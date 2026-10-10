import json
from operational_readiness import build_readiness
from data_quality_summary import build_data_quality

def test_shadow_ready_does_not_mean_broker_ready(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for directory in ("output", "shadow_history", "historical_replay", "governance"):
        (tmp_path / directory).mkdir()
    (tmp_path / "governance/qc_724_daily_state_manifest.json").write_text("{}")
    (tmp_path / "output/latest_signal.json").write_text(json.dumps({"latest":{"asof_date":"2026-10-09"},"action":"NO_CHANGE"}))
    (tmp_path / "shadow_history/health.json").write_text(json.dumps({"status":"GREEN"}))
    (tmp_path / "historical_replay/summary.json").write_text(json.dumps({"last_date":"2026-10-09"}))
    (tmp_path / "shadow_history/anomalies.json").write_text(json.dumps({"status":"CLEAR"}))
    r=build_readiness(str(tmp_path/"readiness.json"))
    assert r["status"]=="READY"
    assert r["scope"]=="SHADOW_SIGNAL_PIPELINE_ONLY"
    assert r["broker_execution_ready"] is False and r["capital_deployment_ready"] is False

def test_exposure_alignment_is_not_input_parity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for directory in ("output", "shadow_history", "research"):
        (tmp_path / directory).mkdir()
    (tmp_path / "output/latest_signal.json").write_text(json.dumps({"latest":{"asof_date":"2026-10-09"}}))
    (tmp_path / "shadow_history/qc_daily_parity.json").write_text(json.dumps({"status":"DATA_SOURCE_DRIFT"}))
    (tmp_path / "research/lean_yahoo_cross_provider_20261009.json").write_text(json.dumps({
        "status":"VERIFIED_CROSS_PROVIDER_EXPOSURE_ALIGNMENT_NOT_LEAN_INPUT_PARITY",
        "overlap_sessions":100,"matching_exposures":99,"daily_exposure_match_rate":0.99}))
    r=build_data_quality()
    assert r["qc_cross_provider_diagnostic"]=="EXPOSURE_ALIGNMENT_ONLY_NOT_LEAN_INPUT_PARITY"
    assert r["qc_original_transition_diagnostic"]=="DATA_SOURCE_DRIFT"
    assert r["lean_same_input_parity_proven"] is False

