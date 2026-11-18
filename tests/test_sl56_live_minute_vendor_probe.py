"""Live probe output never qualifies insufficient market data."""
from infra.aws import sl56_live_minute_vendor_probe as p
def test_fails_both_symbols_without_fake_close(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("289/390 1m bars")
    r=p.verify_session("2026-11-17",fetch=fail)
    assert r["qualified"] is False
    assert set(r["symbols"])=={"QQQ","TQQQ"}
    assert all(z["status"]=="INCOMPLETE_NO_PAPER" for z in r["symbols"].values())
    assert r["paper_receipts_created"] is False
    assert r["aws_mutations"] is False
