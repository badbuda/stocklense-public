"""Provider-sensitive hysteresis diagnostics: signal-only and no LEAN identity claims."""
import json
from pathlib import Path

from data_quality_summary import build_data_quality


def evaluate(tmp_path, monkeypatch, *, close, sma200):
    monkeypatch.chdir(tmp_path)
    for folder in ("output", "shadow_history", "research"):
        Path(folder).mkdir()
    Path("output/latest_signal.json").write_text(json.dumps({
        "latest":{"asof_date":"2026-10-09","features":{"close":close,"sma200":sma200}}
    }))
    Path("shadow_history/health.json").write_text('{"status":"GREEN"}')
    return build_data_quality()


def test_margin_near_upper_threshold_flags_source_sensitivity(tmp_path, monkeypatch):
    report=evaluate(tmp_path,monkeypatch,close=101.05,sma200=100.0)
    assert 4 < report["sma200_upper_hysteresis_margin_bps"] < 6
    assert report["sma200_upper_threshold_within_10bps"] is True
    assert report["sma200_threshold_diagnostic"]=="SOURCE_SENSITIVE_WITHIN_10BPS"
    assert report["sma200_threshold_data_source"]=="QQQ_ADJUSTED_SIGNAL_VENDOR_NOT_LEAN_PARITY"


def test_far_from_upper_threshold_has_no_false_warning(tmp_path, monkeypatch):
    report=evaluate(tmp_path,monkeypatch,close=110.,sma200=100.)
    assert report["sma200_upper_threshold_within_10bps"] is False
    assert report["lean_same_input_parity_proven"] is False


def test_invalid_signal_features_never_report_safe_margin(tmp_path, monkeypatch):
    report=evaluate(tmp_path,monkeypatch,close="nan",sma200=100.)
    assert report["sma200_upper_hysteresis_margin_bps"] is None
    assert report["sma200_upper_threshold_within_10bps"] is None
    assert report["sma200_threshold_diagnostic"]=="INSUFFICIENT_FEATURES"


def test_dashboard_shows_source_and_readiness_scope_without_broker_claim():
    source=Path(__file__).resolve().parents[1].joinpath("docs/portal.js").read_text()
    assert "sma200_upper_hysteresis_margin_bps" in source
    assert "SHADOW_SIGNAL_PIPELINE_ONLY" in source
    assert "לא bid/ask" in source
    assert "מסחר חסום" in source
