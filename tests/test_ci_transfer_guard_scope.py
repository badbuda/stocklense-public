from ci_transfer_guard import in_scope


def test_generated_research_evidence_is_not_locked_source():
    outputs = [
        "research/reports/LATEST.md",
        "research/risk_overlay_deep_dive.json",
        "research/risk_overlay_multifactor.json",
        "research/yahoo_long_history.json",
        "research/yahoo_end_of_day_scorecard.json",
        "docs/site_health.json",
        "historical_replay/daily_states.csv",
        "paper_portfolio/ledger.csv",
        "paper_portfolio/trades.csv",
        "paper_portfolio/state.json",
        "paper_portfolio/latest.md",
        "paper_portfolio/latest_session.json",
    ]
    assert all(not in_scope(path) for path in outputs)


def test_governed_research_sources_remain_locked():
    sources = [
        "research/queue.json",
        "research/validation/challenger_dossiers.json",
        "research/AUTONOMY_STATE.json",
        "ci_transfer_guard.py",
        ".github/workflows/shadow.yml",
        "docs/index.html",
        "docs/workbench.html",
        "docs/portal.html",
        "docs/portal.css",
        "docs/portal.js",
        "docs/portal-insights.js",
        "docs/portal-cloud.js",
        "infra/aws/portal-journal-handler.py",
        "infra/aws/portal-readonly-api.yaml",
        "amplify.yml",
    ]
    assert all(in_scope(path) for path in sources)
