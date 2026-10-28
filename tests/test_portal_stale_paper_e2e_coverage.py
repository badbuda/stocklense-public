"""The actual browser test must inspect the UI before failing on stale archived Paper."""
from pathlib import Path

SCRIPT=Path("tests/portal_browser_smoke.cjs").read_text()


def test_paper_staleness_remains_red_but_is_deferred():
    assert "PUBLISHED_PAPER_ARCHIVE_STALE:" in SCRIPT
    assert "failures.push(reason)" in SCRIPT
    assert "Stale Paper must be explicitly disclosed" in SCRIPT
    assert "Stale Paper archive must render a visible error state" in SCRIPT
    assert "assert.deepEqual(failures,[]" in SCRIPT
    assert "assert.equal(governance.paperSession,governance.signalSession" not in SCRIPT


def test_mobile_and_simulator_are_exercised_before_final_red_verdict():
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
