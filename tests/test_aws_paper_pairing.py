"""Deterministic no-AWS regression tests of cross-session archival pairing."""
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from aws_paper_pairing import previous_session, verify_pair

DAY = "2026-10-09"
PRIOR = "2026-10-08"


def _ddb_json(key, obj, field, fingerprint):
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return {
        "session_date": {"S": key},
        field: {"S": raw},
        fingerprint: {"S": sha256(raw.encode()).hexdigest()},
        "broker_orders_authorized": {"BOOL": False},
    }


def good_items():
    signal = {
        "version": "8.0.2-shadow-completed-session-guard",
        "mode": "SHADOW_ONLY_NO_BROKER_ACTIONS",
        "signal_source": "QQQ_ADJUSTED_DAILY_CLOSE",
        "generated_at_utc": "2026-10-08T23:25:00+00:00",
        "execution_plan": {"broker_actions_enabled": False},
        "latest": {
            "asof_date": PRIOR, "level": 3,
            "qqq_weight": 0.0, "tqqq_weight": 0.985,
        },
    }
    prior = _ddb_json(PRIOR, signal, "signal_json", "signal_sha256")
    prior["recorded_at_utc"] = {"S": "2026-10-09T09:10:30+00:00"}
    row = {
        "session_date": DAY,
        "signal_date": PRIOR,
        "execution_source": "YFINANCE_1M_RAW",
        "trade_count_session": 2,
        "target_qqq_weight": 0.0,
        "target_tqqq_weight": 0.985,
        "cash": 1200.0,
        "equity": 100000.0,
        "qqq_shares": 0,
        "tqqq_shares": 100,
    }
    trades = [
        {"execution_session": DAY, "signal_date": PRIOR,
         "symbol": "QQQ", "side": "SELL", "time_et": "09:31",
         "qty": 1, "modeled_fill_price": 100.0},
        {"execution_session": DAY, "signal_date": PRIOR,
         "symbol": "TQQQ", "side": "BUY", "time_et": "09:32",
         "qty": 100, "modeled_fill_price": 82.0},
    ]
    paper = _ddb_json(DAY + "#PAPER", {"row": row, "trs": trades},
                      "paper_evidence_json", "paper_sha256")
    paper["broker_fills_observed"] = {"BOOL": False}
    return prior, paper


def rewrite(entry, field, sha_field, fn):
    obj = json.loads(entry[field]["S"])
    fn(obj)
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    entry[field]["S"] = raw
    entry[sha_field]["S"] = sha256(raw.encode()).hexdigest()


def test_valid_pair_is_not_live_or_independent_forward_proof():
    signal, paper = good_items()
    report = verify_pair(DAY, signal, paper)
    assert report["status"] == "PASS_READ_ONLY_ARCHIVE_PAIRING_MODELED_NOT_BROKER_FILLS"
    assert report["signal_session"] == PRIOR
    assert report["execution_session"] == DAY
    assert not report["qualified_independent_forward_session"]
    assert not report["broker_fills_observed"]
    assert not report["automatic_trading_authorized"]
    assert len(report["local_pair_digest_sha256"]) == 64


def test_missing_both_sources_fail_closed():
    prior, paper = good_items()
    with pytest.raises(ValueError, match="PRIOR_SIGNAL_ARCHIVE_MISSING"):
        verify_pair(DAY, None, paper)
    with pytest.raises(ValueError, match="PAPER_ARCHIVE_MISSING"):
        verify_pair(DAY, prior, None)


@pytest.mark.parametrize("session, expected", [
    ("2026-10-09", "2026-10-08"),
    ("2026-10-12", "2026-10-09"),
    ("2026-12-28", "2026-12-24"),
])
def test_previous_session_uses_holidays_and_weekends(session, expected):
    assert previous_session(session) == expected


@pytest.mark.parametrize("invalid", ["2026-10-10", "2026-10-11", "2026-13-09", "not-date"])
def test_invalid_exchange_date(invalid):
    with pytest.raises(ValueError, match="INVALID_XNYS_EXECUTION_SESSION"):
        previous_session(invalid)


def test_rehashed_wrong_paper_signal_date_is_rejected():
    prior, paper = good_items()
    rewrite(paper,"paper_evidence_json","paper_sha256",
            lambda obj: obj["row"].update(signal_date="2026-10-07"))
    with pytest.raises(ValueError, match="PAPER_NOT_FROM_PREVIOUS"):
        verify_pair(DAY, prior, paper)


def test_rehashed_wrong_prior_weights_are_rejected():
    prior, paper = good_items()
    rewrite(paper,"paper_evidence_json","paper_sha256",
            lambda obj: obj["row"].update(target_tqqq_weight=0.5))
    with pytest.raises(ValueError, match="TARGET_MISMATCH:tqqq"):
        verify_pair(DAY, prior, paper)


def test_rehashed_wrong_trade_signal_date_is_rejected():
    prior, paper = good_items()
    rewrite(paper,"paper_evidence_json","paper_sha256",
            lambda obj: obj["trs"][1].update(signal_date="2026-10-07"))
    with pytest.raises(ValueError, match="TRADE_NOT_FROM_PREVIOUS"):
        verify_pair(DAY, prior, paper)


@pytest.mark.parametrize("side,wrong_time", [("BUY","09:31"), ("SELL","09:32")])
def test_rehashed_wrong_trade_execution_time_is_rejected(side, wrong_time):
    prior, paper = good_items()
    def change(obj):
        obj["trs"][0]["side"] = side
        obj["trs"][0]["time_et"] = wrong_time
    rewrite(paper,"paper_evidence_json","paper_sha256", change)
    with pytest.raises(ValueError, match="TRADE_WINDOW_MISMATCH"):
        verify_pair(DAY, prior, paper)


def test_archived_previous_signal_after_open_is_rejected():
    prior, paper = good_items()
    prior["recorded_at_utc"] = {"S":"2026-10-09T14:00:00Z"}
    with pytest.raises(ValueError, match="AFTER_NEXT_OPEN"):
        verify_pair(DAY, prior, paper)


def test_wrong_source_or_pretend_broker_fill_is_rejected():
    prior, paper = good_items()
    rewrite(prior,"signal_json","signal_sha256",
            lambda obj: obj.update(signal_source="TQQQ_SYNTHETIC"))
    with pytest.raises(ValueError, match="INVALID_SIGNAL_SOURCE"):
        verify_pair(DAY, prior, paper)
    prior, paper = good_items()
    paper["broker_fills_observed"]["BOOL"] = True
    with pytest.raises(ValueError, match="FALSE_OBSERVED_BROKER_FILLS"):
        verify_pair(DAY, prior, paper)
