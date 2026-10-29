"""Authenticated AWS Staging summaries must reach the visible dashboard."""
from pathlib import Path
import re
import subprocess

def test_private_staging_callback_has_defined_session_source():
    js=Path("docs/portal-cloud.js").read_text(encoding="utf-8")
    assert "stagingUpdated(response.sessions);" in js
    assert "stagingUpdated(rows);" not in js
    assert "const response=await r.json();" in js
    assert "Array.isArray(response.sessions)" in js
    assert "UNTRUSTED_STAGING_EVIDENCE" in js
    assert "production_cutover_authorized!==false" in js

def test_optional_authenticated_data_remains_private():
    js=Path("docs/portal-cloud.js").read_text(encoding="utf-8")
    assert "Authorization:'Bearer '+accessToken" in js
    assert "cache:'no-store'" in js
    assert "PRIVATE_VERSIONED_STAGING_S3" in js
    assert "full_chain_verified_by_portal!==false" in js

def test_portal_cloud_js_parses():
    subprocess.run(["node","--check","docs/portal-cloud.js"],check=True)
