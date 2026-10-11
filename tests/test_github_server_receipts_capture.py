import hashlib
import io
import json
import zipfile
import pytest
from github_server_receipts_capture import (
    report_event_pages, inspect_zip, TARGET_COMMITS)


def test_server_event_created_time_extracted_but_not_market_timestamp():
    event={"id":"server-1","type":"PushEvent","created_at":"2026-10-08T15:00:00Z",
           "payload":{"ref":"refs/heads/main","head":TARGET_COMMITS[0],
                      "commits":[{"sha":TARGET_COMMITS[0]}]}}
    a=report_event_pages([json.dumps([event]).encode()])
    assert a["target_sha_matched_server_events"][TARGET_COMMITS[0]]["github_server_created_at"]=="2026-10-08T15:00:00Z"
    assert a["server_event_receipt_alone_proves_market_capture"] is False
    assert len(a["target_sha_not_found"])==2


def test_not_found_events_cannot_claim_capture():
    a=report_event_pages([b"[]"])
    assert not a["target_sha_matched_server_events"]
    assert len(a["target_sha_not_found"])==len(TARGET_COMMITS)
    assert a["git_author_time_independent_receipt"] is False


def test_validate_old_zip_without_trusting_timestamps():
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w") as z:
        z.writestr("research/data/a.txt","example bytes")
    v=inspect_zip(stream.getvalue(),123)
    assert v["zip_sha256"]==hashlib.sha256(stream.getvalue()).hexdigest()
    assert v["original_market_first_seen_proven"] is False


def test_path_traversal_archive_rejected():
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w") as z:
        z.writestr("../secret","bytes")
    with pytest.raises(ValueError,match="UNSAFE_ORIGINAL_ARTIFACT_ZIP"):
        inspect_zip(stream.getvalue(),123)
