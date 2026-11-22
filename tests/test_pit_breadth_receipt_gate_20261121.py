"""Synthetic contract fixtures only; no observed constituent data."""
import copy
import unittest
from research.pit_breadth_receipt_gate_20261121 import qualify
class TestReceipt(unittest.TestCase):
    def setUp(self):
        self.r={"source_kind":"observed_pit","index":"NDX","decision_at":"2020-01-03T21:00:00+00:00","expected_security_count":2,"vendors":[]}
        for n in ("A","B"):
            self.r["vendors"].append({"vendor_id":n,"source_reference":"fixture","snapshot_sha256":"a"*64,"published_at":"2020-01-03T20:00:00+00:00","retrieved_at":"2020-01-03T20:30:00+00:00","members":["AAA","BBB"]})
    def test_structural_only(self):
        x=qualify(self.r);self.assertEqual(x["status"],"STRUCTURAL_ONLY");self.assertFalse(x["historical_truth_verified"])
    def test_proxy(self):
        self.r["source_kind"]="proxy";self.assertEqual(qualify(self.r)["status"],"BLOCKED")
    def test_future(self):
        self.r["vendors"][0]["published_at"]="2020-01-04T00:00:00+00:00";self.assertEqual(qualify(self.r)["status"],"BLOCKED")
    def test_retrospective_retrieval(self):
        self.r["vendors"][0]["retrieved_at"]="2020-01-04T10:00:00+00:00"
        x=qualify(self.r)
        self.assertEqual(x["status"],"BLOCKED")
        self.assertEqual(x["reason"],"RETROSPECTIVE_RETRIEVAL_NOT_LIVE_PIT")
    def test_retrieval_exactly_at_decision(self):
        self.r["vendors"][0]["retrieved_at"]=self.r["decision_at"]
        self.assertEqual(qualify(self.r)["status"],"STRUCTURAL_ONLY")
    def test_disagreement(self):
        self.r["vendors"][1]["members"]=["AAA","CCC"];self.assertEqual(qualify(self.r)["status"],"BLOCKED")
    def test_duplicate_vendor(self):
        self.r["vendors"][1]["vendor_id"]="A";self.assertEqual(qualify(self.r)["status"],"BLOCKED")
    def test_naive_time(self):
        self.r["decision_at"]="2020-01-03T21:00:00";self.assertEqual(qualify(self.r)["status"],"BLOCKED")
    def test_count(self):
        self.r["expected_security_count"]=100;self.assertEqual(qualify(self.r)["status"],"BLOCKED")
    def test_missing_member(self):
        self.r["vendors"][1]["members"]=["AAA"];self.assertEqual(qualify(self.r)["status"],"BLOCKED")
if __name__=="__main__":unittest.main()
