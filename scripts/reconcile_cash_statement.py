#!/usr/bin/env python3
"""Offline accounting for actual transaction statements; never infer cash from forecasts."""
import argparse
from collections import Counter, defaultdict
from datetime import date
import json
from pathlib import Path


def reconcile(rows, day):
    date.fromisoformat(day)
    if not isinstance(rows, list):
        raise ValueError("statement must be a list")
    groups = defaultdict(list)
    excluded = Counter()
    for r in rows:
        if not isinstance(r, dict):
            excluded["invalid_record"] += 1
            continue
        if r.get("date") != day:
            continue
        ident = r.get("transaction_id")
        if not isinstance(ident, str) or not ident.strip():
            excluded["missing_transaction_id"] += 1
            continue
        groups[ident].append(r)
    totals = Counter()
    for group in groups.values():
        if any(r != group[0] for r in group[1:]):
            excluded["conflicting_transaction"] += len(group)
            continue
        excluded["identical_duplicate"] += len(group) - 1
        r = group[0]
        if r.get("status") != "settled":
            excluded["not_settled"] += 1
            continue
        stake, payout, refund = (r.get(k) for k in ("purchase_yen", "payout_yen", "refund_yen"))
        if (any(type(v) is not int or v < 0 for v in (stake,payout,refund))
                or not stake or refund > stake
                or (refund == stake and payout != 0)):
            excluded["invalid_or_missing_amount"] += 1
            continue
        if not isinstance(r.get("statement_reference"), str) or not r["statement_reference"].strip():
            excluded["missing_statement_reference"] += 1
            continue
        totals["transactions"] += 1
        totals["purchase_yen"] += stake
        totals["payout_yen"] += payout
        totals["refund_yen"] += refund
    n = totals["transactions"]
    incomplete = any(v for k,v in excluded.items() if k != "identical_duplicate")
    return {"date":day, "status":("no_confirmed_records" if not n else
            "partial_statement" if incomplete else "statement_rows_reconciled"),
            "confirmed_transactions":n,
            "purchase_yen":totals["purchase_yen"] if n else None,
            "payout_yen":totals["payout_yen"] if n else None,
            "refund_yen":totals["refund_yen"] if n else None,
            "net_yen":totals["payout_yen"] + totals["refund_yen"] - totals["purchase_yen"] if n else None,
            "excluded":dict(sorted((k,v) for k,v in excluded.items() if v)),
            "notes":["Only supplied settled transaction amounts are counted.",
                     "A statement reference is not independent authentication.",
                     "Partial totals are not the full daily balance; no records means unknown, not zero."]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--date", required=True)
    a = p.parse_args()
    print(json.dumps(reconcile(json.loads(a.input.read_text(encoding="utf-8")), a.date),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
