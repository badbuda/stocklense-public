import capital_readiness as cr


def _inputs(paper_sessions=0, paper_status="WAITING_FOR_NEXT_COMPLETED_SESSION"):
    pub = {
        "git_sha": "frozen-current",
        "replay_dataset_sha256": "d",
        "replay_rows_sha256": "r",
        "simulator_contract_sha256": "c",
        "generation_id": "g",
    }
    files = {
        "research/prospective/registry.json": {
            "last_ingestion_audit": [{
                "experiment_id": "SL9-007-UPSHIFT-CONFIRMATION",
                "accepted_completed_xnys_rows": 8,
                "persisted_prospective_rows": 8,
                "source_status": "AVAILABLE",
                "definition_matches_registration": True,
                "fingerprint_matches_registration": False,
                "gate": cr.PROSPECTIVE_GATE,
            }]
        },
        "docs/workbench_evidence_health.json": {
            "status": "HEALTHY", "market_session_freshness": "CURRENT",
            "market_session": {"signal_replay_aligned": True},
            "automatic_model_change": False, "automatic_promotion": False,
        },
        "shadow_history/execution_readiness.json": {"status": "READY"},
        "docs/simulator_smoke.json": {
            "accounting_invariants": {"status": "PASS"},
            "replay_dataset_sha256": "d", "replay_rows_sha256": "r",
            "contract_sha256": "c", "publication_identity": {"generation_id": "g"},
        },
        "docs/prospective_maturity.json": {
            "status": "PASS", "producer_current": True, "producer_git_sha": "frozen-current",
        },
        "docs/paper_forward_audit.json": {
            "paper_sessions": paper_sessions, "status": paper_status,
            "explicit_missed_sessions": 0, "errors": [],
            "backfill_authorized": False, "live_trading_authorized": False,
        },
    }
    return pub, files


def _evaluate(monkeypatch, tmp_path, paper_sessions, paper_status):
    pub, data = _inputs(paper_sessions, paper_status)
    monkeypatch.setattr(cr, "publication_identity", lambda: pub)
    monkeypatch.setattr(cr, "load", lambda path, default=None: data.get(path, default or {}))
    return cr.build(str(tmp_path / "readiness.json"))


def test_challenger_prospective_never_qualifies_frozen_baseline(monkeypatch, tmp_path):
    result = _evaluate(monkeypatch, tmp_path, 0, "WAITING_FOR_NEXT_COMPLETED_SESSION")
    assert result["prospective_completed_sessions"] == 8
    assert result["frozen_baseline_paper_sessions"] == 0
    assert result["limited_execution_observation_eligible"] is False
    assert result["stage"] == "SHADOW_ONLY"
    assert result["automatic_trading_authorized"] is False
    assert result["checks"]["frozen_baseline_paper_capture_verified"] is False


def test_verified_frozen_paper_count_can_unlock_observation_only(monkeypatch, tmp_path):
    result = _evaluate(monkeypatch, tmp_path, 5, "PROSPECTIVE_PAPER_ACTIVE")
    assert result["limited_execution_observation_eligible"] is True
    assert result["scaled_capital_ready"] is False
    assert result["automatic_trading_authorized"] is False


def test_missed_or_unverified_paper_must_never_qualify(monkeypatch, tmp_path):
    result = _evaluate(monkeypatch, tmp_path, 63, "MISSED_EXECUTION_REVIEW")
    assert result["limited_execution_observation_eligible"] is False
    assert result["stage"] == "SHADOW_ONLY"
