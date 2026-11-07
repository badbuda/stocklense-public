"""No AWS writes: ST Paper source-verified local release candidate tests."""
import base64
import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

import pytest

from infra.aws import st_paper_prepare_review_zip as m


OLD = b"def _fetch_intraday(symbol,start,end):\n    return 42\n\ndef fetch_execution_market(signal,current):\n    return 42\n\ndef balance():\n    return 100\n"
FIX = b"def _fetch_intraday(symbol,start,end,*,expected_session=None):\n    return 43\n\ndef fetch_execution_market(signal,current):\n    return 43\n\ndef balance():\n    return 100\n"
HANDLER = b"def handler(event,context):\n    return 'PAPER'\n"


def fixtures(monkeypatch):
    monkeypatch.setattr(m,"OLD_ENGINE_BLOB",m.git_blob_sha(OLD))
    monkeypatch.setattr(m,"NEW_ENGINE_BLOB",m.git_blob_sha(FIX))
    monkeypatch.setattr(m,"ENTRY_BLOB",m.git_blob_sha(HANDLER))
    buf = io.BytesIO()
    with ZipFile(buf,"w") as z:
        z.writestr("other/critical_accounting.py",b"def calc(): return 100\n")
        z.writestr(m.PAPER_PATH,OLD)
        z.writestr(m.ENTRY_PATH,HANDLER)
    return buf.getvalue()


def test_patch_preserves_all_original_members_except_verified_paper_engine(monkeypatch):
    old = fixtures(monkeypatch)
    patched, proof = m.build_review_archive(old,FIX,m.sha256_b64(old))
    assert proof["only_changed_member"] == m.PAPER_PATH
    assert proof["handler_preserved"] is True
    assert proof["engine_git_blob"] == m.git_blob_sha(FIX)
    assert proof["candidate_sha256_b64"] == m.sha256_b64(patched)
    with ZipFile(io.BytesIO(old)) as b, ZipFile(io.BytesIO(patched)) as a:
        assert a.read(m.ENTRY_PATH) == b.read(m.ENTRY_PATH) == HANDLER
        assert a.read("other/critical_accounting.py") == b.read("other/critical_accounting.py")
        assert a.read(m.PAPER_PATH) == FIX
        assert a.namelist() == b.namelist()


def test_altered_private_handler_and_unaudited_engine_never_pass(monkeypatch):
    old = fixtures(monkeypatch)
    monkeypatch.setattr(m,"ENTRY_BLOB","0"*40)
    with pytest.raises(RuntimeError,match="PRIVATE_HANDLER_DIFFERS"):
        m.build_review_archive(old,FIX,m.sha256_b64(old))
    monkeypatch.setattr(m,"ENTRY_BLOB",m.git_blob_sha(HANDLER))
    monkeypatch.setattr(m,"OLD_ENGINE_BLOB","0"*40)
    with pytest.raises(RuntimeError,match="OLD_ENGINE_DIFFERS"):
        m.build_review_archive(old,FIX,m.sha256_b64(old))


def test_patch_may_not_change_other_accounting_code(monkeypatch):
    old = fixtures(monkeypatch)
    alt = FIX.replace(b"return 100",b"return 200")
    monkeypatch.setattr(m,"NEW_ENGINE_BLOB",m.git_blob_sha(alt))
    with pytest.raises(RuntimeError,match="UNEXPECTED_PAPER_STRATEGY_OR_ACCOUNTING_SOURCE_DIFF"):
        m.build_review_archive(old,alt,m.sha256_b64(old))


def test_invalid_zip_sha_blocks_even_when_members_are_exact(monkeypatch):
    old = fixtures(monkeypatch)
    with pytest.raises(RuntimeError,match="DEPLOYED_ZIP_NOT_SAME"):
        m.build_review_archive(old,FIX,"wrong")


class FakeSTS:
    def get_caller_identity(self):
        return {"Account":m.ACCOUNT}


class FakeCF:
    def describe_stacks(self,*,StackName):
        st = StackName==m.ST
        bucket = m.ST_BUCKET if st else m.PROD_BUCKET
        return {"Stacks":[{
            "StackStatus":"UPDATE_COMPLETE",
            "Outputs":[{"OutputKey":"CandidateDataBucket","OutputValue":bucket},
                       {"OutputKey":"CandidatePaperFunctionName",
                        "OutputValue":m.PAPER_FN}] +
                      [{"OutputKey":key,"OutputValue":StackName+"-"+key}
                       for key in m.RULES] +
                      [{"OutputKey":"CandidateFunctionName",
                        "OutputValue":m.ST+"-candidate"},
                       {"OutputKey":"CandidatePaperPreflightFunctionName",
                        "OutputValue":m.ST+"-paper-preflight"}],
            "Parameters":[
                {"ParameterKey":"ArtifactBucket","ParameterValue":"artifact-test"},
                {"ParameterKey":"ArtifactKey","ParameterValue":"releases/immutable-zip-v1.zip"},
                {"ParameterKey":"CandidateSignalScheduleState","ParameterValue":"DISABLED"},
                {"ParameterKey":"ExpectedSchedulerState","ParameterValue":"DISABLED"},
                {"ParameterKey":"MonitoringStartSession","ParameterValue":"2026-10-30"},
            ] if st else []
        }]}


class FakeEvents:
    def describe_rule(self,*,Name):
        return {"State":"DISABLED" if Name.startswith(m.PROD) or "Orchestrator" in Name
                else "ENABLED"}


class FakeS3:
    def __init__(self,zip_bytes):self.data=zip_bytes
    def head_object(self,*,Bucket,Key):
        assert Bucket=="artifact-test" and Key=="releases/immutable-zip-v1.zip"
        return {"ContentLength":len(self.data)}
    def get_object(self,*,Bucket,Key):
        return {"Body":io.BytesIO(self.data)}


class FakeLambda:
    def __init__(self,zip_bytes):self.data=zip_bytes
    def get_function(self,*,FunctionName):
        assert FunctionName==m.PAPER_FN
        return {
            "Configuration":{
                "FunctionName":FunctionName,"State":"Active",
                "LastUpdateStatus":"Successful","CodeSha256":m.sha256_b64(self.data),
                "Handler":"infra.aws.independent_paper.handler",
                "Environment":{"Variables":{"STOCKLENS_DATA_BUCKET":m.ST_BUCKET}},
            },
            "Code":{"Location":"https://example.test/private"},
        }
    def get_function_configuration(self,*,FunctionName):
        assert FunctionName in (m.ST+"-candidate",m.ST+"-paper-preflight")
        return {"CodeSha256":m.sha256_b64(self.data)}


def test_private_local_review_zip_never_writes_aws(monkeypatch,tmp_path):
    old=fixtures(monkeypatch)
    def remote(url,timeout):
        assert url=="https://example.test/private"
        return io.BytesIO(old)
    monkeypatch.setattr(m,"urlopen",remote)
    services={"sts":FakeSTS(),"cloudformation":FakeCF(),
              "events":FakeEvents(),"s3":FakeS3(old),
              "lambda":FakeLambda(old)}
    result=m.prepare_local_review_artifact(services,FIX,tmp_path)
    assert result["status"]=="LOCAL_ST_PAPER_REVIEW_PACKAGE_PREPARED_NO_DEPLOY"
    assert result["aws_mutations"] is False
    assert result["broker_orders"] is False
    assert result["deployment_authorized"] is False
    assert result["cloudformation_control_plane"]["cfn_schedule_parameter_vs_live_mismatch"] is True
    private_path=Path(result["private_local_zip"])
    assert private_path.is_file()
    assert private_path.stat().st_mode & 0o777 == 0o600
    assert private_path.parent.stat().st_mode & 0o777 == 0o700
    with ZipFile(private_path) as z:
        assert z.read(m.ENTRY_PATH)==HANDLER
        assert z.read(m.PAPER_PATH)==FIX


def test_no_live_mutating_methods():
    source=Path("infra/aws/st_paper_prepare_review_zip.py").read_text()
    for forbidden in (
        ".update_function_code(", ".create_change_set(", ".update_stack(",
        ".put_object(", ".invoke(", ".enable_rule(", ".disable_rule(",
        ".set_alarm_state(", ".execute_change_set(", ".delete_object("
    ):
        assert forbidden not in source
