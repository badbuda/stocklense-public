import copy
import unittest
from research.pit_breadth_coverage_gate_20261112 import qualify

def sample():
    return {"source_kind":"observed_constituent_pit","membership_source_id":"vendor-A-v1",
            "price_source_id":"vendor-B-v1","session":"2026-11-09",
            "decision_at":"2026-11-09T22:00:00Z",
            "membership":[{"security_id":"AAA","known_at":"2026-11-06T20:00:00Z",
                           "effective_from":"2026-11-09","effective_to":None}],
            "prices":[{"security_id":"AAA","known_at":"2026-11-09T21:30:00Z",
                       "session":"2026-11-09","close":100.0}]}

class TestCoverage(unittest.TestCase):
    def test_structural_is_not_real_breadth(self):
        x=qualify(sample())
        self.assertEqual(x["status"],"STRUCTURAL_ONLY")
        self.assertFalse(x["historical_breadth_authorized"])
    def test_missing_price(self):
        x=sample();x["prices"][0]["security_id"]="BBB"
        self.assertEqual(qualify(x)["reason"],"MEMBERSHIP_PRICE_SET_MISMATCH")
    def test_stale_price(self):
        x=sample();x["prices"][0]["session"]="2026-11-06"
        self.assertEqual(qualify(x)["reason"],"STALE_OR_WRONG_SESSION_PRICE")
    def test_future_member(self):
        x=sample();x["membership"][0]["known_at"]="2026-11-10T00:00:00Z"
        self.assertEqual(qualify(x)["reason"],"FUTURE_MEMBERSHIP")
    def test_future_price(self):
        x=sample();x["prices"][0]["known_at"]="2026-11-10T00:00:00Z"
        self.assertEqual(qualify(x)["reason"],"FUTURE_PRICE")
    def test_missing_provenance(self):
        x=sample();del x["membership_source_id"]
        self.assertEqual(qualify(x)["reason"],"SOURCE_PROVENANCE_MISSING")
    def test_duplicate_security(self):
        x=sample();x["membership"].append(copy.deepcopy(x["membership"][0]))
        self.assertEqual(qualify(x)["reason"],"DUPLICATE_OR_EMPTY_SECURITY_ID")
    def test_proxy(self):
        x=sample();x["source_kind"]="qqqe_proxy"
        self.assertEqual(qualify(x)["reason"],"PROXY_NOT_PIT")
    def test_invalid_price(self):
        x=sample();x["prices"][0]["close"]="NaN"
        self.assertEqual(qualify(x)["reason"],"INVALID_PRICE")

if __name__=="__main__":
    unittest.main()
