#!/usr/bin/env python3
"""KEIBA LAB NAR scheduled forecasts. Requires only Python standard library.
Uses NAR's public daily CSV download for *derived forecasts*, not raw-data mirroring.
Initial model is an explicitly untrained, shrinkage-based form heuristic.
"""
import csv
import datetime as dt
import io
import itertools
import unicodedata
import json
import math
import os
from pathlib import Path
import re
import sys
import urllib.request
import zipfile
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
BASE_URL = "https://www.keiba.go.jp/KeibaWeb/DataDownload/RaceDataDownload?type=daily"
ODDS_URL = "https://www.keiba.go.jp/KeibaWeb/DataDownload/OddsDataDownload?type=daily"
MAX_ODDS_DOWNLOAD = 60 * 1024 * 1024
MAX_ODDS_FILE = 120 * 1024 * 1024
DATA_PATH = Path("data/auto/nar_predictions.json")
MAX_DOWNLOAD = 30 * 1024 * 1024
MAX_FILE = 20 * 1024 * 1024
TRACK_FIELDS = ("競馬場", "日付", "レース番号")
BET_TYPES = ("win", "quinella", "exacta", "trio", "trifecta")
FORECAST_LOCK_BEFORE_START = dt.timedelta(minutes=15)
# Publish provisional forecasts as soon as the official entries arrive.
# A later scheduled run seals the most recent pre-cutoff snapshot; if GitHub
# Actions is delayed, no data observed after T-15 is used to change its picks.


def as_int(value):
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def stats(text):
    nums = re.findall(r"\d+", str(text or ""))
    if len(nums) < 4:
        return None
    wins, seconds, thirds, losses = (int(x) for x in nums[:4])
    total = sum((wins, seconds, thirds, losses))
    if total <= 0 or total > 10000:
        return None
    return wins, total


def shrink_rate(value, prior=0.1, strength=10):
    if value is None:
        return prior
    return (value[0] + prior * strength) / (value[1] + strength)


def parse_csv_bytes(data):
    text = None
    for encoding in ("utf-8-sig", "cp932", "utf-8"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeError:
            continue
    if text is None:
        raise ValueError("CSVの文字コードを読み取れません")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    headers = [h.strip().replace("\ufeff", "") for h in rows[0]]
    if headers and ("競馬場" in headers[0] or "レース番号" in headers):
        data_rows = rows[1:]
    else:
        headers = []
        data_rows = rows
    return [(row, {key: row[i].strip() if i < len(row) else "" for i, key in enumerate(headers)})
            for row in data_rows if len(row) >= 6 and any(x.strip() for x in row)]


def cell(row, mapped, *aliases, idx=None):
    for alias in aliases:
        if alias in mapped:
            return mapped[alias]
    return row[idx].strip() if idx is not None and len(row) > idx else ""


def load_zip_tables(zip_data):
    if len(zip_data) > MAX_DOWNLOAD:
        raise ValueError("ダウンロードファイルの容量が上限を超えました")
    tables = {}
    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
        for member in z.infolist():
            name = member.filename.lower()
            if not name.endswith(".csv") or member.file_size > MAX_FILE:
                continue
            kind = next((x for x in ("racelist", "horselist", "payback") if x in name), None)
            if kind:
                tables[kind] = parse_csv_bytes(z.read(member))
    if "racelist" not in tables or "horselist" not in tables:
        raise ValueError("公式ZIPにレース一覧・出馬表CSVがありません")
    return tables


def row_key(row, fields):
    raw, dic = row
    venue = cell(raw, dic, "競馬場", idx=0)
    date = re.sub("[^0-9]", "", cell(raw, dic, "競走年月日", "開催日", idx=1))
    race = as_int(cell(raw, dic, "レース番号", idx=2))
    if not venue or len(date) != 8 or not race or not 1 <= race <= 20:
        return None
    return venue, date, race


def parse_start(date, value):
    cleaned = re.sub(r"[^0-9]", "", str(value or ""))
    if len(cleaned) == 3:
        cleaned = "0" + cleaned
    if len(cleaned) != 4:
        return None
    try:
        return dt.datetime.strptime(date + cleaned, "%Y%m%d%H%M").replace(tzinfo=JST)
    except ValueError:
        return None


def parse_races(tables):
    race_info, horse_rows = {}, {}
    for item in tables["racelist"]:
        key = row_key(item, TRACK_FIELDS)
        if key is None:
            continue
        row, fields = item
        start = parse_start(key[1], cell(row, fields, "発走時刻", idx=3))
        if start is None:
            continue
        race_info[key] = {"start": start, "name": f"{key[0]} {key[2]}R"}
    for item in tables["horselist"]:
        key = row_key(item, TRACK_FIELDS)
        if key is None:
            continue
        row, fields = item
        no = as_int(cell(row, fields, "馬番", idx=5))
        name = cell(row, fields, "馬名", idx=6)
        if not no or no < 1 or no > 30 or not name:
            continue
        # Critical: result columns are NEVER used to predict.
        horse = {
            "no": no,
            "name": name[:60],
            "overall": stats(cell(row, fields, "全成績", idx=24)),
            "venue": stats(cell(row, fields, "当競馬場成績", idx=27)),
            "distance": stats(cell(row, fields, "うち当距離成績", idx=28)),
            "jockey": stats(cell(row, fields, "騎手成績", idx=17)),
            "rank": as_int(cell(row, fields, "着順", idx=31))
        }
        horse_rows.setdefault(key, []).append(horse)
    out = []
    for key, meta in race_info.items():
        horses = horse_rows.get(key, [])
        nums = [h["no"] for h in horses]
        if len(horses) < 3 or len(nums) != len(set(nums)):
            continue
        out.append({
            "id": f"nar-{key[1]}-{key[0]}-{key[2]:02d}",
            "date": f"{key[1][:4]}-{key[1][4:6]}-{key[1][6:]}",
            "venue": key[0], "race_no": key[2], "name": meta["name"],
            "start": meta["start"], "horses": horses
        })
    return sorted(out, key=lambda r: (r["start"], r["venue"]))


def odds_market_index(zip_data):
    """Stream only official single-win odds from NAR's separate odds ZIP."""
    if len(zip_data) > MAX_ODDS_DOWNLOAD:
        raise ValueError("オッズZIPが大きすぎます")
    out = {}
    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
        members = [m for m in z.infolist()
                   if m.filename.lower().endswith("_odds.csv") and m.file_size <= MAX_ODDS_FILE]
        if not members:
            raise ValueError("公式オッズCSVがありません")
        for member in members:
            with z.open(member) as handle:
                sample = handle.read(4096)
            try:
                sample.decode("utf-8-sig")
                encoding = "utf-8-sig"
            except UnicodeDecodeError:
                encoding = "cp932"
            with z.open(member) as handle:
                reader = csv.reader(io.TextIOWrapper(handle, encoding=encoding, errors="replace", newline=""))
                first = next(reader, None)
                if not first:
                    continue
                header = [x.strip().replace("\ufeff", "") for x in first]
                mapped = "競馬場" in header and "賭式" in header
                columns = {name: idx for idx, name in enumerate(header)} if mapped else {}
                def get(row, key, fallback):
                    pos = columns.get(key, fallback)
                    return row[pos].strip() if len(row) > pos else ""
                def consume(row):
                    bet = unicodedata.normalize("NFKC", get(row, "賭式", 3))
                    if bet not in ("単勝", "単勝式"):
                        return
                    venue = get(row, "競馬場", 0)
                    date = re.sub("[^0-9]", "", get(row, "競走年月日", 1))
                    race_no = as_int(get(row, "レース番号", 2))
                    horse_no = as_int(get(row, "番号1", 4))
                    popularity = as_int(get(row, "人気", 9))
                    try:
                        odds = float(get(row, "オッズ", 7))
                    except (TypeError, ValueError):
                        return
                    if not venue or len(date) != 8 or not race_no or not horse_no or not math.isfinite(odds) or odds < 1 or odds >= 10000:
                        return
                    market = {"no": horse_no, "odds": round(odds, 1)}
                    if popularity is not None and 1 <= popularity <= 50:
                        market["popularity"] = popularity
                    out.setdefault((venue, date, race_no), {})[horse_no] = market
                if not mapped:
                    consume(first)
                for row in reader:
                    consume(row)
    return out



def normalized(values):
    total = sum(values)
    if not values or not math.isfinite(total) or total <= 0:
        return None
    return [v / total for v in values]


def form_probabilities(race):
    scores = [(.45 * shrink_rate(h["overall"])
               + .25 * shrink_rate(h["distance"])
               + .20 * shrink_rate(h["venue"])
               + .10 * shrink_rate(h["jockey"])) for h in race["horses"]]
    return normalized([math.exp(7 * (x - max(scores))) for x in scores])


def market_probabilities(horses, odds_by_no):
    """Only complete snapshots from the forecast run are usable."""
    if not isinstance(odds_by_no, dict):
        return None
    implied = []
    for h in horses:
        row = odds_by_no.get(h["no"])
        if not isinstance(row, dict):
            return None
        try:
            odds = float(row["odds"])
        except (KeyError, TypeError, ValueError):
            return None
        if not math.isfinite(odds) or not 1 <= odds < 10000:
            return None
        implied.append(1 / max(1.01, odds))
    return normalized(implied)


def learn_parameters(records, now):
    """Only prior SETTLED races train. Never use mutable display 'market'."""
    history = []
    for record in records:
        try:
            settled = dt.datetime.fromisoformat(record["settled_at"])
            locked = dt.datetime.fromisoformat(record.get("locked_at") or record["predicted_at"])
            rows = record["ranking"]
            winner = record["result"][0]
            ids = [r["no"] for r in rows]
            values = [float(r.get("form_probability", r["win_probability"])) for r in rows]
            if not (settled < now and locked < now and winner in ids and len(ids) >= 3
                    and all(math.isfinite(v) and v > 0 for v in values)):
                continue
            history.append((settled, record, ids, normalized(values), ids.index(winner)))
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    history.sort(key=lambda x: x[0])
    history = history[-400:]
    n = len(history)
    alpha = 1.
    if n >= 25:
        def loss(a):
            result = 0.
            for _, _, _, probs, pos in history:
                adjusted = normalized([p ** a for p in probs])
                result -= math.log(max(adjusted[pos], 1e-10))
            return result / n + .006 * (a - 1) ** 2
        alpha = min([.5, .75, 1., 1.25, 1.5, 2.], key=loss)
    prelock = []
    for _, record, ids, form, winner_pos in history:
        snap = record.get("market_at_lock")
        if not isinstance(snap, dict):
            continue
        try:
            observed = dt.datetime.fromisoformat(snap["updated_at"])
            locked = dt.datetime.fromisoformat(record.get("locked_at") or record["predicted_at"])
            deadline = dt.datetime.fromisoformat(record["cutoff_at"])
            if observed > locked or observed >= deadline:
                continue
            odds = {h["no"]: h for h in snap["horses"]}
            market = market_probabilities([{"no": n} for n in ids], odds)
            if market:
                prelock.append((normalized([p ** alpha for p in form]), market, winner_pos))
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    weight = .8  # Use the market as primary anchor; fit only when sample is sufficient.
    if len(prelock) >= 60:
        def market_loss(w):
            return (sum(-math.log(max((1-w)*p[i] + w*m[i], 1e-10))
                        for p, m, i in prelock) / len(prelock)
                    + .01 * (w-.8)**2)
        weight = min([.5, .6, .7, .8, .9], key=market_loss)
    return {"form_alpha": alpha, "market_weight": weight,
            "form_training_races": n, "market_training_races": len(prelock)}


def forecast(race, timestamp, market=None, calibration=None):
    deadline = race["start"] - FORECAST_LOCK_BEFORE_START
    if timestamp >= deadline:
        raise ValueError("発走15分前以降のレースの予想は新規作成しません")
    horses = race["horses"]
    cfg = calibration or {"form_alpha": 1., "market_weight": .8,
                          "form_training_races": 0, "market_training_races": 0}
    original_form = form_probabilities(race)
    form = normalized([p ** cfg["form_alpha"] for p in original_form])
    market_p = market_probabilities(horses, market)
    w = cfg["market_weight"] if market_p else 0.
    probs = [(1-w)*p + w*market_p[i] if market_p else p for i, p in enumerate(form)]
    ranked = sorted(range(len(horses)), key=lambda i: (-probs[i], horses[i]["no"]))
    pick = [{"no": horses[i]["no"], "name": horses[i]["name"],
             "win_probability": round(probs[i], 4)} for i in ranked[:3]]
    # All ordered three-horse finishing combinations; no result lookup.
    tickets = []
    for i, j, k in itertools.permutations(range(len(horses)), 3):
        p = probs[i] * probs[j] / max(1e-12, 1-probs[i])
        p *= probs[k] / max(1e-12, 1-probs[i]-probs[j])
        tickets.append((p, [horses[i]["no"], horses[j]["no"], horses[k]["no"]]))
    tickets.sort(key=lambda x: (-x[0], x[1]))
    trio_scores = {}
    for p, numbers in tickets:
        key = tuple(sorted(numbers))
        trio_scores[key] = trio_scores.get(key, 0.) + p
    trio_sorted = sorted(trio_scores.items(), key=lambda x: (-x[1], x[0]))
    output = {
        "id": race["id"], "date": race["date"], "venue": race["venue"],
        "race_no": race["race_no"], "name": race["name"],
        "start_at": race["start"].isoformat(timespec="minutes"),
        "predicted_at": timestamp.isoformat(timespec="seconds"),
        "locked_at": timestamp.isoformat(timespec="seconds"),
        "cutoff_at": deadline.isoformat(timespec="minutes"),
        "model": "form_market_v2_calibrated" if market_p else "form_v2_no_odds",
        "calibration": {k: cfg[k] for k in ("form_alpha","market_weight",
                                           "form_training_races","market_training_races")},
        "top3": pick,
        "ranking": [{"no": horses[i]["no"], "name": horses[i]["name"],
                     "win_probability": round(probs[i], 6),
                     "form_probability": round(original_form[i], 6)} for i in ranked],
        "tickets": [numbers for _, numbers in tickets[:12]],
        "trio_tickets": [list(numbers) for numbers, _ in trio_sorted[:8]],
        "result": None, "settled_at": None, "hits": None
    }
    # Display verified official quotes even in preliminary forecasts. These
    # are observations, not model guesses, and can be incomplete.
    if isinstance(market, dict) and market:
        eligible = {h["no"] for h in horses}
        visible = [dict(market[no]) for no in sorted(market) if no in eligible]
        if visible:
            output["market"] = {
                "horses": visible, "updated_at": timestamp.isoformat(timespec="seconds")}
    if market_p:
        # Immutable pre-lock input; the display-only 'market' can change later.
        output["market_at_lock"] = {
            "horses": [dict(market[h["no"]]) for h in horses],
            "updated_at": timestamp.isoformat(timespec="seconds")}
    return output


def payback_index(tables):
    """Official NAR payback.csv rows keyed by race; missing files stay unknown."""
    found = {}
    for item in tables.get("payback", []):
        key = row_key(item, TRACK_FIELDS)
        if key is not None:
            found.setdefault(key, []).append(item)
    return found


def official_payouts(paybacks, race, result):
    """Read confirmed winning numbers and amounts (JPY per 100 yen).
    Index positions follow NAR's May 2026 official CSV specification.
    Never estimate a payout from win odds.
    """
    key = (race["venue"], race["date"].replace("-", ""), race["race_no"])
    rows = paybacks.get(key, [])
    specs = {
        "win": ((4,), 5, False),
        "quinella": ((24, 25), 26, True),
        "exacta": ((28, 29), 30, False),
        "trio": ((44, 45, 46), 47, True),
        "trifecta": ((49, 50, 51), 52, False),
    }
    amounts = {}
    for raw, fields in rows:
        for bet, (number_columns, money_column, unordered) in specs.items():
            numbers = [as_int(raw[i]) if i < len(raw) else None for i in number_columns]
            expected = result[:len(numbers)]
            if any(n is None for n in numbers):
                continue
            if (sorted(numbers) if unordered else numbers) != (sorted(expected) if unordered else expected):
                continue
            amount = as_int(raw[money_column]) if money_column < len(raw) else None
            if amount is not None and 0 < amount <= 100000000:
                amounts[bet] = amount
    return amounts


def settled_order(horses):
    ranked = {i: [] for i in (1, 2, 3)}
    for horse in horses:
        if horse["rank"] in ranked:
            ranked[horse["rank"]].append(horse["no"])
    # Skip dead heats / partial or conflicting provisional results.
    if any(len(ranked[n]) != 1 for n in (1, 2, 3)):
        return None
    return [ranked[n][0] for n in (1, 2, 3)]


def frozen_trio_tickets(pred):
    """Never synthesize new picks using results. Older records derive unordered
    combos only from the originally saved, pre-race trifecta tickets.
    """
    stored = pred.get("trio_tickets")
    if isinstance(stored, list):
        return [sorted(x) for x in stored if isinstance(x, list) and len(x) == 3]
    existing = pred.get("tickets") or []
    seen = set()
    output = []
    for ticket in existing:
        if not isinstance(ticket, list) or len(ticket) != 3:
            continue
        key = tuple(sorted(ticket))
        if len(set(key)) != 3 or key in seen:
            continue
        seen.add(key)
        output.append(list(key))
    return output


def trio_multi_hit(pred, result):
    if not isinstance(result, list) or len(result) != 3:
        return False
    return sorted(result) in frozen_trio_tickets(pred)


def settle(pred, result, now):
    if pred.get("result") is not None:
        return False
    start = dt.datetime.fromisoformat(pred["start_at"])
    if now < start + dt.timedelta(minutes=3):
        return False
    a, b, c = result
    guessed = [x["no"] for x in pred["top3"]]
    same_pair = lambda q, w: sorted(q) == sorted(w)
    pred["result"] = result
    pred["settled_at"] = now.isoformat(timespec="seconds")
    pred["hits"] = {
        "win": guessed[0] == a,
        "quinella": same_pair(guessed[:2], [a, b]),
        "exacta": guessed[:2] == [a, b],
        "trio": same_pair(guessed, result),
        "trio_multi": trio_multi_hit(pred, result),
        "trifecta": result in pred["tickets"]
    }
    return True


def summary(predictions):
    valid = [x for x in predictions if isinstance(x.get("hits"), dict)]
    rate = lambda key: round(sum(x["hits"].get(key) is True for x in valid) / len(valid) * 100, 1) if valid else None
    # Include older sealed forecasts only by interpreting their pre-race trifecta
    # shortlist as unordered picks. No horse or probability is added after off.
    multi_eligible = [x for x in valid if frozen_trio_tickets(x)]
    trio_multi_rate = round(
        100 * sum(trio_multi_hit(x, x["result"]) for x in multi_eligible) / len(multi_eligible), 1
    ) if multi_eligible else None
    return {
        "predicted": len(predictions), "settled": len(valid),
        "pending": len(predictions) - len(valid),
        "win": rate("win"), "quinella": rate("quinella"),
        "exacta": rate("exacta"), "trio": rate("trio"),
        "trio_multi": trio_multi_rate, "trio_multi_settled": len(multi_eligible),
        "trifecta": rate("trifecta"),
        "note": "発走前に予想した確定レースのみ。三連複本線1点と三連複候補最大8点は別集計。以前のレースの三連複候補は保存済み三連単12点を順不同に換算。三連単候補は12点。"
    }


def update_data(races, now, previous, paybacks=None, odds_index=None):
    old = previous.get("races", [])
    if not isinstance(old, list):
        raise ValueError("保存された予想履歴の形式が不正です")
    entries = {p["id"]: p for p in old if isinstance(p, dict) and p.get("id")}
    old_drafts = previous.get("drafts", [])
    if not isinstance(old_drafts, list):
        raise ValueError("事前予想の保存形式が不正です")
    drafts = {
        p["id"]: p for p in old_drafts
        if isinstance(p, dict) and isinstance(p.get("id"), str)
        and p["id"] not in entries
    }
    calibration = learn_parameters(old, now)
    past_schedule = previous.get("schedule", [])
    if not isinstance(past_schedule, list):
        past_schedule = []
    schedule_by_id = {
        x["id"]: x for x in past_schedule
        if isinstance(x, dict) and isinstance(x.get("id"), str)
        and isinstance(x.get("date"), str)
    }
    for race in races:
        schedule_by_id[race["id"]] = {
            "id": race["id"], "date": race["date"], "venue": race["venue"],
            "race_no": race["race_no"], "name": race["name"],
            "start_at": race["start"].isoformat(timespec="minutes")
        }
    oldest_date = (now.date() - dt.timedelta(days=35)).isoformat()
    calendar = sorted(
        (x for x in schedule_by_id.values() if x["date"] >= oldest_date),
        key=lambda x: (x["date"], x["venue"], x["race_no"])
    )[-1200:]
    schedule_changed = calendar != previous.get("schedule", [])
    added = 0
    settled = 0
    payout_updated = 0
    odds_updated = 0
    paybacks = paybacks or {}
    odds_index = odds_index or {}

    # Seal a snapshot that was computed before T-15, even if this scheduled
    # workflow was delayed or today's official CSV no longer lists that race.
    # Never recompute a snapshot after the deadline or use race results in it.
    for ident, draft in list(drafts.items()):
        try:
            cutoff = dt.datetime.fromisoformat(draft["cutoff_at"])
            predicted = dt.datetime.fromisoformat(draft["predicted_at"])
            start_at = dt.datetime.fromisoformat(draft["start_at"])
            valid = (predicted < cutoff == start_at - FORECAST_LOCK_BEFORE_START
                     and predicted < now and len(draft.get("top3", [])) == 3)
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid or ident in entries:
            del drafts[ident]
            continue
        if now >= cutoff:
            sealed = dict(draft)
            sealed.pop("status", None)
            # locked_at is the source snapshot timestamp, not an invented
            # action execution time; finalized_at records actual commit work.
            sealed["locked_at"] = sealed["predicted_at"]
            sealed["finalized_at"] = now.isoformat(timespec="seconds")
            entries[ident] = sealed
            del drafts[ident]
            added += 1

    for race in races:
        ident = race["id"]
        market = odds_index.get((race["venue"], race["date"].replace("-", ""), race["race_no"]), {})
        deadline = race["start"] - FORECAST_LOCK_BEFORE_START
        if ident not in entries:
            if now < deadline and not any(h["rank"] in (1, 2, 3) for h in race["horses"]):
                # Publish a preliminary prediction early, keep updating it
                # with only data available strictly before the T-15 cutoff.
                prior = drafts.get(ident)
                proposal = forecast(race, now, market, calibration)
                # If an odds ZIP temporarily fails, keep the prior observed
                # quote timestamp for display. Never pretend it is current.
                if not proposal.get("market") and prior and isinstance(prior.get("market"), dict):
                    proposal["market"] = prior["market"]
                proposal.pop("locked_at", None)
                proposal["status"] = "draft"
                proposal["created_at"] = prior.get("created_at", prior["predicted_at"]) if prior else proposal["predicted_at"]
                drafts[ident] = proposal
            continue

        # Frozen picks never change. Display-only market data and verified
        # results may still be added after the race without touching the picks.
        if market:
            valid_nos = {h["no"] for h in race["horses"]}
            items = [market[n] for n in sorted(market) if n in valid_nos]
            record = entries[ident]
            if items and record.get("market", {}).get("horses") != items:
                record["market"] = {"horses": items, "updated_at": now.isoformat(timespec="seconds")}
                odds_updated += 1
        order = settled_order(race["horses"])
        if order and settle(entries[ident], order, now):
            settled += 1
        record = entries[ident]
        if isinstance(record.get("result"), list):
            verified = official_payouts(paybacks, race, record["result"])
            if verified:
                old_amounts = record.get("payouts") or {}
                if any(old_amounts.get(k) != v for k, v in verified.items()):
                    record["payouts"] = {**old_amounts, **verified}
                    payout_updated += 1

    predictions = sorted(entries.values(), key=lambda x: (x["date"], x["start_at"]), reverse=True)[:5000]
    # Keep draft storage bounded, but not at the expense of upcoming races.
    previews = sorted(drafts.values(), key=lambda x: (x["date"], x["start_at"]), reverse=True)[:500]
    method = "出馬表取得後に事前予想を公開し発走15分前まで更新。締切時点の最新の事前予想を固定。確定結果のみで学習し予想を遡及変更しません。"
    model_changed = previous.get("method") != method or previous.get("learning") != calibration
    drafts_changed = previews != previous.get("drafts", [])
    return {
        "schema_version": 1, "scope": "NAR地方競馬のみ（中央JRAは対象外）",
        "source": "NAR公式CSVデータ（分析結果のみ表示）",
        "method": method,
        "learning": calibration,
        "updated_at": now.isoformat(timespec="seconds") if (added or settled or payout_updated or odds_updated
                         or schedule_changed or drafts_changed or model_changed or not previous)
                      else previous.get("updated_at"),
        "schedule_updated_at": now.isoformat(timespec="seconds") if schedule_changed or not previous else previous.get("schedule_updated_at"),
        "schedule": calendar,
        "drafts": previews,
        "races": predictions, "summary": summary(predictions)
    }, added, settled, payout_updated + odds_updated


def fetch_daily_zip(url=BASE_URL, max_download=MAX_DOWNLOAD):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "KEIBA-LAB/3.3 (personal race form analysis)", "Accept": "application/zip"}
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        data = response.read(max_download + 1)
    if len(data) > max_download:
        raise ValueError("公式ZIPが容量上限を超えています")
    return data


def selftest():
    now = dt.datetime(2026, 11, 2, 15, 22, tzinfo=JST)
    horse_template = []
    for no in range(1, 9):
        row = [""] * 36
        row[0], row[1], row[2], row[5], row[6] = "門別", "20261102", "1", str(no), f"TEST{no}"
        row[17], row[24], row[27], row[28] = "1-1-0-6", f"{no}-1-2-12", "2-0-1-9", "1-0-1-9"
        horse_template.append((row, {}))
    row = [""] * 30
    row[0], row[1], row[2], row[3] = "門別", "20261102", "1", "1540"
    races = parse_races({"racelist": [(row, {})], "horselist": horse_template})
    assert len(races) == 1
    early, early_added, _, _ = update_data(races, now - dt.timedelta(minutes=15), {})
    assert early_added == 0 and early["races"] == [] and len(early["drafts"]) == 1
    assert len(early["schedule"]) == 1 and early["schedule"][0]["date"] == "2026-11-02"
    assert early["schedule"][0]["start_at"] == "2026-11-02T15:40+09:00"
    preview = early["drafts"][0]
    assert preview["status"] == "draft" and "locked_at" not in preview
    assert preview["predicted_at"] == "2026-11-02T15:07:00+09:00"
    assert preview["created_at"] == preview["predicted_at"]
    draft_updated, n, _, _ = update_data(races, now, early)
    assert n == 0 and len(draft_updated["drafts"]) == 1
    latest = draft_updated["drafts"][0]
    assert latest["predicted_at"] == now.isoformat(timespec="seconds")
    assert latest["created_at"] == preview["created_at"]
    assert "locked_at" not in latest
    assert forecast(races[0], races[0]["start"] - dt.timedelta(minutes=16))["top3"]
    for delta in (dt.timedelta(minutes=15), dt.timedelta(minutes=14)):
        try:
            forecast(races[0], races[0]["start"] - delta)
        except ValueError:
            pass
        else:
            raise AssertionError("15分前以降の予想作成が許可されました")
    cutoff = races[0]["start"] - FORECAST_LOCK_BEFORE_START
    # If the scheduled action runs after T-15, it must ONLY seal the
    # pre-existing early snapshot; no new or result-derived picks.
    locked, added, settled_count, payout_count = update_data(
        races, cutoff + dt.timedelta(minutes=2), draft_updated)
    assert added == 1 and settled_count == 0 and payout_count == 0
    assert len(locked["drafts"]) == 0 and len(locked["races"]) == 1
    pre = locked["races"][0]
    assert pre["predicted_at"] == latest["predicted_at"]
    assert pre["locked_at"] == latest["predicted_at"]
    assert pre["top3"] == latest["top3"] and pre["tickets"] == latest["tickets"]
    assert pre["trio_tickets"] == latest["trio_tickets"]
    assert dt.datetime.fromisoformat(pre["finalized_at"]) > dt.datetime.fromisoformat(pre["cutoff_at"])
    assert len(pre["tickets"]) == 12 and abs(sum(x["win_probability"] for x in pre["top3"])) < 1.001
    assert len(pre["trio_tickets"]) == 8
    assert all(ticket == sorted(ticket) and len(ticket) == len(set(ticket)) == 3 for ticket in pre["trio_tickets"])
    assert len({tuple(ticket) for ticket in pre["trio_tickets"]}) == 8
    # Never backfill if an entire prediction was missed before the cutoff.
    missed, missed_added, _, _ = update_data(races, cutoff + dt.timedelta(minutes=1), {})
    assert missed_added == 0 and missed["races"] == [] and missed["drafts"] == []
    # A late workflow can still seal a verified previously saved preview.
    delayed, count, _, _ = update_data([], races[0]["start"] + dt.timedelta(minutes=12), early)
    assert count == 1 and delayed["races"][0]["top3"] == preview["top3"]
    for i, (_, _) in enumerate(horse_template):
        horse_template[i][0][31] = str(i+1) if i < 3 else ""
    races = parse_races({"racelist": [(row, {})], "horselist": horse_template})
    late = dt.datetime(2026, 11, 2, 16, 0, tzinfo=JST)
    out2, a, s, p = update_data(races, late, locked)
    assert a == 0 and s == 1 and out2["summary"]["settled"] == 1
    assert out2["summary"]["trio_multi_settled"] == 1
    assert out2["races"][0]["hits"]["trio_multi"] == trio_multi_hit(out2["races"][0], [1, 2, 3])
    out3, a, s, p = update_data(races, late, out2)
    assert a == 0 and s == 0 and out3["races"][0]["predicted_at"] == pre["predicted_at"]
    assert update_data(races, late, {})[1] == 0
    assert len(update_data(races, late, {})[0]["schedule"]) == 1
    assert update_data(races, late, {})[0]["races"] == []
    # A verified payback can be added in a subsequent refresh.
    payrow = [""] * 54
    payrow[0], payrow[1], payrow[2] = "門別", "20261102", "1"
    for pos, value in {4:1, 5:430, 24:1, 25:2, 26:810, 28:1, 29:2, 30:1420,
                       44:1, 45:2, 46:3, 47:2750, 49:1, 50:2, 51:3, 52:14820}.items():
        payrow[pos] = str(value)
    paybacks = payback_index({"payback": [(payrow, {})]})
    enriched, a, s, p = update_data(races, late, out3, paybacks)
    assert (a, s, p) == (0, 0, 1)
    assert enriched["races"][0]["payouts"] == {
        "win": 430, "quinella": 810, "exacta": 1420, "trio": 2750, "trifecta": 14820}
    assert update_data(races, late, enriched, paybacks)[3] == 0
    old = dict(pre)
    old.pop("trio_tickets")
    assert len(frozen_trio_tickets(old)) >= 1
    assert {tuple(t) for t in frozen_trio_tickets(old)} == {tuple(sorted(t)) for t in old["tickets"]}
    # Official ten-column NAR odds format: include only single-win odds.
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        rows = [
            ["競馬場", "競走年月日", "レース番号", "賭式", "番号1",
             "番号2", "番号3", "オッズ", "オッズ（最大）", "人気"],
            ["門別", "20261102", "1", "単勝", "2", "", "", "3.4", "", "1"],
            ["門別", "20261102", "1", "単勝", "1", "", "", "10.8", "", "4"],
            ["門別", "20261102", "1", "３連単", "1", "2", "3", "88.5", "", "3"],
        ]
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerows(rows)
        z.writestr("20261102_odds.csv", stream.getvalue().encode("utf-8-sig"))
    market = odds_market_index(mem.getvalue())
    assert market[("門別", "20261102", 1)] == {
        2: {"no": 2, "odds": 3.4, "popularity": 1},
        1: {"no": 1, "odds": 10.8, "popularity": 4},
    }
    # Regression: a live draft must expose official popularity/odds before T-15.
    # Sealing the draft must retain the same quote and original predictions.
    upcoming = {**races[0],
                "horses": [{**h, "rank": None} for h in races[0]["horses"]]}
    draft_odds, _, _, _ = update_data([upcoming], now, {}, odds_index=market)
    displayed = draft_odds["drafts"][0]
    assert displayed["market"]["horses"] == [
        {"no": 1, "odds": 10.8, "popularity": 4},
        {"no": 2, "odds": 3.4, "popularity": 1}]
    assert displayed["market"]["updated_at"] == displayed["predicted_at"]
    # A temporarily missing ZIP should not erase the last observed numbers.
    kept_odds, _, _, _ = update_data(
        [upcoming], now + dt.timedelta(minutes=1), draft_odds)
    assert kept_odds["drafts"][0]["market"] == displayed["market"]
    lock_odds, count_odds, _, _ = update_data(
        [upcoming], cutoff + dt.timedelta(seconds=30), kept_odds)
    assert count_odds == 1
    assert lock_odds["races"][0]["market"] == displayed["market"]
    assert lock_odds["races"][0]["top3"] == kept_odds["drafts"][0]["top3"]
    again, a, settled_again, changed = update_data(
        races, late, enriched, paybacks, market)
    assert (a, settled_again, changed) == (0, 0, 1)
    assert again["races"][0]["market"]["horses"] == [
        {"no": 1, "odds": 10.8, "popularity": 4},
        {"no": 2, "odds": 3.4, "popularity": 1},
    ]
    assert again["races"][0]["top3"] == pre["top3"]
    assert again["races"][0]["tickets"] == pre["tickets"]
    assert update_data(races, late, again, paybacks, market)[3] == 0
    assert "ranking" in pre and len(pre["ranking"]) == len(races[0]["horses"])
    # Regression: the odds leader must influence the NEW forecast at T-17.
    big_fav = {i: {"no": i, "odds": 1.1 if i == 1 else 100.0}
               for i in range(1, 9)}
    trained = forecast(races[0], dt.datetime(2026, 11, 2, 15, 23, tzinfo=JST),
                       big_fav, {"form_alpha": 1., "market_weight": .8,
                                 "form_training_races": 33, "market_training_races": 0})
    assert trained["top3"][0]["no"] == 1
    assert trained["top3"][0]["no"] != forecast(races[0], now)["top3"][0]["no"]
    assert trained["market_at_lock"]["updated_at"] == trained["locked_at"]
    assert trained["cutoff_at"] == "2026-11-02T15:25+09:00"
    assert forecast(races[0], now)["model"] == "form_v2_no_odds"
    past = [dict(pre, result=[1, 2, 3], settled_at="2026-11-02T16:01:00+09:00",
                 market={"horses": list(big_fav.values()),
                         "updated_at": "2026-11-02T16:10:00+09:00"})
            for _ in range(30)]
    assert learn_parameters(past, dt.datetime(2026, 11, 2, 17, tzinfo=JST))["form_training_races"] == 30
    assert learn_parameters(past, dt.datetime(2026, 11, 2, 17, tzinfo=JST))["market_training_races"] == 0
    assert learn_parameters(past, dt.datetime(2026, 11, 2, 15, tzinfo=JST))["form_training_races"] == 0
    print("PASS: pre-lock odds, history-only calibration and immutable predictions")
    print("PASS: official NAR single-win odds, popularity and frozen ranking")
    print("PASS: early provisional forecasts, T-15 cutoff, late safe finalization, frozen picks and results")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    # Capture the clock AFTER network fetches, so a slow ZIP download cannot
    # produce forecasts timestamped before the T-15 cutoff retroactively.
    source_bytes = fetch_daily_zip()
    tables = load_zip_tables(source_bytes)
    races = parse_races(tables)
    if not races:
        raise RuntimeError("有効なレースがありません。CSV形式か配信状況を確認してください")
    previous = json.loads(DATA_PATH.read_text(encoding="utf-8")) if DATA_PATH.exists() else {}
    odds_index = {}
    try:
        odds_index = odds_market_index(fetch_daily_zip(ODDS_URL, MAX_ODDS_DOWNLOAD))
    except Exception as exc:
        print(f"NAR公式オッズ未取得（予想・結果は続行）: {exc}", file=sys.stderr)
    now = dt.datetime.now(JST)
    out, added, settled_count, payout_count = update_data(races, now, previous, payback_index(tables), odds_index)
    if (added or settled_count or payout_count or out["schedule"] != previous.get("schedule", [])
            or out.get("drafts") != previous.get("drafts", [])
            or out.get("method") != previous.get("method") or out.get("learning") != previous.get("learning")
            or not DATA_PATH.exists()):
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        DATA_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"NAR calendar entries: {len(out['schedule'])}; NAR races: {len(races)}, preliminary: {len(out['drafts'])}, newly frozen: {added}, newly settled: {settled_count}, market/payout updates: {payout_count}; total frozen: {out['summary']['predicted']}, settled: {out['summary']['settled']}")


if __name__ == "__main__":
    main()
