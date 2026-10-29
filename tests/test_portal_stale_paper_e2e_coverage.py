"""Keep browser-rendering and public Paper operational freshness separately fail-closed."""
from pathlib import Path

SCRIPT=Path("tests/portal_browser_smoke.cjs").read_text()


def test_paper_staleness_remains_visibly_red_and_operational_gate_fails():
    assert "PUBLISHED_PAPER_ARCHIVE_STALE:" in SCRIPT
    assert "failures.push(reason)" not in SCRIPT
    assert "PORTAL_ARCHIVAL_PAPER_DEGRADED_EXPECTED" in SCRIPT
    gate=Path("portal_publication_readiness.py").read_text()
    workflow=Path(".github/workflows/portal-operational-readiness.yml").read_text()
    assert "PUBLISHED_PAPER_ARCHIVE_STALE:paper=" in gate
    assert "return 2" in gate
    assert "StockLens 8.0 Shadow" in workflow
    assert "Stale Paper must be explicitly disclosed" in SCRIPT
    assert "Stale Paper archive must render a visible error state" in SCRIPT
    assert "assert.deepEqual(failures,[]" in SCRIPT
    assert "assert.equal(governance.paperSession,governance.signalSession" not in SCRIPT


def test_mobile_and_simulator_are_exercised_with_stale_warning_visible():
    assert SCRIPT.index("PUBLISHED_PAPER_ARCHIVE_STALE:") < SCRIPT.index("sim-form button[type=submit]")
    assert SCRIPT.index("sim-form button[type=submit]") < SCRIPT.index("mobile.locator('#menu-toggle')")
    assert SCRIPT.index("mobile.locator('#menu-toggle')") < SCRIPT.index("assert.deepEqual(failures,[]")


def test_history_and_risk_freshness_still_hard_fail():
    assert "assert.equal(governance.historySession,governance.signalSession" in SCRIPT
    assert "assert.equal(governance.riskSession,governance.signalSession" in SCRIPT


def test_stale_health_state_is_explicitly_red_not_falsely_verified():
    assert "if(paperArchiveStale)" in SCRIPT
    assert "Health dashboard must explain stale Paper mismatch" in SCRIPT
    assert "Health dashboard must show the actual archived Paper session" in SCRIPT
    assert "Healthy matching sources must be labeled verified" in SCRIPT
