import copy
import unittest
from research.pit_breadth_vendor_reconcile_20261113 import reconcile

D="2026-11-09T22:00:00Z"
def feed(v):
    return {"vendor_id":v,"observations":[{"security_id":"A","active":True,
           "known_at":"2026-11-09T20:00:00Z"}]}
class VendorGateTests(unittest.TestCase):
    def test_agreement_not_certification(self):
        x=reconcile(feed("A"),feed("B"),D)
        self.assertEqual(x["status"],"AGREEMENT_ONLY")
        self.assertFalse(x["historical_breadth_authorized"])
    def test_same_vendor(self):
        self.assertEqual(reconcile(feed("A"),feed("A"),D)["reason"],"SAME_VENDOR_NOT_INDEPENDENT")
    def test_future_revision(self):
        b=feed("B");b["observations"][0]["known_at"]="2026-11-10T01:00:00Z"
        self.assertEqual(reconcile(feed("A"),b,D)["reason"],"FUTURE_VENDOR_DISCLOSURE")
    def test_disagreement(self):
        b=feed("B");b["observations"][0]["active"]=False
        self.assertEqual(reconcile(feed("A"),b,D)["conflicting"],["A"])
    def test_missing_member(self):
        b=feed("B");b["observations"][0]["security_id"]="B"
        self.assertEqual(reconcile(feed("A"),b,D)["only_primary"],["A"])
    def test_duplicate(self):
        b=feed("B");b["observations"].append(copy.deepcopy(b["observations"][0]))
        self.assertEqual(reconcile(feed("A"),b,D)["reason"],"INVALID_OR_DUPLICATE_SECURITY_ID")
    def test_naive_timestamp(self):
        self.assertEqual(reconcile(feed("A"),feed("B"),"2026-11-09T22:00:00")["reason"],"NAIVE_TIMESTAMP")
    def test_invalid_boolean(self):
        b=feed("B");b["observations"][0]["active"]=1
        self.assertEqual(reconcile(feed("A"),b,D)["reason"],"NON_BOOLEAN_MEMBERSHIP")
