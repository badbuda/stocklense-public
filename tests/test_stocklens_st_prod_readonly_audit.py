"""Mocked AWS read-only control-plane acceptance; no AWS credentials."""
import hashlib
import pytest
from infra.aws.stocklens_st_prod_readonly_audit import (
    ACCOUNT, READ_ONLY, Blocked, aws, gitblob, inspect, inspect_stack, ENV
)

def stub(*args,account=ACCOUNT,rules_state="DISABLED",wrong_bucket=False):
    service,action,*rest=args
    if (service,action)==("sts","get-caller-identity"):
        return {"Account":account}
    if (service,action)==("cloudformation","describe-stacks"):
        name=rest[rest.index("--stack-name")+1]
        label=next(k for k,v in ENV.items() if v[0]==name)
        bucket=ENV[label][1] if not wrong_bucket else "malicious-unexpected-bucket"
        return {"Stacks":[{"StackStatus":"CREATE_COMPLETE",
            "Outputs":[{"OutputKey":"CandidateDataBucket","OutputValue":bucket}]+
             [{"OutputKey":k,"OutputValue":name+"-"+k} for k in
              ("CandidateSignalOnlyRuleName","CandidatePaperOnlyRuleName",
               "CandidateOrchestratorRuleName","CandidateFunctionName",
               "CandidatePaperFunctionName","CandidateOrchestratorFunctionName",
               "CandidatePaperPreflightFunctionName","CandidateSessionWatchdogFunctionName")]}]}
    if (service,action)==("s3api","get-bucket-versioning"):
        return {"Status":"Enabled"}
    if (service,action)==("s3api","get-public-access-block"):
        return {"PublicAccessBlockConfiguration":{k:True for k in
            ("BlockPublicAcls","IgnorePublicAcls","BlockPublicPolicy","RestrictPublicBuckets")}}
    if (service,action)==("events","describe-rule"):
        return {"State":rules_state}
    if (service,action)==("lambda","get-function-configuration"):
        return {"State":"Active","LastUpdateStatus":"Successful","CodeSha256":"fake"}
    if (service,action)==("s3api","head-object"):
        raise Blocked("EVIDENCE_NOT_YET_PUBLISHED")
    raise Blocked("TEST_UNEXPECTED_AWS_CALL")

def test_good_infrastructure_still_not_proven_paper():
    x=inspect(stub)
    assert x["account_verified"]
    assert x["ST"]["status"]=="CONTROL_PLANE_PASS_NOT_PAPER"
    assert x["PROD"]["status"]=="CONTROL_PLANE_PASS_NOT_PAPER"
    assert x["ST_research"]["status"]=="ST_RESEARCH_S3_NOT_VERIFIED"
    assert x["actual_forward_paper"]=="NOT_VERIFIED"
    assert not x["aws_mutation"] and not x["broker_orders"]

def test_any_enabled_trading_schedule_fails_safe():
    def active(*args):
        return stub(*args,rules_state="ENABLED")
    x=inspect(active)
    assert x["ST"]["status"]=="BLOCKED"
    assert x["PROD"]["status"]=="BLOCKED"
    assert any("TRADING_SCHEDULE_NOT_DISABLED" in z for z in x["ST"]["problems"])

def test_wrong_account_aborts_before_stack_inspection():
    calls=[]
    def wrong(*args):
        calls.append(args)
        return stub(*args,account="000000000000")
    with pytest.raises(Blocked,match="WRONG_AWS_ACCOUNT"):
        inspect(wrong)
    assert calls==[("sts","get-caller-identity")]

def test_bucket_mismatch_and_absent_real_receipts_not_green():
    x=inspect_stack("ST",lambda *args:stub(*args,wrong_bucket=True))
    assert x["status"]=="BLOCKED"
    assert "WRONG_ENVIRONMENT_BUCKET" in x["problems"]

def test_only_read_methods_whitelisted_and_git_blob_exact():
    assert ("lambda","invoke") not in READ_ONLY
    assert ("events","put-rule") not in READ_ONLY
    assert ("s3api","put-object") not in READ_ONLY
    assert ("cloudformation","update-stack") not in READ_ONLY
    with pytest.raises(Blocked,match="UNSAFE_AWS_METHOD"):
        aws("s3api","delete-object","--bucket","any")
    payload=b"research historic only"
    expected=hashlib.sha1(b"blob "+str(len(payload)).encode()+b"\0"+payload).hexdigest()
    assert gitblob(payload)==expected
