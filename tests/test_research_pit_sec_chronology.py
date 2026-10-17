"""Synthetic SEC event chronology check."""
import hashlib,json,pytest
from research_pit_event_gate import audit

def test_publication_before_acceptance_is_impossible():
    row={"provider":"SEC_EDGAR","source_record_id":"fixture",
         "source_record_sha256":hashlib.sha256(b"fixture").hexdigest(),
         "published_at_utc":"2026-10-15T13:29:00Z",
         "accepted_at_utc":"2026-10-15T13:30:00Z",
         "collected_at_utc":"2026-10-15T13:31:00Z"}
    with pytest.raises(ValueError,match="SEC_PUBLISHED_BEFORE_ACCEPTANCE"):
        audit(json.dumps([row]).encode())
