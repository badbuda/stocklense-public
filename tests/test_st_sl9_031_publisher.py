"""Pinned AWS ST publisher cannot alter broker, PROD or schedules."""
import subprocess
from pathlib import Path

SCRIPT=Path("infra/aws/publish_st_sl9_031_results.sh")

def test_publisher_syntax():
    r=subprocess.run(["bash","-n",str(SCRIPT)],capture_output=True,text=True)
    assert r.returncode==0,r.stderr

def test_only_create_once_research_objects_and_explicit_confirmation():
    x=SCRIPT.read_text()
    assert "ACCOUNT=634740393398" in x
    assert "ST=stocklens-st" in x
    assert "BUCKET=stocklens-st-candidatedata-6jj7i9fxjmfr" in x
    assert 'REF=8fe5ebdb7f7e2d3a9bc6bc9109d2b2745aae9bea' in x
    assert 'if-none-match' in x
    assert "PUBLISH_ST_RESEARCH_ONLY" in x
    assert "source_independently_audited" in x
    assert "ST_READBACK_SHA_VERIFIED" in x
    assert "ST_SCHEDULE_ACTIVE_REFUSE" in x
    assert "s3api put-object" in x
    assert "delete-object" not in x
    assert "cloudformation update-stack" not in x
    assert "cloudformation delete-stack" not in x
    assert "lambda invoke" not in x
    assert "events enable-rule" not in x
    assert "sns publish" not in x
    assert "stocklens-prod" not in x
    assert "broker submit" not in x
