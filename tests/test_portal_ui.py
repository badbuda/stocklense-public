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
