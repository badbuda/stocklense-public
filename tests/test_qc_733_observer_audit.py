"""QC observer audit remains fail-closed regardless of matching feature chart."""
import csv
from unittest.mock import patch

from qc_733_observer_audit import evaluate


def _fixture(tmp_path, tamper=False):
    p=tmp_path/"observer.csv"
    with p.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=("date","close","sma50","sma200","vol20","mom12","level","defense","leverage"))
        writer.writeheader()
        writer.writerow({"date":"2020-01-02","close":120,"sma50":115,"sma200":100,
                         "vol20":0.2,"mom12":0.2,"level":2 if tamper else 3,
                         "defense":"false","leverage":2 if tamper else 3})
    return p


def test_matching_observer_does_not_prove_native_source(tmp_path):
    p=_fixture(tmp_path)
    with patch("qc_733_observer_audit.validate_export",return_value={"status":"VALID"}):
        out=evaluate(p)
    assert out["observer_math_parity"] is True
    assert out["matched_sessions"]==1
    assert out["source_authenticity_proven"] is False
    assert out["original_724_source_identity_proven"] is False
    assert out["lean_to_yahoo_feature_parity_proven"] is False
    assert out["live_trading_authorized"] is False


def test_mismatch_is_not_promoted(tmp_path):
    p=_fixture(tmp_path,tamper=True)
    with patch("qc_733_observer_audit.validate_export",return_value={"status":"VALID"}):
        out=evaluate(p)
    assert out["status"]=="OBSERVER_733_SAME_INPUT_MISMATCH"
    assert out["mismatched_sessions"]==1


def test_invalid_immutable_reference_blocks(tmp_path):
    p=_fixture(tmp_path)
    with patch("qc_733_observer_audit.validate_export",return_value={"status":"INVALID","errors":["FROZEN_DAILY_STATE_SHA_DRIFT"]}):
        out=evaluate(p)
    assert out["status"]=="BLOCKED_INVALID_OR_INCOMPLETE_OBSERVER"
    assert out["compared_sessions"]==0
