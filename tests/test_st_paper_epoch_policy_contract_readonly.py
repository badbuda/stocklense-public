"""Safe deployed private Paper and Watchdog AST contract, no source leaks."""
from __future__ import annotations
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile
import pytest

from infra.aws import st_paper_epoch_policy_contract_readonly as m


PAPER = b'''
def handler(event, context):
    if event.get("mode") == "STAGING_PAPER_SCHEDULE_READINESS":
        return audit_paper_schedule_readiness(event)
def verify_book_chain():
    raise RuntimeError("SESSION_WITHOUT_CONTINUITY_RECORD")
def run_paper_catchup():
    return verify_book_chain()
def audit_paper_schedule_readiness(event):
    return {"status":"STAGING_PAPER_SCHEDULE_READINESS_PASS_READ_ONLY"}
'''
WATCHDOG = b'''
def handler(event, context):
    return watchdog()
def watchdog():
    if "MISSED_UNRECOVERABLE":
        return {"epoch":1,"status":"FAIL_CLOSED"}
'''


def test_module_allowlist_does_not_allow_traversal_or_foreign_paths():
    assert m.approved_module("infra.aws.independent_paper")
    assert m.approved_module("infra.aws.independent_staging_watchdog")
    assert not m.approved_module("infra.aws.__private__.deeper")
    assert not m.approved_module("infra.aws../secret")
    assert not m.approved_module("outside.private_watchdog")


def test_ast_summary_only_safe_function_and_literal_names():
    private = PAPER+b'\nSECRET="X_AMAZON_SECRET"\n'
    summary=m.ast_summary(private,"infra.aws.independent_paper")
    assert summary["private_source_printed"] is False
    assert summary["handler_function_present"] is True
    assert "SESSION_WITHOUT_CONTINUITY_RECORD" in summary["module_known_literal_vocabulary"]
    catchup=next(x for x in summary["selected_functions"] if x["name"]=="run_paper_catchup")
    assert catchup["direct_calls_to_known_contract_functions"]==["verify_book_chain"]
    assert "X_AMAZON_SECRET" not in json.dumps(summary)


def test_paper_and_watchdog_source_bound_to_one_exact_archive(monkeypatch):
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w") as z:
        z.writestr("infra/aws/independent_paper.py",PAPER)
        z.writestr("infra/aws/independent_staging_watchdog.py",WATCHDOG)
    archive=b.getvalue()
    monkeypatch.setattr(m.release,"NEW",
        base64.b64encode(hashlib.sha256(archive).digest()).decode())
    monkeypatch.setattr(m.release.p,"ENTRY_BLOB",
        m.release.p.git_blob_sha(PAPER))
    got=m.contracts_from_verified_archive(
        archive,["infra.aws.independent_paper","infra.aws.independent_staging_watchdog"])
    assert all(v["status"]=="VERIFIED_PACKAGE_PRIVATE_AST_SUMMARY"
               for v in got.values())
    assert got["infra.aws.independent_staging_watchdog"][
        "handler_function_present"] is True
    assert "MISSED_UNRECOVERABLE" in got["infra.aws.independent_staging_watchdog"][
        "module_known_literal_vocabulary"]
    assert "X_AMAZON_SECRET" not in json.dumps(got)
    with pytest.raises(RuntimeError,match="DEPLOYED_ARCHIVE_SHA_MISMATCH"):
        m.contracts_from_verified_archive(archive+b"tamper",
             ["infra.aws.independent_paper"])


def test_missing_watcher_module_never_claims_source_supported(monkeypatch):
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w") as z:
        z.writestr("infra/aws/independent_paper.py",PAPER)
    archive=b.getvalue()
    monkeypatch.setattr(m.release,"NEW",
        base64.b64encode(hashlib.sha256(archive).digest()).decode())
    monkeypatch.setattr(m.release.p,"ENTRY_BLOB",
        m.release.p.git_blob_sha(PAPER))
    report=m.contracts_from_verified_archive(
        archive,["infra.aws.independent_paper","infra.aws.independent_staging_watchdog"])
    assert report["infra.aws.independent_staging_watchdog"]["status"]==(
        "MODULE_NOT_IN_RELEASE_ARCHIVE_UNVERIFIED")


def test_full_inspection_only_after_verified_release_and_in_memory_handler(monkeypatch):
    monkeypatch.setattr(m.release,"check_readonly",lambda c:{
        "current_all_candidate":True,"mixed_or_partial_code":False,
        "prod_schedules_all_disabled":True,
        "blocked_cfn_change_set":{"status":"RETIRED_NOT_EXECUTED"}})
    monkeypatch.setattr(m.release,"trusted_inventory",lambda c:(
        {"st_outputs":{
            "CandidatePaperFunctionName":"stocklens-st-paper-candidate",
            "CandidateSessionWatchdogFunctionName":"stocklens-st-session-watchdog"
        }},
        {"stocklens-st-paper-candidate":{"CodeSha256":m.release.NEW},
         "stocklens-st-session-watchdog":{"CodeSha256":m.release.NEW,
                "Handler":"infra.aws.independent_staging_watchdog.handler"}},
        {}
    ))
    class FakeLambda:
        def get_function(self,**kwargs):
            return {"Configuration":{"CodeSha256":m.release.NEW},
                    "Code":{"Location":"https://signed.aws.example/zip"}}
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):return None
        def read(self,n):return b"mock"
    monkeypatch.setattr("urllib.request.urlopen",lambda *_a,**_kw: Response())
    monkeypatch.setattr(m,"contracts_from_verified_archive",lambda *_a:{
        "infra.aws.independent_paper":{"status":"VERIFIED_PACKAGE_PRIVATE_AST_SUMMARY"},
        "infra.aws.independent_staging_watchdog":{"status":"VERIFIED_PACKAGE_PRIVATE_AST_SUMMARY"}})
    report=m.inspect({"lambda":FakeLambda()})
    assert report["all_five_st_new_code_verified"] is True
    assert report["governance"]["aws_mutations"] is False
    assert report["governance"]["new_epoch_authorized"] is False
    assert report["governance"]["lambda_invoked"] is False
    assert report["governance"]["source_disclosed"] is False


def test_full_inspection_rejects_stale_lambda_before_private_download(monkeypatch):
    monkeypatch.setattr(m.release,"check_readonly",lambda c:{
        "current_all_candidate":False,"mixed_or_partial_code":True,
        "prod_schedules_all_disabled":True,
        "blocked_cfn_change_set":{"status":"RETIRED_NOT_EXECUTED"}})
    with pytest.raises(RuntimeError,match="EXPECTED_VERIFIED_ST_RELEASE_MISSING"):
        m.inspect({})


def test_source_contains_no_mutating_services():
    source=Path("infra/aws/st_paper_epoch_policy_contract_readonly.py").read_text()
    for banned in (".invoke(", ".put_object(", ".delete_object(", ".put_item(",
                   ".update_function_code(", ".update_stack(",
                   ".set_alarm_state(", ".execute_change_set(", ".disable_rule(",
                   ".enable_rule(", ".create_change_set("):
        assert banned not in source
