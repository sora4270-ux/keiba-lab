#!/usr/bin/env python3
"""Read-only daily reconciliation of saved forecasts and official race CSVs."""
import argparse
from collections import Counter, defaultdict
import datetime as dt
import json
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from update_nar import BASE_URL, fetch_daily_zip, load_zip_tables, row_key, cell, as_int
from audit_nar_daily_axes import analyze as daily_axes
from audit_nar_confidence_wide import grade_from_frozen
from backtest_nar_stake_allocation import official_market_index, official_settlement
from nar_official_status import OfficialStatusLookup

STATUS = {"取消":"withdrawn", "出走取消":"withdrawn", "除外":"excluded",
          "競走除外":"excluded", "中止":"did_not_finish", "競走中止":"did_not_finish"}


def summarize(records, tables, day, lookup=None):
    audit = daily_axes(records, day)
    eligible = {r["id"]: r for r in audit["race_details"]}
    races = defaultdict(list)
    horses = defaultdict(list)
    for kind, target in (("racelist", races), ("horselist", horses)):
        for item in tables.get(kind, []):
            key = row_key(item, ())
            if key and key[1] == day.replace("-", ""):
                target[key].append(item)
    market = official_market_index(tables)
    coverage, status_counts = Counter(), Counter()
    groups, confidence = defaultdict(Counter), defaultdict(Counter)
    details = []
    by_id = {r["id"]: r for r in records if isinstance(r, dict) and r.get("id") in eligible}
    for ident, d in eligible.items():
        r = by_id[ident]
        key = (r.get("venue"), day.replace("-", ""), r.get("race_no"))
        detail = {"id": ident, "venue": key[0], "race_no": key[2]}
        rr = races.get(key, [])
        ground = "unknown"
        if len(rr) == 1:
            raw, fields = rr[0]
            value = cell(raw, fields, "馬場", "馬場状態", idx=25)
            if value in ("良", "稍重", "重", "不良"):
                ground = value
            detail["weather"] = cell(raw, fields, "天候", idx=24) or None
            detail["distance_m"] = as_int(cell(raw, fields, "距離", idx=23))
            coverage["unique_racelist"] += 1
        detail["official_ground"] = ground
        if ground != "unknown":
            coverage["known_ground"] += 1
        payout, error = official_settlement(r, market)
        detail["official_payout_status"] = error or "verified"
        coverage["payout_" + (error or "verified")] += 1
        if payout:
            stored = r.get("payouts") or {}
            detail["stored_payout_comparison"] = {
                k: ("missing" if k not in stored else "match" if stored[k] == v else "mismatch")
                for k, v in payout["payouts"].items()}
            for k, v in detail["stored_payout_comparison"].items():
                coverage[f"stored_{k}_{v}"] += 1
        rows = defaultdict(list)
        for raw, fields in horses.get(key, []):
            no = as_int(cell(raw, fields, "馬番", idx=5))
            if no is not None and 1 <= no <= 30:
                rows[no].append(cell(raw, fields, "着順", idx=31))
        statuses = {}
        for no in d["ranking"]:
            values = rows.get(no, [])
            if len(values) != 1:
                label = "missing_or_duplicate"
            else:
                rank = as_int(values[0])
                label = STATUS.get(values[0], "finished" if rank and rank > 0 else "unknown")
            statuses[str(no)] = label
        wanted = {int(n) for n, v in statuses.items() if v in ("unknown", "missing_or_duplicate")}
        if wanted and lookup is not None:
            evidence, lookup_status = lookup(key[0], day, key[2], wanted)
            detail["status_lookup"] = lookup_status
            detail["status_evidence"] = {}
            for n, item in evidence.items():
                if n in wanted and item.get("status") in STATUS.values():
                    statuses[str(n)] = item["status"]
                    detail["status_evidence"][str(n)] = item
            coverage["lookup_" + lookup_status] += 1
        status_counts.update(statuses.values())
        detail["official_runner_status"] = statuses
        detail["unresolved_runner_numbers"] = [int(n) for n,v in statuses.items()
                                                if v in ("unknown","missing_or_duplicate")]
        # These labels are not actual tickets or a verified refund ledger.
        detail["refund_review_required"] = any(x in ("withdrawn", "excluded", "unknown", "missing_or_duplicate") for x in statuses.values())
        if detail["refund_review_required"]:
            coverage["refund_review_required"] += 1
        try:
            grade, _ = grade_from_frozen(r)
        except (TypeError, ValueError, AttributeError, KeyError):
            grade = None
        detail["reconstructed_confidence"] = grade or "unknown"
        # Only independently reconciled results enter condition/confidence statistics.
        if payout:
            for c in (groups[(str(key[0]), ground)], confidence[grade or "unknown"]):
                c["races"] += 1
                c["top1_win"] += int(d["top1_win"])
                c["top1_in_podium"] += int(d["top1_in_podium"])
        details.append(detail)
    return {"date":day, "saved_eligible":len(eligible), "coverage":dict(coverage),
            "runner_status_counts":dict(status_counts),
            "venue_ground":[{"venue":v,"ground":g,**dict(c)} for (v,g),c in sorted(groups.items())],
            "confidence":{g:dict(c) for g,c in sorted(confidence.items())},
            "race_details":details,
            "notes":["Only explicit CSV or official result-page status text is interpreted; missing or numeric zero remains unknown unless corroborated.",
                     "Condition is the official result-time condition, not proven pre-race availability.",
                     "No real wagers, refund amounts, or ROI are inferred. Confidence is reconstructed from frozen data."]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--input", type=Path, default=Path("data/auto/nar_predictions.json"))
    p.add_argument("--output", type=Path, default=Path("nar-official-daily.json"))
    p.add_argument("--official-zip", type=Path)
    a = p.parse_args()
    day = dt.date.fromisoformat(a.date)
    today = dt.datetime.now(ZoneInfo("Asia/Tokyo")).date()
    url = BASE_URL if day == today else BASE_URL.split("?")[0] + "?" + urlencode(
        {"type":"monthly","k_year":day.year,"k_month":f"{day.month:02d}"})
    tables = load_zip_tables(a.official_zip.read_bytes() if a.official_zip else fetch_daily_zip(url))
    report = summarize(json.loads(a.input.read_text(encoding="utf-8"))["races"], tables, a.date,
                       None if a.official_zip else OfficialStatusLookup())
    report["source"] = "supplied_zip" if a.official_zip else url
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "race_details"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
