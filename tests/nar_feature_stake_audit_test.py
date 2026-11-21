import datetime as dt
import itertools
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_nar_feature_availability import coverage
from backtest_nar_stake_allocation import backtest, eligible, settle_one, PLANS


def fake(day="2026-11-19", result=None):
    rank = list(range(1, 7))
    actual = result or [1, 2, 3]
    return {
        "id": "nar-"+day.replace("-", "")+"-大井-01", "date": day, "venue": "大井",
        "start_at": day+"T12:00+09:00", "cutoff_at": day+"T11:45+09:00",
        "locked_at": day+"T11:43+09:00", "predicted_at": day+"T11:42+09:00",
        "result": actual, "ranking": [{"no": n} for n in rank],
        "trio_tickets": [list(t) for t in itertools.combinations(rank[:5], 3)],
        "tickets": [list(t) for t in itertools.permutations(rank[:5], 3)],
        "payouts": {"win": 500, "trio": 1400, "trifecta": 8500},
        "wide_payouts": {"1-2": 220, "1-3": 330, "2-3": 450},
    }


class OfficialFeatureTests(unittest.TestCase):
    def test_official_archive_fields_do_not_certify_t15(self):
        venue, day, race = "大井", "20261119", "1"
        races = [([venue,day,race]+[""]*22+["重"]+[""]*33+["1,2,3"], {})]
        horses = [([venue,day,race]+[""]*13+["57"], {})]
        got = coverage({"racelist": races, "horselist": horses})
        self.assertEqual(got["race_track_condition_present"], 1)
        self.assertEqual(got["carried_weight_present"], 1)
        self.assertFalse(got["prelock_track_condition_capture_verified"])
        self.assertFalse(got["direct_running_style_field"])
    def test_banei_weight_is_separate(self):
        raw = ["帯広ば","20261119","1"]+[""]*22+["2.3"]
        horse = ["帯広ば","20261119","1"]+[""]*13+["650"]
        got = coverage({"racelist":[(raw,{})],"horselist":[(horse,{})]})
        self.assertEqual(got["banei_carried_weight_present"],1)


class AllocationTests(unittest.TestCase):
    def test_fixed_budget_and_same_race_cohort(self):
        one = fake()
        two = fake("2026-11-20", [3, 2, 1])
        two["wide_payouts"] = {"1-2": 220, "1-3": 330, "2-3": 450}
        report = backtest([one, two])
        self.assertEqual(report["eligible_races"], 2)
        for name, values in report["plans"].items():
            self.assertEqual(values["all"]["races"],2)
            self.assertEqual(values["all"]["stake_yen"],10000)
        self.assertEqual(report["holdout_dates"],1)
        self.assertEqual(report["plans"]["no_trifecta"]["all"]["by_type"]["trifecta"]["stake_yen"],0)
    def test_late_and_naive_and_missing_payout_excluded(self):
        late = fake()
        late["locked_at"]=late["start_at"]
        self.assertEqual(eligible(late)[1], "late_or_inconsistent_lock")
        naive = fake()
        naive["predicted_at"]="2026-11-19T11:42"
        self.assertEqual(eligible(naive)[1], "naive_timestamp")
        missing = fake()
        del missing["wide_payouts"]["2-3"]
        self.assertEqual(eligible(missing)[1], "missing_wide_market")
    def test_dead_heat_and_duplicate_tickets_excluded(self):
        tied = fake()
        tied["result_alternatives"]=[[1,2,3],[1,2,4]]
        self.assertEqual(eligible(tied)[1], "unsettled_or_dead_heat")
        duplicates = fake()
        duplicates["tickets"] = [[1,2,3],[1,2,3]]
        self.assertEqual(eligible(duplicates)[1], "duplicate_tickets")
    def test_no_outcome_based_ticket_choice(self):
        a=fake()
        b=fake(result=[3,2,1])
        info_a,_=eligible(a);info_b,_=eligible(b)
        self.assertEqual(info_a["tickets"],info_b["tickets"])
        left=settle_one(info_a, PLANS["balanced"])
        right=settle_one(info_b, PLANS["balanced"])
        self.assertEqual(left[0],5000)
        self.assertEqual(right[0],5000)
        self.assertNotEqual(left[1],right[1])
    def test_no_false_profit_when_zero_valid(self):
        report=backtest([{"status":"draft"}])
        self.assertEqual(report["eligible_races"],0)
        self.assertIsNone(report["plans"]["balanced"]["all"]["roi_percent"])


if __name__ == "__main__":
    unittest.main()
