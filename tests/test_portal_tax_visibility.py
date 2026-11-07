"""Cross-dashboard tax signal is visible, proven or explicitly blocked everywhere."""
from pathlib import Path
import subprocess
from html.parser import HTMLParser


class Ids(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
    def handle_starttag(self, tag, attrs):
        value = dict(attrs).get("id")
        if value:
            assert value not in self.ids, "duplicate id: " + value
            self.ids.add(value)


def test_tax_panels_cover_all_existing_stocklens_screens():
    html = Path("docs/portal.html").read_text(encoding="utf-8")
    p = Ids()
    p.feed(html)
    needed = {
        "tax-global-signal", "tax-overview-panel", "tax-overview-net",
        "tax-hero-signal", "tax-paper-panel", "tax-paper-assessed",
        "tax-performance-panel", "tax-performance-status",
        "tax-sim-panel", "tax-sim-strategy", "tax-sim-qqq", "tax-sim-paid", "tax-sim-chart",
        "tax-research-panel", "tax-evidence-panel", "tax-evidence-status"
    }
    assert needed <= p.ids
    assert all(f'data-view="{page}"' in html for page in
               ("overview", "paper", "performance", "simulator", "research", "evidence"))
    assert html.count('class="panel tax-panel"') >= 6


def test_public_site_defaults_to_blocked_tax_not_fake_after_tax_nav():
    import json
    feed = json.loads(Path("docs/tax-status.json").read_text())
    assert feed["kind"] == "STOCKLENS_TAX_STATUS_V1"
    assert feed["status"] == "BLOCKED"
    assert feed["gross_paper_nav_usd"] is None
    assert feed["estimated_after_tax_liquidation_usd"] is None
    assert feed["fx_verified"] is False
    assert feed["lot_history_verified"] is False
    assert feed["broker_withholding_verified"] is False
    js = Path("docs/portal.js").read_text()
    cloud = Path("docs/portal-cloud.js").read_text()
    assert "taxFeedView(feed,currentSession,sourceEquity)" in js
    assert "state.privateTax||state.tax" in js
    assert "renderTaxPanels()" in js
    assert "onTaxChange:report=>" in js
    assert "'/v1/tax?date='" in cloud
    assert "Authorization:'Bearer '+accessToken" in cloud
    assert "stagingSnapshot(response.sessions).paper?.session_date" in cloud
    assert "await refreshPrivateTax(aligned).catch(()=>taxUpdated(null));" in cloud


def test_tax_math_is_reproducible_and_fail_closed():
    subprocess.run(["node", "tests/portal_tax_unit.mjs"], check=True)
    for file in ("docs/portal.js", "docs/portal-cloud.js", "docs/portal-tax.mjs"):
        subprocess.run(["node", "--check", file], check=True)
