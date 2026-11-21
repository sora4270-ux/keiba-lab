#!/usr/bin/env python3
"""Audit immutable NAR records without treating after-race information as a pre-race signal."""
import argparse
import collections
import datetime as dt
import json
from pathlib import Path


def audit(records):
    out = {"total": len(records), "settled": 0, "prelock_trifecta_quotes": 0,
           "missing_prelock_quotes": 0, "old_comparable": {"races": 0, "stake_yen": 0,
           "return_yen": 0, "hits": 0}, "new_shadow": {"recorded": 0, "candidate": 0,
           "settled_comparable": 0}, "by_venue": {}, "by_grade": {}, "by_bet_type": {}, "banei": {}, "other": {}, "risk": {"old_max_drawdown_yen": 0, "shadow_max_drawdown_yen": 0}}
    groups = {"banei": collections.Counter(), "other": collections.Counter()}
    old_equity = shadow_equity = old_peak = shadow_peak = 0
    for r in sorted(records, key=lambda x: (str(x.get("date", "")), str(x.get("start_at", "")), str(x.get("id", "")))):
        result = r.get("result")
        if not isinstance(result, list) or len(result) != 3 or len(set(result)) != 3:
            continue
        out["settled"] += 1
        venue = str(r.get("venue", ""))
        kind = "banei" if "帯広" in venue or "ばんえい" in venue else "other"
        group = groups[kind]
        group["races"] += 1
        ranking = r.get("ranking") or []
        if ranking:
            group["top1_wins"] += int(ranking[0].get("no") == result[0])
            group["top1_podium"] += int(ranking[0].get("no") in result)
        shadow = r.get("trifecta_value_shadow")
        if isinstance(shadow, dict):
            out["new_shadow"]["recorded"] += 1
            if shadow.get("status") == "candidate":
                out["new_shadow"]["candidate"] += 1
            if shadow.get("status") == "skip":
                out["new_shadow"]["skipped"] = out["new_shadow"].get("skipped", 0) + 1
        snap = r.get("trifecta_market_at_lock")
        try:
            observed = dt.datetime.fromisoformat(snap["updated_at"])
            locked = dt.datetime.fromisoformat(r.get("locked_at") or r["predicted_at"])
            cutoff = dt.datetime.fromisoformat(r["cutoff_at"])
            valid = (all(t.tzinfo is not None for t in (observed, locked, cutoff))
                     and dt.timedelta(0) <= locked-observed <= dt.timedelta(minutes=15)
                     and locked < cutoff)
        except (KeyError, ValueError, TypeError):
            valid = False
        if not valid:
            out["missing_prelock_quotes"] += 1
            continue
        out["prelock_trifecta_quotes"] += 1
        tickets = r.get("tickets") or []
        payout = (r.get("payouts") or {}).get("trifecta")
        if not isinstance(payout, int) or payout < 0 or not tickets:
            continue
        hit = any(t == result for t in tickets)
        stake = len(tickets)*100
        ret = payout if hit else 0
        old = out["old_comparable"]
        old["races"] += 1
        old["stake_yen"] += stake
        old["return_yen"] += ret
        old["hits"] += int(hit)
        v = out["by_venue"].setdefault(venue, {"races": 0, "stake_yen": 0, "return_yen": 0})
        v["races"] += 1
        v["stake_yen"] += stake
        v["return_yen"] += ret
        grade = str(r.get("confidence") or r.get("grade") or "unknown")
        g = out["by_grade"].setdefault(grade, {"races": 0, "stake_yen": 0, "return_yen": 0})
        g["races"] += 1
        g["stake_yen"] += stake
        g["return_yen"] += ret
        old_equity += ret - stake
        old_peak = max(old_peak, old_equity)
        out["risk"]["old_max_drawdown_yen"] = max(out["risk"]["old_max_drawdown_yen"], old_peak-old_equity)
        if isinstance(shadow, dict) and shadow.get("status") in ("skip", "candidate"):
            out["new_shadow"]["settled_comparable"] += 1
            new = out["new_shadow"]
            new["stake_yen"] = new.get("stake_yen", 0)
            new["return_yen"] = new.get("return_yen", 0)
            new["hits"] = new.get("hits", 0)
            if shadow.get("status") == "candidate":
                shadow_tickets = shadow.get("tickets") or []
                shadow_stake = shadow.get("stake_yen")
                if (isinstance(shadow_stake, int) and shadow_stake == 100 * len(shadow_tickets)
                        and 0 < len(shadow_tickets) <= 6
                        and all(isinstance(t, list) and len(t) == 3 for t in shadow_tickets)):
                    shadow_hit = any(t == result for t in shadow_tickets)
                    new["stake_yen"] += shadow_stake
                    new["return_yen"] += payout if shadow_hit else 0
                    new["hits"] += int(shadow_hit)
                    new["evaluated_candidates"] = new.get("evaluated_candidates", 0) + 1
                    shadow_equity += (payout if shadow_hit else 0)-shadow_stake
                    shadow_peak = max(shadow_peak, shadow_equity)
                    out["risk"]["shadow_max_drawdown_yen"] = max(out["risk"]["shadow_max_drawdown_yen"], shadow_peak-shadow_equity)

    for name, group in groups.items():
        n = group["races"]
        out[name] = {"races": n, "top1_wins": group["top1_wins"],
                     "top1_podium": group["top1_podium"],
                     "win_rate_percent": round(group["top1_wins"]*100/n, 2) if n else None,
                     "podium_rate_percent": round(group["top1_podium"]*100/n, 2) if n else None}
    new = out["new_shadow"]
    new["roi_percent"] = (round(new.get("return_yen", 0)*100/new["stake_yen"], 2)
                          if new.get("stake_yen", 0) else None)
    new["profit_yen"] = new.get("return_yen", 0)-new.get("stake_yen", 0)
    old = out["old_comparable"]
    old["roi_percent"] = round(old["return_yen"]*100/old["stake_yen"], 2) if old["stake_yen"] else None
    old["profit_yen"] = old["return_yen"]-old["stake_yen"]
    for row in list(out["by_venue"].values()) + list(out["by_grade"].values()):
        row["roi_percent"] = round(row["return_yen"]*100/row["stake_yen"], 2) if row["stake_yen"] else None
    out["by_bet_type"]["trifecta"] = {"old": dict(old), "shadow": dict(new)}
    out["decision"] = ("insufficient_new_shadow_data" if out["new_shadow"].get("evaluated_candidates", 0) < 100
                       else "review_out_of_sample_results_before_any_adoption")
    out["note"] = ("Old and new strategies are hypothetical 100-yen-per-ticket. New strategy requires settled "
                   "immutable pre-race shadow records; no improvement claim is valid without a sufficient prospective sample. "
                   "Banei results belong to the prior model, not the new provisional baseline.")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/auto/nar_predictions.json")
    parser.add_argument("--output", default="data/auto/trifecta_banei_audit.json")
    args = parser.parse_args()
    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    report = audit(raw["races"])
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2)+"
", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
