"""Read-only ST Paper source and S3 receipt forensics regression tests."""
import base64
import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

import pytest

from infra.aws import st_paper_recovery_readonly as m


def make_zip(paper=None, entry=b"def handler(event, context): pass\n"):
    if paper is None:
        paper = Path("stocklens/paper.py").read_bytes()
    buf = io.BytesIO()
    with ZipFile(buf, "w") as z:
        z.writestr("stocklens/paper.py", paper)
        z.writestr("infra/aws/independent_paper.py", entry)
    return buf.getvalue()


def code_sha(data):
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


def test_original_source_exact_git_blob_and_zip_proof():
    raw = Path("stocklens/paper.py").read_bytes()
    assert m.git_blob_sha(raw) == m.VERIFIED_PUBLIC_PAPER_GIT_BLOB
    packed = make_zip(raw)
    evidence = m.inspect_archive(packed, code_sha(packed))
    assert evidence["zip_sha256_matches_lambda"] is True
    assert evidence["paper_entrypoint_in_zip"] is True
    assert evidence["paper_engine_in_zip"] is True
    assert evidence["engine_matches_verified_github_fix"] is True
    assert evidence["paper_engine_git_blob"] == m.VERIFIED_PUBLIC_PAPER_GIT_BLOB
    assert evidence["entrypoint_git_blob"] is not None


def test_wrong_zip_sha_never_claims_source_parity():
    packed = make_zip()
    with pytest.raises(RuntimeError, match="DEPLOYED_ZIP_SHA256_MISMATCH"):
        m.inspect_archive(packed, "not-the-real-code-sha")


def test_deployed_old_paper_source_is_not_called_fixed():
    packed = make_zip(b"# historic, missing retry\n")
    evidence = m.inspect_archive(packed, code_sha(packed))
    assert evidence["engine_matches_verified_github_fix"] is False


def test_source_missing_in_zip_is_reported_not_assumed_present():
    buf = io.BytesIO()
    with ZipFile(buf, "w") as z:
        z.writestr("README.txt", "not source")
    packed = buf.getvalue()
    report = m.inspect_archive(packed, code_sha(packed))
    assert report["paper_engine_in_zip"] is False
    assert report["paper_entrypoint_in_zip"] is False
    assert report["engine_matches_verified_github_fix"] is False


class HeadError(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code}}


class FakeS3:
    def get_bucket_versioning(self, *, Bucket):
        assert Bucket == m.ST_BUCKET
        return {"Status": "Enabled"}

    def head_object(self, *, Bucket, Key):
        assert Bucket == m.ST_BUCKET
        if Key.endswith("genesis.json") or Key.startswith("signals/"):
            return {"VersionId": "immutable-v1", "ContentLength": 123}
        raise HeadError("404")


def test_only_404_counts_missing_not_access_denied():
    class Denied:
        def head_object(self, *, Bucket, Key):
            raise HeadError("AccessDenied")
    assert m.s3_head(Denied(), m.ST_BUCKET, "paper/sessions/x.json")["status"] == "READ_UNVERIFIED"
    assert m.s3_head(FakeS3(), m.ST_BUCKET, "paper/sessions/x.json")["status"] == "NOT_FOUND"


class FakeSTS:
    def get_caller_identity(self):
        return {"Account": m.ACCOUNT}


class FakeCF:
    def describe_stacks(self, *, StackName):
        bucket = m.ST_BUCKET if StackName == m.ST_STACK else m.PROD_BUCKET
        return {"Stacks": [{"StackStatus": "UPDATE_COMPLETE", "Outputs": [
            {"OutputKey": "CandidateDataBucket", "OutputValue": bucket},
            {"OutputKey": "CandidatePaperFunctionName", "OutputValue": m.ST_STACK + "-paper-candidate"},
            *[
                {"OutputKey": x, "OutputValue": StackName + "-" + x}
                for x in ("CandidateSignalOnlyRuleName", "CandidatePaperOnlyRuleName",
                          "CandidateOrchestratorRuleName")
            ]
        ]}]}


class FakeEvents:
    def describe_rule(self, *, Name):
        state = "DISABLED" if Name.startswith(m.PROD_STACK) or "Orchestrator" in Name else "ENABLED"
        return {"State": state}


def test_audit_reads_only_st_genesis_signal_and_gap_candidates():
    class NoInvocationsAllowed:
        def __getattr__(self, name):
            raise AssertionError("No Lambda calls or mutations expected: " + name)
    sdk = {"sts": FakeSTS(), "cloudformation": FakeCF(), "events": FakeEvents(),
           "s3": FakeS3(), "lambda": NoInvocationsAllowed()}
    out = m.audit(sdk, "2026-11-05", package_reader=lambda _:
                  {"status": "CODE_PROVENANCE_UNVERIFIED"})
    assert out["account_verified"] is True
    assert out["prod_schedules_all_disabled"] is True
    assert out["missing_or_unverified_receipts"] == ["paper_session", "paper_continuity"]
    assert out["qualified_paper_session"] is False
    assert out["versioned_candidate_receipts"]["signal"]["status"] == "VERSIONED_PRESENT"
    assert out["versioned_candidate_receipts"]["paper_genesis"]["status"] == "VERSIONED_PRESENT"
    assert out["lambda_invocations"] is False
    assert out["aws_mutations"] is False
    assert out["paper_backfill"] is False


def test_no_mutating_aws_methods_or_lambda_invoke():
    src = Path("infra/aws/st_paper_recovery_readonly.py").read_text()
    for forbidden in (".invoke(", ".put_object(", ".update_function_code(",
                      ".update_stack(", ".create_change_set(", ".set_alarm_state(",
                      ".enable_rule(", ".disable_rule(", ".delete_object("):
        assert forbidden not in src
