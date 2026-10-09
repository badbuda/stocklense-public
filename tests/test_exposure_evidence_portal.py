"""Evidence publication regression: avoid 7.25% transition index as daily parity."""
import json
from pathlib import Path


def test_portal_exposure_evidence_is_bounded():
    raw=json.loads(Path("docs/lean-exposure-evidence.json").read_text())
    assert raw["overlap_sessions"] == 3662
    assert raw["matching_exposures"] == 3655
    assert raw["different_exposures"] == 7
    assert abs(raw["daily_exposure_match_rate"]-3655/3662)<1e-12
    assert raw["full_same_input_parity_proven"] is False
    assert raw["original_lean_input_features_proven"] is False
    assert raw["broker_fills_proven"] is False
    assert raw["provenance"]["original_daily_date_leverage_sha256"]


def test_portal_renders_evidence_without_claiming_input_parity():
    code=Path("docs/portal.js").read_text()
    assert "lean-exposure-evidence.json" in code
    assert "exposureEvidenceTag()" in code
    assert "e.full_same_input_parity_proven===false" in code
    assert "התאמה בחשיפה בלבד" in code
    assert "זהות קלט ומחירי ביצוע" in code


def test_quality_feed_keeps_distinct_metric_names():
    code=Path("data_quality_summary.py").read_text()
    assert '"lean_yahoo_daily_exposure_match_rate"' in code
    assert '"qc_transition_index_alignment_diagnostic"' in code
    assert '"lean_same_input_parity_proven":False' in code
