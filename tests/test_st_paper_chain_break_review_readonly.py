"""Immutable ST private handler & paper gap read-only evidence, no external AWS."""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

from infra.aws import st_paper_chain_break_review_readonly as m


class ClientError(Exception):
    def __init__(self, code):
        self.response={"Error":{"Code":code}}


class S3:
    def __init__(self):
        self.records={}
        for session in m.EXPECTED[:4]:
            self.records[f"paper/sessions/{session}.json"]={
                "session_date":session,
                "book":"NEW_AWS_INDEPENDENT_STAGING_BOOK",
                "state":{"cash":999_999_999,"last_mark_session":session}}
            self.records[f"paper/continuity/{session}.json"]={
                "session":session,"continuity_status":"ON_TIME_QUALIFIED",
                "audit":"no_broker"}
        self.records[f"paper/book/{m.BOOK}/genesis.json"]={
            "genesis_session":"2026-10-30",
            "state":{"cash":123_456,"shares":{"QQQ":42}}}
    def get_bucket_versioning(self, **kw):
        assert kw["Bucket"]==m.BUCKET
        return {"Status":"Enabled"}
    def head_object(self, *, Bucket, Key):
        assert Bucket==m.BUCKET
        if Key not in self.records:
            raise ClientError("404")
        raw=json.dumps(self.records[Key]).encode()
        return {"VersionId":"ver-"+Key,"ContentLength":len(raw)}
    def get_object(self, *, Bucket, Key, VersionId):
        assert VersionId=="ver-"+Key and Bucket==m.BUCKET
        raw=json.dumps(self.records[Key]).encode()
        return {"VersionId":VersionId, "Body":io.BytesIO(raw)}


def test_verified_s3_receipt_prints_schema_not_cash_holdings():
    s3=S3()
    key=f"paper/book/{m.BOOK}/genesis.json"
    evidence=m.receipt(s3,key)
    assert evidence["s3_version_verified"] is True
    assert evidence["status"]=="VERSIONED_JSON_READ_NOT_LEDGER_ACCEPTANCE"
    assert evidence["safe_identifiers"]["genesis_session"]=="2026-10-30"
    assert "cash" not in str(evidence)
    assert "123456" not in str(evidence)
    assert len(evidence["sha256"])==64


def test_missing_receipts_are_not_faked():
    s3=S3()
    key="paper/sessions/2026-11-05.json"
    assert m.receipt(s3,key)=={"status":"MISSING_VERIFIED_S3_KEY"}


def test_access_denied_or_unversioned_fails_closed():
    s3=S3()
    class DeniedS3(S3):
        def head_object(self,*,Bucket,Key):
            raise ClientError("AccessDenied")
    with pytest.raises(RuntimeError,match="S3_RECEIPT_HEAD_FAILED"):
        m.receipt(DeniedS3(),"paper/sessions/2026-11-05.json")
    class UnversionedS3(S3):
        def head_object(self,*,Bucket,Key):
            return {"VersionId":"null","ContentLength":20}
    with pytest.raises(RuntimeError,match="UNVERSIONED_RECEIPT"):
        m.receipt(UnversionedS3(),"paper/sessions/2026-11-05.json")


def test_private_handler_ast_summarizes_only_approved_mode_names(monkeypatch):
    private_code=b'''
def handler(event,context):
    secret="AWS_SECRET_ACCESS_KEY=SHOULD_NEVER_LEAK"
    mode=event.get("mode")
    if mode=="STAGING_PAPER_SCHEDULE_READINESS":
        return {"mode":"read_only"}
'''
    blob=m.release.p.git_blob_sha(private_code)
    monkeypatch.setattr(m.release.p,"ENTRY_BLOB",blob)
    zip_bytes=io.BytesIO()
    with zipfile.ZipFile(zip_bytes,"w") as z:
        z.writestr(m.release.p.ENTRY_PATH,private_code)
    archive=zip_bytes.getvalue()
    sha=base64.b64encode(hashlib.sha256(archive).digest()).decode()
    monkeypatch.setattr(m.release,"NEW",sha)
    output=m.private_contract_from_zip(archive)
    assert output["entrypoint_blob_verified"] is True
    assert output["known_mode_and_guard_literals_present"][
        "STAGING_PAPER_SCHEDULE_READINESS"] is True
    assert output["source_content_disclosed"] is False
    assert "SHOULD_NEVER_LEAK" not in str(output)
    with pytest.raises(RuntimeError,match="PRIVATE_RUNTIME_ARCHIVE_SHA_MISMATCH"):
        m.private_contract_from_zip(archive+b"extra")


def test_full_review_outputs_not_accounting_certification(monkeypatch):
    monkeypatch.setattr(m.release,"check_readonly",lambda _: {
        "current_all_candidate":True,"mixed_or_partial_code":False,
        "prod_schedules_all_disabled":True,
        "blocked_cfn_change_set":{"status":"RETIRED_NOT_EXECUTED"},
    })
    monkeypatch.setattr(m.release,"trusted_inventory",lambda _: (
        {"st_outputs":{"CandidatePaperFunctionName":"stocklens-st-paper-candidate"}},
        {},{}))
    monkeypatch.setattr(m,"inspect_private_contract",lambda *x: {
        "status":"PINNED_PRIVATE_HANDLER_AST_READ_IN_MEMORY",
        "source_content_disclosed":False})
    data=m.inspect({"s3":S3(),"lambda":object()})
    assert data["known_gap_needs_explicit_policy"] is True
    assert data["missing_by_date"]["2026-11-05"]==["sessions","continuity"]
    assert data["missing_by_date"]["2026-11-06"]==["sessions","continuity"]
    assert data["latest_qualified_Paper_book"]=="NOT_ATTESTED_FROM_STRUCTURAL_READS"
    assert data["paper_backfill"] is False
    assert data["lambda_invocations"] is False


def test_wrong_code_baseline_is_rejected(monkeypatch):
    monkeypatch.setattr(m.release,"check_readonly",lambda _: {
        "current_all_candidate":False,"mixed_or_partial_code":True,
        "prod_schedules_all_disabled":True,
        "blocked_cfn_change_set":{"status":"RETIRED_NOT_EXECUTED"},
    })
    with pytest.raises(RuntimeError,match="POST_DEPLOY_SECURITY_BASELINE_NOT_VERIFIED"):
        m.inspect({})


def test_source_has_no_mutating_aws_calls():
    source=Path("infra/aws/st_paper_chain_break_review_readonly.py").read_text()
    banned=(
        ".invoke(", ".put_object(", ".delete_object(", ".put_item(",
        ".set_alarm_state(", ".execute_change_set(", ".update_function_code(",
        ".update_function_configuration(", ".enable_rule(", ".disable_rule(",
        ".update_stack(", ".delete_change_set(", ".create_change_set(",
    )
    assert all(expr not in source for expr in banned)
    assert "urlopen(url" in source
    assert "source_content_disclosed" in source
