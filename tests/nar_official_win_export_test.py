import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from export_nar_official_win_payouts import extract, official_win_market


def record(no="3", amount="240", venue="大井", date="20261001", race="1"):
    row = [""] * 6
    row[0], row[1], row[2], row[4], row[5] = venue, date, race, no, amount
    return row, {}


class OfficialWinExportTests(unittest.TestCase):
    def test_winner_and_verified_loser(self):
        tables = {"payback": [record()]}
        selections = [
            {"race_id": "nar-20261001-大井-01", "horse_no": "3", "bet_type": "win"},
            {"race_id": "nar-20261001-大井-01", "horse_no": "4", "bet_type": "win"},
        ]
        rows, skipped = extract(selections, tables)
        self.assertEqual([r["official_payout_per_100_yen"] for r in rows], ["240", "0"])
        self.assertEqual(skipped, {})

    def test_missing_market_never_assumed_loss(self):
        rows, skipped = extract([{"race_id": "nar-20261001-大井-01",
                                  "horse_no": "4", "bet_type": "win"}], {})
        self.assertEqual(rows, [])
        self.assertEqual(skipped["missing_or_ambiguous_official_win_market"], 1)

    def test_dead_heat_and_conflict_skipped(self):
        self.assertEqual(official_win_market({"payback": [record(), record(no="4")]}), {})
        self.assertEqual(official_win_market({"payback": [record(), record(amount="300")]}), {})

    def test_place_is_not_guessed(self):
        rows, skipped = extract([{"race_id": "nar-20261001-大井-01",
                                  "horse_no": "3", "bet_type": "place"}],
                                {"payback": [record()]})
        self.assertEqual(rows, [])
        self.assertEqual(skipped["unsupported_bet_type"], 1)


if __name__ == "__main__":
    unittest.main()
