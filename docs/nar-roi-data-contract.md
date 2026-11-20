# NAR ROI verification: data contract

The historical replay JSON **does not contain official payouts or pre-decision odds**. It cannot calculate ROI by itself.

## Accepted CSV columns

`race_id,horse_no,grade,bet_type,stake_yen,official_payout_per_100_yen,decision_time,odds_observed_time,odds,official_result_verified`

- `race_id`: stable venue/date/race identifier; `horse_no`: selected horse number.
- `grade`: S/A/B/C assigned **before** the race using frozen thresholds from an earlier period. Never recompute from the outcome.
- `bet_type`: `win` or `place`. For place, use the **actual official payout for that horse**, not a midpoint of an odds range.
- `stake_yen`: positive multiple of ¥100. `official_payout_per_100_yen`: official payout per ¥100 for the selected horse, or 0 if the bet verifiably lost.
- `decision_time` and `odds_observed_time`: timezone-aware ISO-8601 timestamps; odds must have been observed no later than the decision.
- `official_result_verified`: `true` only after a human or trusted independent process has checked the official result and payout. The script **does not authenticate** this assertion.
- Refunded, canceled, dead-heat, and special-settlement bets need separate audited handling. **Do not include them** in the present CSV.

## Run locally

```bash
python -m unittest discover -s tests -p 'nar_roi_test.py'
python scripts/evaluate_nar_roi.py --input verified-bets.csv --output nar-roi-report.json
```

**No real CSV is bundled**. Do not publish a report as a real return-on-investment result until genuine historical decision-time snapshots and official payouts are linked by race and horse, including losses. A winners-only dataset would severely bias the return.

The ROI report includes accepted and rejected counts. ROI is payout / stake × 100 (100% is break-even before any other costs). This is research-only, not a staking instruction.
