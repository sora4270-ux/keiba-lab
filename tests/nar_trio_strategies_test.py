import copy
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_nar_trio_strategies import analyze, strategies


def race(race_id, result, ranking=None):
    return {
        "id": race_id, "date": "2026-11-22",
        "start_at": "2026-11-22T20:00:00+09:00",
        "cutoff_at": "2026-11-22T19:45:00+09:00",
        "locked_at": "2026-11-22T19:44:00+09:00",
        "predicted_at": "2026-11-22T19:43:00+09:00",
        "ranking": [{"no": n} for n in (ranking or [1,2,3,4,5,6,7])],
        "result": result,
    }


class TrioStrategiesTest(unittest.TestCase):
    def test_ex_ante_ticket_sets_and_fixed_budget(self):
        picks = strategies([1,2,3,4,5,6,7])
        self.assertEqual({k: len(v) for k,v in picks.items()},
                         {"axis1":10, "axis2":5, "box5":10})
        self.assertEqual(len(set(picks["axis1"])), 10)
        self.assertEqual(len(set(picks["axis2"])), 5)
        self.assertEqual(len(set(picks["box5"])), 10)
        self.assertIn((1,2,6), picks["axis1"])
        self.assertNotIn((1,2,7), picks["axis1"])
        self.assertIn((1,2,7), picks["axis2"])
        self.assertNotIn((1,3,4), picks["axis2"])

    def test_paired_hit_and_surprise_in_denominator(self):
        rows = [race("axis2_only",[1,2,7]), race("box_only",[3,4,5]),
                race("all",[1,2,3]), race("surprise",[1,2,9])]
        frozen = copy.deepcopy(rows)
        out = analyze(rows, "2026-11-22")
        self.assertEqual(rows, frozen)
        self.assertEqual(out["eligible_races"], 4)
        self.assertEqual(out["strategies"]["axis1"]["hits"], 1)
        self.assertEqual(out["strategies"]["axis2"]["hits"], 2)
        self.assertEqual(out["strategies"]["box5"]["hits"], 2)
        for item in out["strategies"].values():
            self.assertEqual(item["hypothetical_total_stake_yen"], 4000)
            self.assertEqual(item["tickets"] * item["yen_per_ticket"], 1000)

    def test_official_roi_uses_only_verified_common_cohort(self):
        rows = [race("verified", [1,2,3]), race("unverified", [1,2,3])]
        def settlement(row, market):
            if row["id"] == "verified":
                return {"payouts": {"trio": 1500}}, None
            return None, "official_row_missing_or_dead_heat"
        with patch("audit_nar_trio_strategies.official_market_index", return_value={}), \\
             patch("audit_nar_trio_strategies.official_settlement", side_effect=settlement):
            out = analyze(rows, "2026-11-22", {"payback":[]})
        self.assertEqual(out["eligible_races"], 2)
        official = out["official_settlement"]
        self.assertEqual(official["verified_races"], 1)
        self.assertEqual(official["excluded"]["official_row_missing_or_dead_heat"], 1)
        self.assertEqual(official["per_strategy"]["axis1"]["stake_yen"], 1000)
        self.assertEqual(official["per_strategy"]["axis1"]["payout_yen"], 1500)
        self.assertEqual(official["per_strategy"]["axis2"]["payout_yen"], 3000)
        self.assertEqual(official["per_strategy"]["box5"]["roi_percent"], 150.0)

    def test_no_official_zip_does_not_invent_roi(self):
        out = analyze([race("a", [1,2,3])])
        self.assertEqual(out["official_settlement"]["verified_races"], 0)
        self.assertIsNone(out["official_settlement"]["per_strategy"]["axis1"]["roi_percent"])

    def test_exclusions(self):
        good = race("good",[1,2,3])
        short = race("short",[1,2,3], [1,2,3,4,5])
        late = {**good, "id":"late", "locked_at":"2026-11-22T19:46:00+09:00"}
        tie = {**good, "id":"tie", "result_alternatives":[[1,2,3],[2,1,3]]}
        out = analyze([good,good,short,late,tie], "2026-11-22")
        self.assertEqual(out["eligible_races"], 1)
        self.assertEqual(out["excluded"]["duplicate_or_missing_id"], 1)
        self.assertEqual(out["excluded"]["fewer_than_seven_ranked"], 1)
        self.assertEqual(out["excluded"]["unverifiable_lock"], 1)
        self.assertEqual(out["excluded"]["draft_or_dead_heat"], 1)


if __name__ == "__main__":
    unittest.main()
