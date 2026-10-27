"""A successful frozen Shadow publication must be followed by actual Amplify E2E."""
from pathlib import Path

W = Path(".github/workflows/portal-browser-smoke.yml").read_text()


def test_shadow_success_triggers_real_browser_verification():
    assert 'workflow_run:' in W
    assert 'workflows: ["StockLens 8.0 Shadow"]' in W
    assert 'types: [completed]' in W
    assert "github.event.workflow_run.conclusion == 'success'" in W
    assert 'aws' in W and 'PORTAL_BASE_URL: https://main.d20nvlvzjafg5m.amplifyapp.com' in W


def test_browser_checks_exact_production_inputs():
    assert 'sha256sum "docs/$asset"' in W
    assert 'curl -fLsS --max-time 15' in W
    for path in ("data.json", "timeseries.json", "portal-history.json",
                 "cloud-config.json", "portal.js", "portal-live.mjs",
                 "observed_tqqq_risk_audit.json"):
        assert path in W
    assert "Verify local build in desktop and mobile Chromium" in W
    assert "Verify actual AWS Amplify deployed website" in W
