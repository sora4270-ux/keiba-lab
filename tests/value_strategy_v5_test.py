#!/usr/bin/env python3
"""Regression tests for strictly pre-race shadow picks."""
import datetime as dt
import itertools
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from value_strategy_v5 import build_shadow_plan

NOW = "2026-11-08T10:00:00+09:00"


def fixture(n=7, concentrated=False):
    ranking = [{"no": i} for i in range(1, n + 1)]
    combos = list(itertools.combinations(range(1, n + 1), 3))
    if concentrated:
        weights = [0.09 if set(t).issubset(set(range(1, 6))) else 0.004 for t in combos]
    else:
        weights = [1. for _ in combos]
    total = sum(weights)
    trios = [(t, w / total) for t, w in zip(combos, weights)]
    odds = {t: 10000. for t, _ in trios}
    return ranking, trios, odds


def plan(ranking, trios, quotes, **kw):
    return build_shadow_plan(ranking, [], trios, quotes, NOW, True, NOW, **kw)


class V5ShadowTest(unittest.TestCase):
    def test_can_use_seven_and_records_coverage(self):
        ranking, trios, odds = fixture()
        outcome = plan(ranking, trios, odds)
        self.assertEqual(outcome["candidate_count"], 7)
        self.assertAlmostEqual(outcome["coverage_by_count"]["5"], 10 / 35, places=5)
        self.assertAlmostEqual(outcome["coverage_by_count"]["6"], 20 / 35, places=5)
        self.assertEqual(outcome["count"], 10)
        self.assertEqual(outcome["stake_yen"], 1000)
        self.assertEqual(len(set(map(tuple, outcome["tickets"]))), 10)

    def test_five_horse_concentration(self):
        ranking, trios, odds = fixture(concentrated=True)
        outcome = plan(ranking, trios, odds)
        self.assertEqual(outcome["candidate_count"], 5)
        self.assertTrue(all(set(t).issubset(set(range(1, 6))) for t in outcome["tickets"]))

    def test_insufficient_coverage_requires_skip(self):
        ranking, trios, odds = fixture(12)
        outcome = plan(ranking, trios, odds)
        self.assertEqual(outcome["status"], "below_coverage")
        self.assertEqual(outcome["tickets"], [])
        self.assertEqual(outcome["stake_yen"], 0)

    def test_missing_prices_never_fabricated(self):
        ranking, trios, _ = fixture()
        outcome = plan(ranking, trios, {})
        self.assertEqual(outcome["status"], "no_trio_quotes")
        self.assertFalse(outcome["tickets"])
        outcome = plan(ranking, trios, {(1, 2, 3): 3.})
        self.assertEqual(outcome["status"], "below_value")

    def test_no_market_and_staleness(self):
        ranking, trios, odds = fixture()
        self.assertEqual(build_shadow_plan(ranking, [], trios, odds, NOW, False, NOW)["status"], "no_win_market")
        stale = "2026-11-08T09:30:00+09:00"
        self.assertEqual(build_shadow_plan(ranking, [], trios, odds, NOW, True, stale)["status"], "stale_market")
        future = "2026-11-08T10:01:00+09:00"
        self.assertEqual(build_shadow_plan(ranking, [], trios, odds, NOW, True, future)["status"], "stale_market")

    def test_no_value_and_official_odds_only(self):
        ranking, trios, odds = fixture()
        self.assertEqual(plan(ranking, trios, {t: 1.0 for t in odds})["status"], "below_value")
        outcome = plan(ranking, trios, {(40, 41, 42): 100.})
        self.assertEqual(outcome["status"], "no_matching_quotes")

    def test_no_result_information_is_used(self):
        ranking, trios, odds = fixture()
        before = plan(ranking, trios, odds)
        after = plan(ranking, trios, odds)
        self.assertEqual(before, after)
        self.assertNotIn("result", before)
        self.assertNotIn("payout", before)


if __name__ == "__main__":
    unittest.main()
