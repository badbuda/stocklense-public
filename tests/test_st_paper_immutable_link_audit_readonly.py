"""Review original immutable Paper links without trusting missing date receipts."""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path

import pytest
from infra.aws import st_paper_immutable_link_audit_readonly as m


def sha(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


class S3:
    def __init__(self):
        self.data={}
        prev_paper=None
        prev_cont=None
        for date in m.SESSIONS[:4]:
            paper={
                "book":m.BOOK,"session":date,
                "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
                "broker_fills_observed":False,"broker_orders_authorized":False,
                "state":{"last_mark_session":date,"cash":10_000_000},
                "prior_receipt_sha256":prev_paper,
            }
            key=f"paper/sessions/{date}.json"
            self.data[key]=paper
            cont={
                "book":m.BOOK,"session":date,"status":"ON_TIME_QUALIFIED",
                "previous_record_sha256":prev_cont,
                "broker_orders":False,"broker_fills":False,
                "evidence":{"paper_sha256":sha(paper),"paper_version_id":"V1",
                            "paper_key":key},
            }
            self.data[f"paper/continuity/{date}.json"]=cont
            prev_paper=sha(paper)
            prev_cont=sha(cont)
        genesis={"book":m.BOOK,
            "receipt_sha256":sha(self.data["paper/sessions/2026-10-30.json"]),
            "continuity_sha256":sha(self.data["paper/continuity/2026-10-30.json"])}
        self.data[f"paper/book/{m.BOOK}/genesis.json"]=genesis

    def get_bucket_versioning(self, **k):
        assert k["Bucket"]==m.BUCKET
        return {"Status":"Enabled"}

    def head_object(self, **k):
        if k["Key"] not in self.data:
            raise ClientError("404")
        raw=json.dumps(self.data[k["Key"]],sort_keys=True).encode()
        return {"ContentLength":len(raw),"VersionId":"V1"}

    def get_object(self, **k):
        assert k["VersionId"]=="V1"
        raw=json.dumps(self.data[k["Key"]],sort_keys=True).encode()
        return {"VersionId":"V1","Body":io.BytesIO(raw)}


class ClientError(Exception):
    def __init__(self, code):
        self.response={"Error":{"Code":code}}


def test_four_exact_linked_record_pairs_and_missing_nov_dates():
    obj=m.chain_report(S3())
    assert obj["genesis"]["initial_paper_link"]=="MATCH"
    assert obj["genesis"]["initial_continuity_link"]=="MATCH"
    assert len(obj["stored_hash_linkage"])==3
    assert all(row["paper_prior_receipt_link"]=="MATCH" and
               row["continuity_previous_record_link"]=="MATCH"
               for row in obj["stored_hash_linkage"])
    assert obj["missing_dates"]==["2026-11-05","2026-11-06"]
    assert obj["original_economic_accounting_status"]=="NOT_ATTESTED_BY_HASH_LINKS"
    assert obj["no_broker_or_historical_backfill"] is True
    assert "10000000" not in json.dumps(obj)


def test_tampered_or_missing_link_is_reported_not_auto_repaired():
    s=S3()
    s.data["paper/sessions/2026-11-04.json"]["prior_receipt_sha256"]="0"*64
    result=m.chain_report(s)
    assert result["stored_hash_linkage"][-1]["paper_prior_receipt_link"]==(
        "DOES_NOT_MATCH_EXACT_STORED_BYTES")
    assert result["missing_dates"]==["2026-11-05","2026-11-06"]
    s.data["paper/continuity/2026-11-03.json"].pop("previous_record_sha256")
    result=m.chain_report(s)
    assert result["stored_hash_linkage"][1]["continuity_previous_record_link"]==(
        "MISSING_OR_INVALID_POINTER")


def test_lack_of_s3_bucket_versioning_blocks_all_claims():
    class Unversioned(S3):
        def get_bucket_versioning(self, **k):
            return {"Status":"Suspended"}
    with pytest.raises(RuntimeError,match="ST_BUCKET_VERSIONING_DISABLED"):
        m.chain_report(Unversioned())


def test_access_denied_not_misclassified_as_missing():
    class Denied(S3):
        def head_object(self, **k):
            if k["Key"].endswith("2026-11-05.json"):
                raise ClientError("403")
            return super().head_object(**k)
    with pytest.raises(RuntimeError,match="HEAD_FAILED_NOT_A_404"):
        m.chain_report(Denied())


def test_unexpected_version_or_body_length_blocks():
    class WrongVersion(S3):
        def get_object(self, **k):
            return {"VersionId":"WRONG", "Body":io.BytesIO(b"{}")}
    with pytest.raises(RuntimeError,match="GET_VERSION_NOT_PINNED"):
        m.chain_report(WrongVersion())


def test_all_release_and_prod_gates_before_s3_read(monkeypatch):
    monkeypatch.setattr(m.release,"check_readonly",lambda c:{
        "current_all_candidate":False,
        "mixed_or_partial_code":True,
        "prod_schedules_all_disabled":True,
        "blocked_cfn_change_set":{"status":"RETIRED_NOT_EXECUTED"}})
    with pytest.raises(RuntimeError,match="RELEASE_AUTHORITY_NOT_VERIFIED"):
        m.inspect({})


def test_read_only_full_report_does_not_claim_live_paper_success(monkeypatch):
    monkeypatch.setattr(m.release,"check_readonly",lambda c:{
        "current_all_candidate":True,
        "mixed_or_partial_code":False,
        "prod_schedules_all_disabled":True,
        "blocked_cfn_change_set":{"status":"RETIRED_NOT_EXECUTED"}})
    monkeypatch.setattr(m.release,"trusted_inventory",lambda c:(
        {"st_outputs":{"CandidatePaperFunctionName":"stocklens-st-paper-candidate"}},
        {},{"CandidateSignalOnlyRuleName":True}))
    monkeypatch.setattr(m.original,"inspect_private_contract",lambda a,b:{
        "status":"PINNED_PRIVATE_HANDLER_AST_READ_IN_MEMORY",
        "source_content_disclosed":False})
    result=m.inspect({"s3":S3(),"lambda":object()})
    assert result["private_runtime_contract"]["source_content_disclosed"] is False
    assert result["forward_epoch_transition"]=="NOT_AUTHORIZED_OR_IMPLEMENTED"
    assert result["aws_mutations"] is False
    assert result["lambda_invocations"] is False
    assert result["paper_backfill"] is False


def test_source_no_broker_and_aws_mutators():
    s=Path("infra/aws/st_paper_immutable_link_audit_readonly.py").read_text()
    forbidden=(
        ".invoke(", ".put_object(", ".delete_object(", ".put_item(",
        ".set_alarm_state(", ".execute_change_set(", ".update_function_code(",
        ".update_function_configuration(", ".enable_rule(", ".disable_rule(",
        ".update_stack(", ".delete_change_set(", ".create_change_set(",
    )
    for expression in forbidden:
        assert expression not in s
