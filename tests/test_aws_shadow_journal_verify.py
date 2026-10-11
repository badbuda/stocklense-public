"""Fail-closed safety regressions for AWS observed shadow archive checks."""
import hashlib
import json

import pytest

from aws_shadow_journal_verify import verify_journal_response

DAY = "2026-10-08"


def make_result():
    payload = {
        "version": "8.0.2-shadow-completed-session-guard",
        "mode": "SHADOW_ONLY_NO_BROKER_ACTIONS",
        "signal_source": "QQQ_ADJUSTED_DAILY_CLOSE",
        "generated_at_utc": "2026-10-08T23:25:00+00:00",
        "execution_plan": {"broker_actions_enabled": False},
        "latest": {
            "asof_date": DAY,
            "level": 3,
            "qqq_weight": 0,
            "tqqq_weight": 0.985,
        },
    }
    raw = json.dumps(payload)
    return {"Item": {
        "session_date": {"S": DAY},
        "recorded_at_utc": {"S": "2026-10-09T03:10:00+00:00"},
        "signal_json": {"S": raw},
        "signal_sha256": {"S": hashlib.sha256(raw.encode()).hexdigest()},
        "broker_orders_authorized": {"BOOL": False},
    }}


def edit_payload(record, fn):
    obj = json.loads(record["Item"]["signal_json"]["S"])
    fn(obj)
    raw = json.dumps(obj)
    record["Item"]["signal_json"]["S"] = raw
    record["Item"]["signal_sha256"]["S"] = hashlib.sha256(raw.encode()).hexdigest()


def test_valid_record_is_only_archive_proof():
    result = verify_journal_response(make_result(), DAY)
    assert result["status"] == "PASS_OBSERVED_ARCHIVED_SHADOW_SIGNAL"
    assert result["broker_fill_evidence"] is False
    assert result["live_trading_authorized"] is False


def test_no_record_fails():
    with pytest.raises(ValueError, match="JOURNAL_SESSION_NOT_FOUND"):
        verify_journal_response({}, DAY)


def test_sha_mismatch_even_when_signal_json_parses():
    result = make_result()
    result["Item"]["signal_sha256"]["S"] = "0" * 64
    with pytest.raises(ValueError, match="SIGNAL_ARCHIVE_SHA256_MISMATCH"):
        verify_journal_response(result, DAY)


@pytest.mark.parametrize("field,value,expected", [
    ("mode", "BROKER_LIVE", "NOT_SHADOW_ONLY"),
    ("signal_source", "TQQQ_SYNTHETIC", "INVALID_SIGNAL_SOURCE"),
    ("version", "9.0", "FROZEN_VERSION_REQUIRED"),
])
def test_rejects_incompatible_contract(field, value, expected):
    row = make_result()
    edit_payload(row, lambda o: o.update({field: value}))
    with pytest.raises(ValueError, match=expected):
        verify_journal_response(row, DAY)


def test_rejects_embedded_broker_flag():
    row = make_result()
    edit_payload(row, lambda o: o["execution_plan"].update(broker_actions_enabled=True))
    with pytest.raises(ValueError, match="SIGNAL_BROKER_FLAG_NOT_DISABLED"):
        verify_journal_response(row, DAY)


def test_rejects_stored_broker_flag():
    row = make_result()
    row["Item"]["broker_orders_authorized"]["BOOL"] = True
    with pytest.raises(ValueError, match="BROKER_EXECUTION_MUST_REMAIN_DISABLED"):
        verify_journal_response(row, DAY)


def test_rejects_mismatched_session_even_if_json_matches_hash():
    row = make_result()
    edit_payload(row, lambda o: o["latest"].update(asof_date="2026-10-07"))
    with pytest.raises(ValueError, match="SIGNAL_ASOF_DATE_MISMATCH"):
        verify_journal_response(row, DAY)


def test_rejects_wrong_primary_key():
    row = make_result()
    row["Item"]["session_date"]["S"] = "2026-10-07"
    with pytest.raises(ValueError, match="JOURNAL_PRIMARY_KEY_MISMATCH"):
        verify_journal_response(row, DAY)


def test_rejects_future_and_old_generation():
    row = make_result()
    edit_payload(row, lambda o: o.update(generated_at_utc="2026-10-09T05:10:00+00:00"))
    with pytest.raises(ValueError, match="SIGNAL_WAS_NOT_FRESH_AT_RECORD_TIME"):
        verify_journal_response(row, DAY)
    row = make_result()
    edit_payload(row, lambda o: o.update(generated_at_utc="2026-10-07T03:10:00+00:00"))
    with pytest.raises(ValueError, match="SIGNAL_WAS_NOT_FRESH_AT_RECORD_TIME"):
        verify_journal_response(row, DAY)


def test_rejects_invalid_exposure():
    row = make_result()
    edit_payload(row, lambda o: o["latest"].update(tqqq_weight=1.2))
    with pytest.raises(ValueError, match="INVALID_TARGET_WEIGHTS"):
        verify_journal_response(row, DAY)


def test_rejects_missing_generating_timestamp():
    row = make_result()
    edit_payload(row, lambda o: o.pop("generated_at_utc"))
    with pytest.raises(ValueError, match="INVALID_SIGNAL_TIME"):
        verify_journal_response(row, DAY)
