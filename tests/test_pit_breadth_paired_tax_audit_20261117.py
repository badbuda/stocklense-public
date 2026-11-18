import unittest
from research.pit_breadth_paired_tax_audit_20261117 import audit_pair

def fixtures():
    base = dict(dataset_sha256="a"*64, execution_sha256="b"*64,
                sessions=["2026-01-05", "2026-01-06"], lag_sessions=1,
                source_kind="synthetic", cash_timing="immediate")
    before = dict(base, tax_mode="none", rows=[
        dict(session="2026-01-05", gross_equity_nis="1000", fees_nis="1", trade_fingerprint="x"),
        dict(session="2026-01-06", gross_equity_nis="1100", fees_nis="1", trade_fingerprint="y")])
    after = dict(base, tax_mode="illustrative", statutory_tax_verified=False, rows=[
        dict(before["rows"][0], tax_paid_nis="10", net_equity_nis="990"),
        dict(before["rows"][1], tax_paid_nis="20", net_equity_nis="1070")])
    return before, after

class PairedTaxAuditTests(unittest.TestCase):
    def test_synthetic_pair_structural_only(self):
        a,b=fixtures()
        self.assertEqual(audit_pair(a,b)["status"],"STRUCTURAL_ONLY")
        self.assertFalse(audit_pair(a,b)["performance_verified"])
    def test_dataset_mismatch(self):
        a,b=fixtures(); b["dataset_sha256"]="c"*64
        self.assertEqual(audit_pair(a,b)["status"],"BLOCKED")
    def test_lag_zero(self):
        a,b=fixtures(); a["lag_sessions"]=b["lag_sessions"]=0
        self.assertEqual(audit_pair(a,b)["status"],"BLOCKED")
    def test_gross_mismatch(self):
        a,b=fixtures(); b["rows"][0]["gross_equity_nis"]="1001"
        self.assertEqual(audit_pair(a,b)["status"],"BLOCKED")
    def test_tax_not_reconciled(self):
        a,b=fixtures(); b["rows"][1]["net_equity_nis"]="1090"
        self.assertEqual(audit_pair(a,b)["status"],"BLOCKED")
    def test_unverified_tax_disclosed(self):
        a,b=fixtures(); b["statutory_tax_verified"]=True
        self.assertEqual(audit_pair(a,b)["status"],"BLOCKED")
    def test_year_end_not_silently_accepted(self):
        a,b=fixtures(); a["cash_timing"]=b["cash_timing"]="year_end"
        self.assertEqual(audit_pair(a,b)["status"],"BLOCKED")
    def test_duplicate_session_rejected(self):
        a,b=fixtures()
        a["sessions"][1]=b["sessions"][1]=a["sessions"][0]
        self.assertEqual(audit_pair(a,b)["reason"], "NON_MONOTONIC_OR_DUPLICATE_SESSIONS")
    def test_reversed_sessions_rejected(self):
        a,b=fixtures()
        a["sessions"]=b["sessions"]=list(reversed(a["sessions"]))
        self.assertEqual(audit_pair(a,b)["status"], "BLOCKED")
    def test_malformed_digest_rejected(self):
        a,b=fixtures()
        a["dataset_sha256"]=b["dataset_sha256"]="not-a-sha256"
        self.assertEqual(audit_pair(a,b)["reason"], "INVALID_DATASET_SHA256")
    def test_invalid_session_date_rejected(self):
        a,b=fixtures()
        a["sessions"][0]=b["sessions"][0]="2026-99-99"
        self.assertEqual(audit_pair(a,b)["status"], "BLOCKED")
    def test_proxy_not_observed(self):
        a,b=fixtures(); a["source_kind"]=b["source_kind"]="proxy"
        self.assertEqual(audit_pair(a,b)["source_kind"],"proxy")

if __name__=="__main__":
    unittest.main()
