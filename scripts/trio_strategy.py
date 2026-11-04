#!/usr/bin/env python3
"""Exploratory pre-race trio strategy for KEIBA LAB; Python standard library only.

Keep reference tickets separate from optional, odds-gated selections. Archived
forecasts and results are NEVER rewritten during a retrospective comparison.
Model-implied return multiples are hypotheses, not verified expected returns.
"""
import csv
import datetime as dt
import io
import itertools
import json
import math
import sys
import unicodedata
import zipfile
from pathlib import Path


def normalize(values):
    s = sum(values)
    return [v / s for v in values] if s > 0 and math.isfinite(s) else None


def market_probabilities(nos, snapshot):
    if not isinstance(snapshot, dict) or set(nos) - set(snapshot):
        return None
    odds = []
    for number in nos:
        row = snapshot.get(number)
        value = row.get("odds") if isinstance(row, dict) else None
        try:
            o = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(o) or o < 1 or o >= 10000:
            return None
        odds.append(1.0 / max(1.01, o))
    return normalize(odds)


def trio_odds_index(archive):
    """Parse observed 3連複 quotations. Never construct them from WIN odds."""
    output = {}
    if len(archive) > 60 * 1024 * 1024:
        raise ValueError("trio odds ZIP exceeds size limit")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        for info in zipped.infolist():
            if not info.filename.lower().endswith("_odds.csv") or info.file_size > 120 * 1024 * 1024:
                continue
            with zipped.open(info) as stream:
                sample = stream.read(4096)
            try:
                sample.decode("utf-8-sig")
                encoding = "utf-8-sig"
            except UnicodeDecodeError:
                encoding = "cp932"
            with zipped.open(info) as stream:
                rows = csv.reader(io.TextIOWrapper(stream, encoding=encoding, errors="replace", newline=""))
                first = next(rows, None)
                if not first:
                    continue
                header = [v.strip().replace("\ufeff", "") for v in first]
                named = "賭式" in header and "競馬場" in header
                columns = {v: i for i, v in enumerate(header)} if named else {}
                def read(row, key, default):
                    idx = columns.get(key, default)
                    return row[idx].strip() if idx < len(row) else ""
                def consume(row):
                    bet = unicodedata.normalize("NFKC", read(row, "賭式", 3)).strip()
                    if bet not in ("3連複", "三連複"):
                        return
                    venue = read(row, "競馬場", 0)
                    date = "".join(c for c in read(row, "競走年月日", 1) if c.isdigit())
                    try:
                        race = int(read(row, "レース番号", 2))
                        nums = tuple(sorted(int(read(row, f"番号{i}", i + 3)) for i in (1, 2, 3)))
                        odds = float(read(row, "オッズ", 7))
                    except (TypeError, ValueError):
                        return
                    if (not venue or len(date) != 8 or not 1 <= race <= 20
                            or len(set(nums)) != 3 or not all(1 <= n <= 30 for n in nums)
                            or not math.isfinite(odds) or not 1 <= odds < 10000):
                        return
                    output.setdefault((venue, date, race), {})[nums] = round(odds, 1)
                if not named:
                    consume(first)
                for row in rows:
                    consume(row)
    return output


def ticket_ranking(horses, win, form, market, config=None):
    """Rank 3-way tickets using distinct conditional second/third weights."""
    config = config or {}
    n = len(horses)
    if n < 3 or len(win) != n or len(form) != n:
        raise ValueError("Incomplete race probability input")
    if market is not None and len(market) == n:
        second_w = float(config.get("place_market_weight", .65) or .65)
        third_w = float(config.get("show_market_weight", .50) or .50)
        second = normalize([(1-second_w)*form[i] + second_w*market[i] for i in range(n)])
        third = normalize([(1-third_w)*form[i] + third_w*market[i] for i in range(n)])
    else:
        second, third = form, form
    ordered, trios = [], {}
    for i, j, k in itertools.permutations(range(n), 3):
        prob = win[i] * second[j] / max(1e-12, 1-second[i])
        prob *= third[k] / max(1e-12, 1-third[i]-third[j])
        ticket = [horses[i]["no"], horses[j]["no"], horses[k]["no"]]
        ordered.append((prob, ticket))
        key = tuple(sorted(ticket))
        trios[key] = trios.get(key, 0) + prob
    ordered.sort(key=lambda x: (-x[0], x[1]))
    return ordered, sorted(trios.items(), key=lambda x: (-x[1], x[0]))


def value_selection(ranked_trios, official_quotes, observed_at, threshold=1.15):
    """Use observed pre-cutoff TRIO odds. Missing or insufficient value -> skip."""
    available = isinstance(official_quotes, dict) and bool(official_quotes)
    examined = []
    if available:
        for ticket, probability in ranked_trios[:24]:
            price = official_quotes.get(ticket)
            if not isinstance(price, (int, float)) or not math.isfinite(price) or price < 1:
                continue
            ratio = probability * price
            examined.append({
                "ticket": list(ticket), "model_probability": round(probability, 6),
                "official_trio_odds": round(price, 1),
                "model_return_multiple": round(ratio, 3),
                "passes_threshold": ratio >= threshold
            })
    qualifying = [row for row in examined if row["passes_threshold"]]
    count = 8 if len(qualifying) >= 8 else 6 if len(qualifying) >= 6 else 4 if len(qualifying) >= 4 else 0
    chosen = qualifying[:count]  # probability order, NOT hindsight or max theoretical odds
    return {
        "status": "candidate" if count else "below_threshold" if examined else "no_matching_quotes" if available else "no_official_trio_odds",
        "model": "experimental_v1", "threshold": threshold,
        "observed_at": observed_at if available else None,
        "quote_count": len(official_quotes) if available else 0,
        "tickets": [r["ticket"] for r in chosen],
        "evaluated": examined
    }


def calibration_for_podium(records, now):
    """Fit position-specific market weights using settled, pre-lock races only."""
    observations = []
    for r in records:
        try:
            if dt.datetime.fromisoformat(r["settled_at"]) >= now:
                continue
            snap = r.get("market_at_lock") or {}
            if dt.datetime.fromisoformat(snap["updated_at"]) >= dt.datetime.fromisoformat(r["cutoff_at"]):
                continue
            if dt.datetime.fromisoformat(snap["updated_at"]) > dt.datetime.fromisoformat(r["locked_at"]):
                continue
            rows = r["ranking"]
            ids = [x["no"] for x in rows]
            if len(ids) < 3 or len(r["result"]) < 3 or len(set(r["result"])) < 3:
                continue
            form = normalize([float(x["form_probability"]) ** float(r.get("calibration", {}).get("form_alpha", 1)) for x in rows])
            market = market_probabilities(ids, {x["no"]: x for x in snap["horses"]})
            if not form or not market:
                continue
            indices = [ids.index(n) for n in r["result"]]
            observations.append((form, market, indices))
        except (KeyError, TypeError, ValueError, IndexError, OverflowError):
            continue
    defaults = (.65, .50)
    if len(observations) < 60:
        return {"place_market_weight": defaults[0], "show_market_weight": defaults[1], "podium_training_races": len(observations)}
    def loss(weight, position, prior):
        total = 0
        for form, market, ids in observations[-400:]:
            probs = normalize([(1-weight)*f + weight*m for f, m in zip(form, market)])
            excluded = ids[:position]
            conditional = probs[ids[position]] / max(1e-12, 1-sum(probs[j] for j in excluded))
            total -= math.log(max(conditional, 1e-12))
        return total / len(observations[-400:]) + .02*(weight-prior)**2
    weights = [.3, .5, .65, .8, 1.0]
    return {
        "place_market_weight": min(weights, key=lambda w: loss(w, 1, defaults[0])),
        "show_market_weight": min(weights, key=lambda w: loss(w, 2, defaults[1])),
        "podium_training_races": len(observations)
    }


def archived_trio_tickets(record):
    if isinstance(record.get("trio_tickets"), list):
        return [tuple(sorted(t)) for t in record["trio_tickets"] if isinstance(t, list) and len(t) == 3]
    return list(dict.fromkeys(tuple(sorted(t)) for t in record.get("tickets", []) if isinstance(t, list) and len(t) == 3))


def simulated_trio_tickets(record):
    """Replay archived PRE-RACE probabilities, without using results to choose."""
    try:
        rows = record["ranking"]
        nos = [r["no"] for r in rows]
        win = normalize([float(r["win_probability"]) for r in rows])
        alpha = float(record.get("calibration", {}).get("form_alpha", 1))
        form = normalize([float(r["form_probability"]) ** alpha for r in rows])
        snap = record.get("market_at_lock") or {}
        market = None
        if snap and dt.datetime.fromisoformat(snap["updated_at"]) < dt.datetime.fromisoformat(record["cutoff_at"]):
            market = market_probabilities(nos, {h["no"]: h for h in snap["horses"]})
        if not win or not form:
            return []
        config = record.get("calibration") or {}
        _, combos = ticket_ranking(rows, win, form, market, config)
        return [t for t, _ in combos]
    except (KeyError, TypeError, ValueError, OverflowError):
        return []


def backtest(records, day=None):
    """Offline historical comparison. NOT a prospective estimate or training."""
    relevant = [r for r in records if isinstance(r.get("result"), list) and len(r["result"]) == 3
                and isinstance(r.get("payouts", {}).get("trio"), int)
                and (day is None or r.get("date") == day)]
    strategies = {f"{model}_{n}": {"races": 0, "hits": 0, "spent": 0, "paid": 0}
                  for model in ("saved", "simulation") for n in (4, 6, 8)}
    by_venue = {}
    for r in relevant:
        result = tuple(sorted(r["result"]))
        for model, tickets in (("saved", archived_trio_tickets(r)), ("simulation", simulated_trio_tickets(r))):
            for n in (4, 6, 8):
                picks = tickets[:n]
                if len(picks) < n:
                    continue
                record = strategies[f"{model}_{n}"]
                record["races"] += 1
                record["spent"] += n*100
                if result in picks:
                    record["hits"] += 1
                    record["paid"] += r["payouts"]["trio"]
        by_venue[r["venue"]] = by_venue.get(r["venue"], 0) + 1
    for row in strategies.values():
        row["roi_pct"] = round(row["paid"]/row["spent"]*100, 1) if row["spent"] else None
        row["hit_pct"] = round(row["hits"]/row["races"]*100, 1) if row["races"] else None
    return {"date": day or "all", "eligible_races": len(relevant), "venue_counts": by_venue,
            "strategies": strategies, "warning": "過去データの再計算。実運用と将来成績を保証しない。過去の買い目は不変更。"}


def selftest():
    horses = [{"no": i} for i in range(1, 7)]
    win = normalize([.38, .25, .17, .1, .06, .04])
    form = normalize([.25, .16, .12, .2, .15, .12])
    ordered, trios = ticket_ranking(horses, win, form, win)
    assert len(ordered) == 120 and len(trios) == 20
    assert abs(sum(p for _, p in trios) - 1) < 1e-8
    quotes = {t: 100. for t, _ in trios}
    picked = value_selection(trios, quotes, "2026-11-04T19:00+09:00")
    assert len(picked["tickets"]) == 8
    assert len(value_selection(trios, {}, "2026-11-04T19:00+09:00")["tickets"]) == 0
    assert len(value_selection(trios, {trios[0][0]: 1.}, "2026-11-04T19:00+09:00")["tickets"]) == 0
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        text = io.StringIO()
        csv.writer(text).writerows([
            ["競馬場", "競走年月日", "レース番号", "賭式", "番号1", "番号2", "番号3", "オッズ", "オッズ（最大）", "人気"],
            ["船橋", "20261104", "12", "３連複", "1", "2", "3", "55.5", "", "4"],
            ["船橋", "20261104", "12", "単勝", "1", "", "", "3.2", "", "1"],
            ["船橋", "20261104", "12", "３連複", "1", "1", "3", "99", "", "1"]
        ])
        z.writestr("20261104_odds.csv", text.getvalue().encode("utf-8-sig"))
    assert trio_odds_index(buf.getvalue()) == {("船橋", "20261104", 12): {(1, 2, 3): 55.5}}
    synthetic = {"result": [1, 2, 3], "payouts": {"trio": 500}, "venue": "船橋", "date": "2026-11-04",
                 "trio_tickets": [[1, 2, 3], [1, 2, 4], [1, 2, 5], [1, 2, 6]]}
    stat = backtest([synthetic], "2026-11-04")["strategies"]["saved_4"]
    assert stat["hits"] == 1 and stat["spent"] == 400 and stat["paid"] == 500
    print("PASS: pre-race trio quotes only, normalized podium model, odds-gated 4/6/8/skip and honest offline backtest")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--backtest" in sys.argv:
        path = Path("data/auto/nar_predictions.json")
        races = json.loads(path.read_text(encoding="utf-8")).get("races", [])
        day = next((v.split("=", 1)[1] for v in sys.argv[1:] if v.startswith("--date=")), None)
        print(json.dumps(backtest(races, day), ensure_ascii=False, indent=2))
    else:
        print("usage: python scripts/trio_strategy.py --selftest | --backtest [--date=YYYY-MM-DD]")
