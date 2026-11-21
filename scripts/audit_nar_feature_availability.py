#!/usr/bin/env python3
"""Report NAR CSV feature availability, not proof of pre-race capture.

Historical same-race corner order and final track condition must NEVER be
fed into predictions for that race. Use older races only for style estimates.
"""
import argparse
import collections
import json
from pathlib import Path
from urllib.parse import urlencode

from update_nar import BASE_URL, cell, fetch_daily_zip, load_zip_tables, row_key


def coverage(tables):
    races = {}
    for item in tables.get("racelist", []):
        key = row_key(item, ())
        if not key:
            continue
        raw, fields = item
        track = cell(raw, fields, "馬場", idx=25).strip()
        corners = [cell(raw, fields, f"コーナー通過順{i}", idx=58+i).strip()
                   for i in range(1, 9)]
        races[key] = {
            "track": bool(track),
            "corners": any(corners),
            "is_banei": "帯広" in key[0] or "ばんえい" in key[0],
        }
    horse_rows, weight_rows, banei_weight_rows = 0, 0, 0
    for item in tables.get("horselist", []):
        key = row_key(item, ())
        if key not in races:
            continue
        raw, fields = item
        horse_rows += 1
        raw_weight = cell(raw, fields, "負担重量", idx=16).strip()
        if raw_weight:
            try:
                value = float(raw_weight)
                if 0 < value <= 1200:
                    weight_rows += 1
                    if races[key]["is_banei"]:
                        banei_weight_rows += 1
            except ValueError:
                pass
    return {
        "source": "NAR official race-data CSV",
        "races": len(races),
        "race_track_condition_present": sum(x["track"] for x in races.values()),
        "past_race_corner_order_present": sum(x["corners"] for x in races.values()),
        "runner_rows": horse_rows,
        "carried_weight_present": weight_rows,
        "banei_carried_weight_present": banei_weight_rows,
        "direct_running_style_field": False,
        "prelock_track_condition_capture_verified": False,
        "prelock_weight_capture_verified": False,
        "prelock_running_style_capture_verified": False,
        "status": "archive_field_coverage_only",
        "notes": [
            "Running style is not an explicit NAR CSV field; derive from prior races' corner order only.",
            "Monthly archives cannot attest to the track/weight value observed at T-15.",
            "Banei weight is loading weight, not interchangeable with flat-racing jockey weight.",
            "Do not backfill archived results into an immutable pre-race feature snapshot.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--zip", type=Path, help="Offline official race-data ZIP; if absent, download monthly data")
    p.add_argument("--month", default="2026-11", help="YYYY-MM for optional live probe")
    p.add_argument("--output", type=Path, default=Path("nar-feature-availability.json"))
    a = p.parse_args()
    if a.zip:
        raw = a.zip.read_bytes()
    else:
        year, month = a.month.split("-")
        if len(year) != 4 or len(month) != 2 or not year.isdigit() or not month.isdigit() or not 1 <= int(month) <= 12:
            p.error("month must be YYYY-MM")
        url = BASE_URL.split("?", 1)[0] + "?" + urlencode({"type": "monthly", "k_year": int(year), "k_month": month})
        raw = fetch_daily_zip(url)
    report = coverage(load_zip_tables(raw))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if report["races"] == 0:
        raise SystemExit("No race rows; availability not verified")


if __name__ == "__main__":
    main()
