"""Static product contract for the new StockLens Hebrew dashboard."""
from html.parser import HTMLParser
from pathlib import Path

P=Path("docs/portal.html")
JS=Path("docs/portal.js")
CSS=Path("docs/portal.css")
INDEX=Path("docs/index.html")
AMPLIFY=Path("amplify.yml")


class Portal(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=set()
        self.pages=set()
        self.scripts=[]
    def handle_starttag(self,tag,attrs):
        props=dict(attrs)
        if props.get("id"):
            assert props["id"] not in self.ids,"duplicate ID: "+props["id"]
            self.ids.add(props["id"])
        if props.get("data-view"):
            self.pages.add(props["data-view"])
        if tag=="script":
            self.scripts.append(props.get("src",""))


def test_primary_screens_are_reachable_and_static_assets_available():
    p=Portal();p.feed(P.read_text(encoding="utf-8"))
    assert p.pages=={"overview","paper","performance","simulator","research","evidence"}
    for need in ("sim-initial","sim-monthly","sim-start","sim-end","sim-chart",
                 "trades-body","performance-chart","years-body","research-list"):
        assert need=="research-list" or need in p.ids
    assert "./portal.js" in p.scripts
    assert P.read_text().count('data-page=')>=6
    assert 'href="./portal.css"' in P.read_text()


def test_default_dashboard_is_new_portal_but_old_ui_remains_available():
    assert "location.replace('./portal.html'" in INDEX.read_text()
    assert "has('legacy')" in INDEX.read_text()
    assert 'index.html?legacy=1' in P.read_text()


def test_simulator_uses_observed_tqqq_and_never_multiplies_qqq_to_fake_price():
    src=JS.read_text()
    assert "observed_ohlc_available" in src
    assert "REAL_QQQ" not in src or "portal-history.json" in src
    assert "simulateRealETF" in src
    assert "slip/10000" in src
    assert "Number(r.to)" in src
    assert "Number(r.tc)" not in src or "Number(r[k])" in src
    assert "broker" in src.lower()
    assert "downloadCSV" in src


def test_amplify_hosts_docs_as_prebuilt_static_site():
    cfg=AMPLIFY.read_text()
    assert "baseDirectory: docs" in cfg
    assert "portal-history.json" in cfg
    assert "'**/*'" in cfg
    assert "AWS_ACCESS_KEY" not in cfg


def test_ui_is_responsive_and_readable():
    html=P.read_text()
    css=CSS.read_text()
    assert 'lang="he"' in html and 'dir="rtl"' in html
    assert '@media(max-width:660px)' in css
    assert 'data-view="simulator"' in html
    assert 'aria-label' in html


def test_secure_aws_and_scenario_panels_are_present():
    html=P.read_text(encoding='utf-8')
    src=JS.read_text(encoding='utf-8')
    for element in ('paper-trade-detail','journal-gap-list','cloud-login','cloud-load',
                    'scenario-b-form','scenario-compare-chart','scenario-compare-body'):
        assert f'id="{element}"' in html
    assert "'./portal-insights.js'" in src
    assert "'./portal-cloud.js'" in src
    assert 'dynamodb:GetItem' in Path('infra/aws/portal-readonly-api.yaml').read_text()


def test_cognito_module_is_unique_and_not_truncated():
    src=Path("docs/portal-cloud.js").read_text(encoding="utf-8")
    assert src.count("export function initCloudJournal(")==1
    assert src.count("export async function refreshCloudJournal(")==1
    assert src.count("function validateConfig(")==1
    assert src.count("const b64=")==1
    assert src.count("const money=")==1
    assert not any(line.strip().startswith("+new Intl.NumberFormat(") for line in src.splitlines())
    assert "const money=x=>" in src
    assert src.rstrip().endswith("}")


def test_portal_displays_real_forward_loss_and_blocks_false_ready_claims():
    html=P.read_text(encoding="utf-8")
    js=JS.read_text(encoding="utf-8")
    for element in ("readiness-clarity","readiness-message","real-paper-sessions",
                    "research-session-count","real-paper-return","real-paper-baseline",
                    "model-parity-state","capital-readiness-details"):
        assert f'id="{element}"' in html
    assert "renderGovernance(d)" in js
    assert "technical_checks_pass===true" in js
    assert "automatic_trading_authorized===true" in js
    assert "full_lean_execution_parity===true" in js
    assert "latest.cumulative_return" in js
    assert "original/(1+cum)" in js
    assert "prospective_completed_sessions" in js
    assert "performance מראה" in js
    assert "מניית TQQQ אחת" in js


def test_published_snapshot_contains_separate_evidence_types():
    import json
    data=json.loads(Path("docs/data.json").read_text(encoding="utf-8"))
    paper=data["paper"]
    capital=data["capital_readiness"]
    assert paper["sessions"] != capital["prospective_completed_sessions"]
    assert float(paper["latest"]["cumulative_return"]) < 0
    assert not capital["technical_checks_pass"]
    assert not capital["full_lean_execution_parity"]
    assert not capital["automatic_trading_authorized"]



def test_optional_private_aws_api_is_explicitly_disabled_by_default():
    import json
    config=json.loads(Path("docs/cloud-config.json").read_text(encoding="utf-8"))
    assert config["enabled"] is False
    assert config.get("api_base_url") is None
    assert config.get("cognito_domain") is None
    assert config.get("client_id") is None
    assert not any("secret" in key.lower() for key in config)



def test_site_exposes_latest_session_coherence_and_shadow_only_fallback():
    js=JS.read_text(encoding="utf-8")
    for code in ("paper.latest?.session_date", "updated_session", "state.risk?.period?.end",
                 "sessionCoherent", "תאריך נתוני האתר", "observational_only===true",
                 "fallbackMargin"):
        assert code in js
    # Never claim absent/lagged JSON is 'green'.
    assert "sessionCoherent?'מאומת" in js
    assert "פער תאריכים" in js


def test_production_browser_gate_compares_exact_deployed_data_and_code_hashes():
    workflow=Path(".github/workflows/portal-browser-smoke.yml").read_text()
    for asset in ("portal.html", "portal.js", "portal-insights.js",
                  "data.json", "timeseries.json", "portal-history.json",
                  "observed_tqqq_risk_audit.json"):
        assert asset in workflow
    assert "AMPLIFY_ALL_SEVEN_ASSET_SHA_MATCH=PASS" in workflow
    assert 'expected="$(sha256sum "docs/$asset"' in workflow
    assert "AMPLIFY_ASSET_SHA_MISMATCH" in workflow
    browser=Path("tests/portal_browser_smoke.cjs").read_text()
    for field in ("signalSession", "paperSession", "historySession", "riskSession"):
        assert field in browser
    assert "Paper is stale versus published signal" in browser
    assert "Historical ETF feed is stale" in browser
    assert "Risk cohort is stale" in browser
