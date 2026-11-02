#!/usr/bin/env python3
"""KEIBA LAB NAR scheduled forecasts. Requires only Python standard library.
Uses NAR's public daily CSV download for *derived forecasts*, not raw-data mirroring.
Initial model is an explicitly untrained, shrinkage-based form heuristic.
"""
import csv
import datetime as dt
import io
import itertools
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
DATA_PATH = Path("data/auto/nar_predictions.json")
MAX_DOWNLOAD = 30 * 1024 * 1024
MAX_FILE = 20 * 1024 * 1024
TRACK_FIELDS = ("競馬場", "日付", "レース番号")
BET_TYPES = ("win", "quinella", "exacta", "trio", "trifecta")


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


def forecast(race, timestamp):
    horses = race["horses"]
    raw_scores = []
    for h in horses:
        s = (
            .45 * shrink_rate(h["overall"]) +
            .25 * shrink_rate(h["distance"]) +
            .20 * shrink_rate(h["venue"]) +
            .10 * shrink_rate(h["jockey"])
        )
        raw_scores.append(s)
    high = max(raw_scores)
    weights = [math.exp(7 * (s - high)) for s in raw_scores]
    denom = sum(weights)
    probs = [w / denom for w in weights]
    ranked = sorted(range(len(horses)), key=lambda i: (-probs[i], horses[i]["no"]))
    pick = [{"no": horses[i]["no"], "name": horses[i]["name"],
             "win_probability": round(probs[i], 4)} for i in ranked[:3]]
    # Plackett-Luce approximation. Top 12 ordered triple tickets, NOT guaranteed hit.
    tickets = []
    for i, j, k in itertools.permutations(range(len(horses)), 3):
        p = probs[i] * probs[j] / max(1e-12, 1 - probs[i])
        p *= probs[k] / max(1e-12, 1 - probs[i] - probs[j])
        tickets.append((p, [horses[i]["no"], horses[j]["no"], horses[k]["no"]]))
    tickets.sort(key=lambda x: -x[0])
    return {
        "id": race["id"], "date": race["date"], "venue": race["venue"],
        "race_no": race["race_no"], "name": race["name"],
        "start_at": race["start"].isoformat(timespec="minutes"),
        "predicted_at": timestamp.isoformat(timespec="seconds"),
        "model": "form_heuristic_v1_untrained",
        "top3": pick,
        "tickets": [t for _, t in tickets[:12]],
        "result": None, "settled_at": None, "hits": None
    }


def settled_order(horses):
    ranked = {i: [] for i in (1, 2, 3)}
    for horse in horses:
        if horse["rank"] in ranked:
            ranked[horse["rank"]].append(horse["no"])
    # Skip dead heats / partial or conflicting provisional results.
    if any(len(ranked[n]) != 1 for n in (1, 2, 3)):
        return None
    return [ranked[n][0] for n in (1, 2, 3)]


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
        "trifecta": result in pred["tickets"]
    }
    return True


def summary(predictions):
    valid = [x for x in predictions if isinstance(x.get("hits"), dict)]
    rate = lambda key: round(sum(x["hits"][key] is True for x in valid) / len(valid) * 100, 1) if valid else None
    return {
        "predicted": len(predictions), "settled": len(valid),
        "pending": len(predictions) - len(valid),
        "win": rate("win"), "quinella": rate("quinella"),
        "exacta": rate("exacta"), "trio": rate("trio"),
        "trifecta": rate("trifecta"),
        "note": "的中率の分母は発走前に保存し、1〜3着を後日照合できたレースのみ。三連単は上位候補12点。"
    }


def update_data(races, now, previous):
    old = previous.get("races", [])
    if not isinstance(old, list):
        raise ValueError("保存された予想履歴の形式が不正です")
    entries = {p["id"]: p for p in old if isinstance(p, dict) and p.get("id")}
    added = 0
    settled = 0
    for race in races:
        ident = race["id"]
        if ident not in entries:
            # A forecast made after the race or shortly before off is not valid.
            if now >= race["start"] - dt.timedelta(minutes=10):
                continue
            # Strictly exclude races that already report results.
            if any(h["rank"] in (1, 2, 3) for h in race["horses"]):
                continue
            entries[ident] = forecast(race, now)
            added += 1
        else:
            order = settled_order(race["horses"])
            if order and settle(entries[ident], order, now):
                settled += 1
    # Prevent unbounded site data growth. Keep latest 5000 independently timestamped forecasts.
    predictions = sorted(entries.values(), key=lambda x: (x["date"], x["start_at"]), reverse=True)[:5000]
    return {
        "schema_version": 1, "scope": "NAR地方競馬のみ（中央JRAは対象外）",
        "source": "NAR公式CSVデータ（分析結果のみ表示）",
        "method": "過去成績の縮約率から計算する未学習ヒューリスティック。的中保証なし。",
        "updated_at": now.isoformat(timespec="seconds") if added or settled or not previous else previous.get("updated_at"),
        "races": predictions, "summary": summary(predictions)
    }, added, settled


def fetch_daily_zip():
    request = urllib.request.Request(
        BASE_URL,
        headers={"User-Agent": "KEIBA-LAB/3.3 (personal race form analysis)", "Accept": "application/zip"}
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        data = response.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise ValueError("公式ZIPが容量上限を超えています")
    return data


def selftest():
    now = dt.datetime(2026, 11, 2, 9, 0, tzinfo=JST)
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
    out, added, settled_count = update_data(races, now, {})
    assert added == 1 and settled_count == 0 and out["summary"]["settled"] == 0
    pre = out["races"][0]
    assert len(pre["tickets"]) == 12 and abs(sum(x["win_probability"] for x in pre["top3"])) < 1.001
    for i, (_, _) in enumerate(horse_template):
        horse_template[i][0][31] = str(i+1) if i < 3 else ""
    races = parse_races({"racelist": [(row, {})], "horselist": horse_template})
    late = dt.datetime(2026, 11, 2, 16, 0, tzinfo=JST)
    out2, a, s = update_data(races, late, out)
    assert a == 0 and s == 1 and out2["summary"]["settled"] == 1
    out3, a, s = update_data(races, late, out2)
    assert a == 0 and s == 0 and out3["races"][0]["predicted_at"] == pre["predicted_at"]
    assert update_data(races, late, {})[1] == 0
    print("PASS: prediction snapshot before off; settle only after; no duplicates; no late insertion")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    now = dt.datetime.now(JST)
    source_bytes = fetch_daily_zip()
    tables = load_zip_tables(source_bytes)
    races = parse_races(tables)
    if not races:
        raise RuntimeError("有効なレースがありません。CSV形式か配信状況を確認してください")
    previous = json.loads(DATA_PATH.read_text(encoding="utf-8")) if DATA_PATH.exists() else {}
    out, added, settled_count = update_data(races, now, previous)
    if added or settled_count or not DATA_PATH.exists():
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        DATA_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"NAR races: {len(races)}, newly predicted: {added}, newly settled: {settled_count}; total: {out['summary']['predicted']}, settled: {out['summary']['settled']}")


if __name__ == "__main__":
    main()
