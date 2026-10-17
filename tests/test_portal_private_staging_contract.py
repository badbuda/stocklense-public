from pathlib import Path

def test_private_staging_portal_contract():
    template = Path("infra/aws/portal-readonly-api.yaml").read_text()
    js = Path("docs/portal-cloud.js").read_text()
    html = Path("docs/portal.html").read_text()
    assert "PortalApiId:" in template and "Value: !Ref JournalApi" in template
    assert "PortalAuthorizerId:" in template and "Value: !Ref JournalAuthorizer" in template
    assert "STOCKLENS_AUTHENTICATED_STAGING_S3_READ_ONLY" in js
    assert "full_chain_verified_by_portal!==false" in js
    assert "production_cutover_authorized!==false" in js
    assert "Authorization:'Bearer '+accessToken" in js
    assert "/v1/staging?dates=" in js
    assert "cloud-staging-results" in html
    assert "cloud-staging-load" in html
