import unittest
from research.pit_breadth_input_gate_20261111 import audit

def fixture():
    return {"source_kind":"observed_constituent_pit","sessions":[{"session":"2026-11-09",
      "decision_at":"2026-11-09T22:00:00Z","members":[{"symbol":"AAA",
      "member_from":"2020-01-01","member_to":None,
      "membership_known_at":"2020-01-01T12:00:00Z",
      "price_known_at":"2026-11-09T21:30:00Z","close":100}]}]}

class TestPitGate(unittest.TestCase):
    def test_qualified_input_not_backtest(self):
        x=audit(fixture()); self.assertEqual(x["status"],"INPUT_QUALIFIED_ONLY")
    def test_proxy_rejected(self):
        x=fixture();x["source_kind"]="qqqe_proxy";self.assertEqual(audit(x)["status"],"BLOCKED")
    def test_future_membership_rejected(self):
        x=fixture();x["sessions"][0]["members"][0]["membership_known_at"]="2026-11-10T00:00:00Z"
        self.assertEqual(audit(x)["reason"],"FUTURE_MEMBERSHIP_DISCLOSURE")
    def test_future_price_rejected(self):
        x=fixture();x["sessions"][0]["members"][0]["price_known_at"]="2026-11-10T00:00:00Z"
        self.assertEqual(audit(x)["reason"],"FUTURE_PRICE")
    def test_delisted_rejected(self):
        x=fixture();x["sessions"][0]["members"][0]["member_to"]="2026-11-09"
        self.assertEqual(audit(x)["reason"],"DELISTED_MEMBER")
    def test_duplicate_symbol_rejected(self):
        x=fixture();x["sessions"][0]["members"]*=2
        self.assertEqual(audit(x)["reason"],"DUPLICATE_SYMBOL")
    def test_no_timezone_rejected(self):
        x=fixture();x["sessions"][0]["decision_at"]="2026-11-09T22:00:00"
        self.assertEqual(audit(x)["reason"],"timezone_required")
if __name__=="__main__":unittest.main()
