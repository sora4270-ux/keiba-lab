import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from reconcile_cash_statement import reconcile

DAY="2026-11-24"
def row(ident="a", **updates):
    return {"transaction_id":ident,"date":DAY,"status":"settled","purchase_yen":1000,
            "payout_yen":500,"refund_yen":200,"statement_reference":"local-record",**{}} | updates

class StatementTest(unittest.TestCase):
    def test_settled_amounts_and_duplicates(self):
        a=row()
        x=reconcile([a,a,row("b",purchase_yen=100,payout_yen=0,refund_yen=100)],DAY)
        self.assertEqual(x["confirmed_transactions"],2)
        self.assertEqual(x["refund_yen"],300)
        self.assertEqual(x["net_yen"],-300)
        self.assertEqual(x["excluded"]["identical_duplicate"],1)
    def test_unknown_and_conflict_never_become_zero(self):
        x=reconcile([row(),row(refund_yen=0),row("b",status="pending"),
                     row("c",refund_yen=None),row("d",refund_yen=1000)],DAY)
        self.assertEqual(x["status"],"no_confirmed_records")
        self.assertIsNone(x["net_yen"])
        self.assertIsNone(x["refund_yen"])
    def test_partial_statement(self):
        x=reconcile([row(),row("b",status="pending")],DAY)
        self.assertEqual(x["status"],"partial_statement")
        self.assertEqual(x["net_yen"],-300)

if __name__=="__main__":
    unittest.main()
