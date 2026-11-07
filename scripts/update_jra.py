#!/usr/bin/env python3
"""Scheduled JRA forecast ingestion from a separately licensed, redistribution-authorized JSON feed.

No JRA site scraping, JRA-VAN Data Lab JV-Link credential sharing, or unofficial
bypass. The feed is an adapter endpoint supplied by a licensed data provider.
This repository is public; only execute with explicit PUBLICATION authorization.
"""
from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import os
from pathlib import Path
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo
from trio_strategy import top_five_tickets, trifecta_plan

JST = ZoneInfo("Asia/Tokyo")
OUT = Path("data/auto/jra_predictions.json")
VENUES = {"東京", "中山", "京都", "阪神", "中京", "新潟", "福島", "小倉", "札幌", "函館"}
CUT_OFF = dt.timedelta(minutes=15)
KEEP_DAYS = 21
MAX_FEED_BYTES = 3 * 1024 * 1024


def iso(value):
    x = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if x.tzinfo is None:
        raise ValueError("start_at requires an explicit timezone")
    return x.astimezone(JST)


def race_id(r):
    return f"jra-{r['date'].replace('-', '')}-{r['venue']}-{int(r['race_no']):02d}"


def normalized_race(r):
    """Refuse fabricated, incomplete or stale entries, rather than filling gaps."""
    if not isinstance(r, dict):
        raise ValueError("Race must be an object")
    date = str(r["date"])
    dt.date.fromisoformat(date)
    venue = str(r["venue"])
    no = int(r["race_no"])
    start = iso(r["start_at"])
    if venue not in VENUES or not 1 <= no <= 12 or start.date().isoformat() != date:
        raise ValueError("Invalid JRA venue, race number, or local date")
    horses = []
    for h in r["horses"]:
        n = int(h["no"])
        name = str(h["name"]).strip()
        odds = float(h["odds"])
        if not 1 <= n <= 18 or not name or len(name) > 90 or not math.isfinite(odds) or not 1 <= odds < 10000:
            raise ValueError("Missing or invalid horse number/name/odds")
        horses.append({"no": n, "name": name, "odds": odds})
    if not 3 <= len(horses) <= 18 or len(set(x["no"] for x in horses)) != len(horses):
        raise ValueError("3-18 unique runners with current win odds are required")
    return {
        "id": race_id(r), "date": date, "venue": venue, "race_no": no,
        "name": str(r.get("name") or f"{venue} {no}R")[:100],
        "start_at": start.isoformat(timespec="seconds"), "horses": horses,
    }


def forecast(r, now):
    """Market-derived Plackett-Luce approximation; not a trained horse-racing AI."""
    weights = [1.0 / h["odds"] for h in r["horses"]]
    total = sum(weights)
    p = [w / total for w in weights]
    odds_order = sorted(range(len(p)), key=lambda i: (r["horses"][i]["odds"], r["horses"][i]["no"]))
    popularity = {i: rank + 1 for rank, i in enumerate(odds_order)}
    ranks = sorted(range(len(p)), key=lambda i: (-p[i], r["horses"][i]["no"]))
    runners = r["horses"]
    ranking = [
        {"no": runners[i]["no"], "name": runners[i]["name"],
         "win_probability": round(p[i], 6), "odds": runners[i]["odds"], "popularity": popularity[i]}
        for i in ranks
    ]
    trifecta = []
    for i, j, k in itertools.permutations(ranks[:5], 3):
        denom1 = 1 - p[i]
        denom2 = 1 - p[i] - p[j]
        if denom1 <= 0 or denom2 <= 0:
            continue
        probability = p[i] * p[j] / denom1 * p[k] / denom2
        trifecta.append((probability, [runners[i]["no"], runners[j]["no"], runners[k]["no"]]))
    trifecta.sort(key=lambda t: (-t[0], t[1]))
    trio_tickets, tickets = top_five_tickets([h["no"] for h in ranking], trifecta)
    cutoff = iso(r["start_at"]) - CUT_OFF
    return {
        "id": r["id"], "date": r["date"], "venue": r["venue"], "race_no": r["race_no"],
        "name": r["name"], "start_at": r["start_at"],
        "cutoff_at": cutoff.isoformat(timespec="seconds"),
        "status": "draft", "predicted_at": now.isoformat(timespec="seconds"),
        "model": "market_only_plackett_luce_untrained",
        "top3": ranking[:3], "top5": ranking[:5], "ranking": ranking,
        "trio_tickets": trio_tickets, "tickets": tickets,
        "trifecta_plan": {k: v for k, v in trifecta_plan([h["no"] for h in ranking], trifecta).items() if k != "tickets"},
    }


def confirmed_result(entry):
    if not isinstance(entry, dict) or entry.get("confirmed") is not True:
        return None
    place = entry.get("result")
    if not isinstance(place, list) or len(place) != 3:
        return None
    try:
        result = [int(v) for v in place]
    except (ValueError, TypeError):
        return None
    if len(set(result)) != 3 or any(not 1 <= n <= 18 for n in result):
        return None
    payouts = {}
    for key in ("win", "quinella", "exacta", "trio", "trifecta"):
        value = (entry.get("payouts") or {}).get(key)
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100000000:
            payouts[key] = value
    return {"result": result, "payouts": payouts}


def settle(locked, results):
    id_to_result = {}
    for value in results:
        if not isinstance(value, dict):
            continue
        try:
            ident = race_id(value)
            result = confirmed_result(value)
            if result:
                id_to_result[ident] = result
        except (KeyError, ValueError, TypeError):
            continue
    for rec in locked:
        # Never alter an already recorded official result.
        if isinstance(rec.get("result"), list) and len(rec["result"]) == 3:
            continue
        known = id_to_result.get(rec["id"])
        if not known:
            continue
        rec.update(known)
        actual = known["result"]
        rec["hits"] = {
            "win": bool(rec["top3"] and rec["top3"][0]["no"] == actual[0]),
            "trio": any(t == sorted(actual) for t in rec.get("trio_tickets", [])),
            "trifecta": any(t == actual for t in rec.get("tickets", [])),
        }


def update(payload, previous=None, now=None):
    now = now or dt.datetime.now(JST)
    if now.tzinfo is None:
        raise ValueError("aware clock is required")
    now = now.astimezone(JST)
    payload = payload or {}
    if not isinstance(payload.get("races", []), list) or not isinstance(payload.get("results", []), list):
        raise ValueError("Feed requires races and results arrays")
    previous = previous or {}
    locked = {r["id"]: dict(r) for r in previous.get("races", []) if isinstance(r, dict) and r.get("id")}
    drafts = {r["id"]: dict(r) for r in previous.get("drafts", []) if isinstance(r, dict) and r.get("id")}
    schedule = {}
    rejected = 0
    for entry in payload.get("races", []):
        try:
            r = normalized_race(entry)
        except (ValueError, TypeError, KeyError, OverflowError):
            rejected += 1
            continue
        ident = r["id"]
        schedule[ident] = {k: r[k] for k in ("id", "date", "venue", "race_no", "name", "start_at")}
        cutoff = iso(r["start_at"]) - CUT_OFF
        if ident in locked:
            continue
        if now < cutoff:
            drafts[ident] = forecast(r, now)
        # Once the cutoff passed, retain the last PRE-cutoff snapshot only.
    for ident, draft in list(drafts.items()):
        try:
            cutoff = iso(draft["cutoff_at"])
        except (KeyError, ValueError, TypeError):
            drafts.pop(ident, None)
            continue
        if ident in locked:
            drafts.pop(ident, None)
        elif now >= cutoff:
            saved_time = iso(draft["predicted_at"])
            if saved_time >= cutoff:
                drafts.pop(ident, None)
                continue
            locked[ident] = {**draft, "status": "locked",
                              "locked_at": draft["predicted_at"],
                              "finalized_at": now.isoformat(timespec="seconds")}
            drafts.pop(ident, None)
    settled = list(locked.values())
    settle(settled, payload.get("results", []))
    retain_after = (now - dt.timedelta(days=KEEP_DAYS)).date()
    def fresh(record):
        try:
            return dt.date.fromisoformat(record["date"]) >= retain_after
        except (ValueError, TypeError, KeyError):
            return False
    settled = [x for x in settled if fresh(x)]
    active = [x for x in drafts.values() if fresh(x)]
    calendar = sorted([x for x in schedule.values() if fresh(x)], key=lambda x: (x["date"], x["start_at"], x["venue"]))
    settled.sort(key=lambda x: (x["date"], x["start_at"], x["venue"]), reverse=True)
    active.sort(key=lambda x: (x["date"], x["start_at"], x["venue"]))
    verified = [x for x in settled if isinstance(x.get("result"), list) and len(x["result"]) == 3]
    summary = {
        "locked": len(settled), "drafts": len(active), "settled": len(verified),
        "pending": len(settled) - len(verified),
        "win_hits": sum(bool(x.get("hits", {}).get("win")) for x in verified),
        "trio_hits": sum(bool(x.get("hits", {}).get("trio")) for x in verified),
        "trifecta_hits": sum(bool(x.get("hits", {}).get("trifecta")) for x in verified),
        "rejected_entries": rejected,
    }
    return {
        "schema_version": 1, "scope": "JRA中央競馬のみ",
        "source": "契約済み・公開利用許諾済みJSONフィード（提供元を設定）",
        "status": "ready", "updated_at": now.isoformat(timespec="seconds"),
        "method": "単勝オッズの市場支持率による近似。学習済みAIではありません。発走15分前より前の予想だけを固定。",
        "races": settled, "drafts": active, "schedule": calendar, "summary": summary,
    }


class BlockRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Cross-origin/redirecting feeds are not accepted")


def fetch_json(url, token):
    target = urllib.parse.urlsplit(url)
    if target.scheme != "https" or not target.hostname or target.username or target.password or target.fragment:
        raise ValueError("A direct HTTPS feed endpoint is required")
    request = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": "KEIBA-LAB-licensed-data-consumer/1.0",
        **({"Authorization": f"Bearer {token}"} if token else {}),
    })
    opener = urllib.request.build_opener(BlockRedirect)
    with opener.open(request, timeout=20) as response:
        data = response.read(MAX_FEED_BYTES + 1)
    if len(data) > MAX_FEED_BYTES:
        raise ValueError("Feed is too large")
    return json.loads(data.decode("utf-8-sig"))


def not_configured():
    return {
        "schema_version": 1, "scope": "JRA中央競馬のみ", "status": "not_configured",
        "source": "許諾済みデータ配信先が未設定",
        "method": "取得先と公開利用許諾の設定が必要です。実データは未取得です。",
        "updated_at": None, "races": [], "drafts": [], "schedule": [],
        "summary": {"locked": 0, "drafts": 0, "settled": 0, "pending": 0,
                    "win_hits": 0, "trio_hits": 0, "trifecta_hits": 0},
    }


def selftest():
    now = dt.datetime(2099, 1, 1, 9, 0, tzinfo=JST)
    race = {"date": "2099-01-01", "venue": "東京", "race_no": 11,
            "start_at": "2099-01-01T10:00:00+09:00",
            "horses": [{"no": n, "name": f"架空{n}", "odds": 2.0 * n} for n in range(1, 8)]}
    source = {"races": [race], "results": []}
    first = update(source, now=now)
    assert len(first["drafts"]) == 1 and len(first["races"]) == 0
    before = update(source, first, now + dt.timedelta(minutes=43))
    assert before["drafts"][0]["predicted_at"] != first["drafts"][0]["predicted_at"]
    after = update(source, before, now + dt.timedelta(minutes=50))
    assert len(after["races"]) == 1 and len(after["drafts"]) == 0
    assert after["races"][0]["predicted_at"] == before["drafts"][0]["predicted_at"]
    assert after["races"][0]["locked_at"] == before["drafts"][0]["predicted_at"]
    missed = update(source, now=now + dt.timedelta(minutes=50))
    assert not missed["races"] and not missed["drafts"], "No retrospective forecasts"
    results = {"races": [], "results": [{**race, "confirmed": True, "result": [1, 2, 3],
                                          "payouts": {"win": 300}}]}
    final = update(results, after, now + dt.timedelta(hours=2))
    assert final["races"][0]["result"] == [1, 2, 3]
    assert final["races"][0]["payouts"] == {"win": 300}
    unconfirmed = update({"races": [], "results": [{**race, "confirmed": False,
                                                   "result": [4, 5, 6]}]}, after, now + dt.timedelta(hours=2))
    assert not unconfirmed["races"][0].get("result")
    assert len(final["races"][0]["trio_tickets"]) == 10
    assert 6 <= len(final["races"][0]["tickets"]) <= 36
    assert not_configured()["races"] == []
    print("PASS: licensed JRA provider guard, 15-minute freeze, no retroactive prediction, confirmed results only")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    feed_url = os.getenv("JRA_LICENSED_FEED_URL", "").strip()
    permitted = os.getenv("JRA_PUBLICATION_RIGHTS_CONFIRMED", "").strip().lower() == "true"
    if not feed_url or not permitted:
        data = not_configured()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != content:
            OUT.write_text(content, encoding="utf-8")
        print("JRA auto feed not activated: licensed feed and publication permission are required")
        return
    auth = os.getenv("JRA_LICENSED_FEED_TOKEN", "")
    prior = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    payload = fetch_json(feed_url, auth)
    results_url = os.getenv("JRA_LICENSED_RESULTS_URL", "").strip()
    if results_url:
        response = fetch_json(results_url, auth)
        if not isinstance(response, dict) or not isinstance(response.get("results"), list):
            raise ValueError("Results endpoint must return {results:[...]}")
        payload["results"] = response["results"]
    updated = update(payload, prior)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
    OUT.write_text(content, encoding="utf-8")
    print("JRA forecasts:", updated["summary"])


if __name__ == "__main__":
    main()
