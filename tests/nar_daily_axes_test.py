import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_nar_daily_axes import analyze


def race(id, ranking, result, trios=None, trifectas=None):
    return {
        "id": id, "date": "2026-11-22", "venue": "高知",
        "start_at": "2026-11-22T20:00:00+09:00",
        "cutoff_at": "2026-11-22T19:45:00+09:00",
        "locked_at": "2026-11-22T19:44:00+09:00",
        "predicted_at": "2026-11-22T19:43:00+09:00",
        "ranking": [{"no": n} for n in ranking], "result": result,
        "trio_tickets": trios, "tickets": trifectas,
    }


class DailyAxesTest(unittest.TestCase):
    def test_hit_and_misses_without_mutating_history(self):
        rows = [
            race("a", [1,2,3,4,5,6], [1,2,3], [[1,2,3]], [[1,3,2]]),
            race("b", [1,2,3,4,5,6], [4,5,6], [[1,2,3]], [[1,2,3]]),
            race("c", [1,2,3,4,5,6], [2,3,4], [[2,3,5],[2,4,5],[3,4,5]], [[2,4,3]]),
            race("d", [1,2,3,4,5,6], [1,2,3], [[1,2,3]], [[1,2,3]]),
        ]
        before = copy.deepcopy(rows)
        x = analyze(rows, "2026-11-22")
        self.assertEqual(rows, before)
        self.assertEqual(x["settled_eligible"], 4)
        self.assertEqual(x["top1_win"], 2)
        self.assertEqual(x["top2_both_in_podium"], 2)
        self.assertEqual(x["podium_inside_top5"], 3)
        self.assertEqual(x["trio"]["candidate_missing"], 1)
        self.assertEqual(x["trio"]["combination_missing"], 1)
        self.assertEqual(x["trio"]["hit"], 2)
        self.assertEqual(x["trifecta"]["order_mismatch"], 2)
        self.assertEqual(x["trifecta"]["hit"], 1)

    def test_prelock_deadheat_and_unsettled_excluded(self):
        first = race("ok", [1,2,3,4,5], [1,2,3])
        late = {**first, "id":"late", "locked_at":"2026-11-22T19:46:00+09:00"}
        tie = {**first, "id":"tie", "result_alternatives":[[1,2,3],[2,1,3]]}
        incomplete = {**first, "id":"none", "result":None}
        x = analyze([first, late, tie, incomplete, first], "2026-11-22")
        self.assertEqual(x["settled_eligible"], 1)
        self.assertEqual(x["excluded"]["prelock_not_verifiable"], 1)
        self.assertEqual(x["excluded"]["draft_or_dead_heat"], 1)
        self.assertEqual(x["excluded"]["missing_or_invalid_result"], 1)
        self.assertEqual(x["excluded"]["missing_or_duplicate_id"], 1)
        self.assertEqual(x["trio"]["unrecorded"], 1)

    def test_conflicting_duplicate_ids_are_order_independent(self):
        a = race("conflict", [1,2,3,4,5], [1,2,3])
        b = {**a, "result": [3,2,1]}
        ok = race("valid", [1,2,3,4,5], [1,2,3])
        for rows in ([a,b,ok], [b,a,ok]):
            before = copy.deepcopy(rows)
            x = analyze(rows, "2026-11-22")
            self.assertEqual(rows, before)
            self.assertEqual(x["races_on_date"], 3)
            self.assertEqual(x["settled_eligible"], 1)
            self.assertEqual(x["excluded"], {"conflicting_duplicate_id": 2})
            self.assertEqual(x["top1_win"], 1)

    def test_unranked_podium_horse_is_a_miss_not_excluded(self):
        # Previous audit silently dropped exactly this kind of surprise result.
        row = race("surprise", [1,2,3,4,5], [8,2,3],
                   [[1,2,3]], [[1,2,3]])
        frozen = copy.deepcopy(row)
        x = analyze([row], "2026-11-22")
        self.assertEqual(row, frozen)
        self.assertEqual(x["settled_eligible"], 1)
        self.assertEqual(x["excluded"], {})
        self.assertEqual(x["top1_win"], 0)
        self.assertEqual(x["podium_inside_top5"], 0)
        self.assertEqual(x["winner_outside_top5"], 1)
        self.assertEqual(x["podium_horse_outside_ranking"], 1)
        self.assertEqual(x["trio"]["candidate_missing"], 1)
        self.assertEqual(x["trifecta"]["candidate_missing"], 1)

    def test_unranked_third_finisher_counts_as_axis_success_only(self):
        row = race("third", [1,2,3,4,5], [1,2,8])
        x = analyze([row], "2026-11-22")
        self.assertEqual(x["settled_eligible"], 1)
        self.assertEqual(x["top1_win"], 1)
        self.assertEqual(x["top2_both_in_podium"], 1)
        self.assertEqual(x["podium_inside_top5"], 0)
        self.assertEqual(x["podium_horse_outside_ranking"], 1)

    def test_venue_misses_and_banei_are_separate_and_reconcile(self):
        rows = [race("flat", [1,2,3,4,5,6], [1,2,3], [[1,2,3]], [[1,3,2]]),
                {**race("banei", [1,2,3,4,5,6], [6,2,3], [[1,2,3]], [[1,2,3]]),
                 "venue": "帯広ば"}]
        before = copy.deepcopy(rows)
        x = analyze(rows, "2026-11-22")
        self.assertEqual(rows, before)
        self.assertEqual(x["disciplines"]["flat"]["trifecta_order_mismatch"], 1)
        self.assertEqual(x["disciplines"]["banei"]["trio_candidate_missing"], 1)
        self.assertEqual(x["venues"]["帯広ば"]["winner_outside_top5"], 1)
        self.assertEqual(len(x["race_details"]), x["settled_eligible"])
        self.assertEqual(sum(v["settled"] for v in x["disciplines"].values()), x["settled_eligible"])
        for kind in ("trio", "trifecta"):
            for reason, count in x[kind].items():
                self.assertEqual(sum(v.get(f"{kind}_{reason}", 0) for v in x["venues"].values()), count)
                self.assertEqual(sum(d[kind] == reason for d in x["race_details"]), count)

    def test_daily_winner_rank_distribution_and_review(self):
        surprising = race("surprise", [1,2,3,4,5,6], [8,2,3],
                          [[1,2,3]], [[1,2,3]])
        sixth = race("sixth", [1,2,3,4,5,6], [6,2,3],
                     [[1,2,3]], [[1,2,3]])
        normal = race("normal", [1,2,3,4,5,6], [1,2,3],
                      [[1,2,3]], [[1,2,3]])
        normal["finish_order"] = [{"no": 1},{"no": 2},{"no": 3}]
        x = analyze([surprising, sixth, normal], "2026-11-22")
        self.assertEqual(x["winner_predicted_rank_distribution"],
                         {"1": 1, "6plus": 1, "not_in_ranking": 1})
        self.assertEqual(x["finish_order_quality_flags"]["ranked_horses_absent_from_finish_order"], 1)
        reviews = {item["id"]: item for item in x["race_reviews"]}
        self.assertEqual(reviews["surprise"]["winner_predicted_rank"], None)
        self.assertEqual(reviews["sixth"]["winner_predicted_rank"], 6)
        self.assertEqual(reviews["surprise"]["trio_reason"], "candidate_missing")
        self.assertEqual(reviews["normal"]["ranked_horses_absent_from_finish_order"], [4,5,6])

    def test_duplicate_frozen_tickets_cannot_be_reported_as_hits(self):
        row = race("duplicate", [1,2,3,4,5],
                   [1,2,3], [[1,2,3],[3,2,1]], [[1,2,3],[1,2,3]])
        x = analyze([row], "2026-11-22")
        self.assertEqual(x["settled_eligible"], 1)
        self.assertEqual(x["trio"]["unrecorded"], 1)
        self.assertEqual(x["trifecta"]["unrecorded"], 1)
        self.assertEqual(x["race_reviews"][0]["trio_reason"], "unrecorded")

    def test_other_date_and_invalid_schema(self):
        r = race("x", [1,2,3,4,5], [1,2,3])
        self.assertEqual(analyze([r], "2026-11-21")["settled_eligible"], 0)
        with self.assertRaises(ValueError):
            analyze({}, "2026-11-22")


if __name__ == "__main__":
    unittest.main()
