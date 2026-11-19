#!/usr/bin/env python3
"""Deploy one NEW DARK ST Epoch4 Lambda; never touch old Paper or enable schedules.

Only --stage-dark mutates AWS: upload immutable ST code artifact, create new
CFN stack (scoped IAM role, log group, Lambda) and invoke new READ-ONLY
preflight. No Genesis, Paper, Continuity, EventBridge, PROD or broker writes.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

from infra.aws import sl56_epoch4_approval_readback as approval
from infra.aws import sl63_deployed_paper_source_parity as baseline
from infra.aws import sl63_epoch4_immutable_store as store

REGION="eu-central-1"
ACCOUNT="634740393398"
BUCKET=store.ST_BUCKET
FUNCTION="stocklens-st-epoch4-paper-dark"
STACK="stocklens-st-epoch4-paper-dark"
HANDLER="infra.aws.sl63_epoch4_lambda.handler"
ZIP_LIMIT=100_000_000
NEW_MODULES={
  "infra/aws/sl63_epoch4_lambda.py":"bf158c1962d40a81a342d6d1bafe188bc1616474",
  "infra/aws/sl63_epoch4_paper_economic_adapter.py":"b1234f2e033fd7dd1db5214f2342f75da71922e6",
  "infra/aws/sl63_epoch4_immutable_store.py":"e01b5700204e96b1778cd4e5535ad0184e6e1086",
}
EXCLUDE={"infra/aws/independent_paper.py",
         "infra/aws/independent_pipeline.py"}


def require(ok,reason):
    if not ok:raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()


def package(baseline_zip,repo):
    new={}
    for name,hash_expected in NEW_MODULES.items():
        raw=(repo/name).read_bytes()
        require(git_blob(raw)==hash_expected,"NEW_GIT_BLOB_CHANGED:"+name)
        new[name]=raw
    with zipfile.ZipFile(io.BytesIO(baseline_zip)) as orig:
        names=orig.namelist()
        require(len(names)==len(set(names)) and
                orig.testzip() is None,"OLD_ZIP_NOT_VERIFIED")
        require(not any(name in names for name in new),
                "NEW_ENTRY_CONFLICTS_EXISTING_ZIP")
        require(all(not n.startswith("/") and
                    ".." not in Path(n).parts and "\\" not in n for n in names),
                "UNSAFE_ZIP_PATH")
        require(all(git_blob(orig.read(name))==blob
                    for name,blob in baseline.PINNED_PUBLIC_MODULE_BLOBS.items()),
                "DEPLOYED_ECONOMIC_CODE_DRIFT")
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,"w",compression=zipfile.ZIP_DEFLATED) as dst:
            for item in orig.infolist():
                if item.filename in EXCLUDE:continue
                require(item.file_size<30_000_000,"UNEXPECTED_ZIP_MEMBER_SIZE")
                dst.writestr(item.filename,orig.read(item.filename))
            for name,data in sorted(new.items()):
                dst.writestr(name,data)
        output=stream.getvalue()
    require(0<len(output)<ZIP_LIMIT,"DARK_ZIP_OVERSIZED")
    with zipfile.ZipFile(io.BytesIO(output)) as z:
        require(not any(x in z.namelist() for x in EXCLUDE),
                "OLD_PRIVATE_ENTRYPOINT_COPIED")
        require(all(z.read(k)==v for k,v in new.items()),
                "NEW_CODE_ZIP_VERIFICATION_FAILED")
    return output


def template(key,original):
    runtime=original.get("Runtime")
    require(runtime in ("python3.12","python3.13"),"UNEXPECTED_ST_RUNTIME")
    arch=original.get("Architectures",["x86_64"])
    require(arch in (["x86_64"],["arm64"]),"UNEXPECTED_ST_ARCH")
    prefix="arn:aws:s3:::"+BUCKET+"/"
    epoch=prefix+store.PREFIX
    writer=[epoch+"genesis.json",epoch+"sessions/*",epoch+"continuity/*"]
    reader=writer+[prefix+"signals/*",
                   epoch+"preopen-inception-approval.json"]
    perms={"Version":"2012-10-17","Statement":[
      {"Effect":"Allow","Action":["s3:GetObject","s3:GetObjectVersion"],
       "Resource":reader},
      {"Effect":"Allow","Action":["s3:PutObject"],"Resource":writer},
      {"Effect":"Allow","Action":["logs:CreateLogStream","logs:PutLogEvents"],
       "Resource":["arn:aws:logs:"+REGION+":"+ACCOUNT+
                   ":log-group:/aws/lambda/"+FUNCTION+":*"]},
    ]}
    props={"FunctionName":FUNCTION,
       "Description":"DARK ST Epoch4 Paper; NO EventBridge; no broker",
       "Runtime":runtime,"Handler":HANDLER,
       "Role":{"Fn::GetAtt":["DarkRole","Arn"]},
       "Code":{"S3Bucket":BUCKET,"S3Key":key},
       "Timeout":120,"MemorySize":max(1024,original.get("MemorySize",512)),
       "Architectures":arch,
       "Environment":{"Variables":{
           "STOCKLENS_DATA_BUCKET":BUCKET,
           "STOCKLENS_EPOCH4_WRITE_ENABLED":"false"}},
    }
    layers=[x["Arn"] for x in original.get("Layers",[])]
    if layers:props["Layers"]=layers
    return {"AWSTemplateFormatVersion":"2010-09-09",
       "Description":"ST Epoch4 DARK; writes disabled; no schedules; separate IAM",
       "Resources":{
         "DarkRole":{"Type":"AWS::IAM::Role","Properties":{
           "AssumeRolePolicyDocument":{"Version":"2012-10-17",
             "Statement":[{"Effect":"Allow",
                "Principal":{"Service":"lambda.amazonaws.com"},
                "Action":"sts:AssumeRole"}]},
           "Policies":[{"PolicyName":"only-epoch4-s3-and-logs",
                        "PolicyDocument":perms}]}},
         "DarkLogGroup":{"Type":"AWS::Logs::LogGroup",
           "Properties":{"LogGroupName":"/aws/lambda/"+FUNCTION,
                         "RetentionInDays":14}},
         "DarkLambda":{"Type":"AWS::Lambda::Function",
           "DependsOn":["DarkRole","DarkLogGroup"],"Properties":props},
       },
       "Outputs":{"Function":{"Value":FUNCTION},
                  "PaperWriteEnabled":{"Value":"false"},
                  "ScheduleEnabled":{"Value":"false"}},
    }


def _artifact(s3,pkg):
    key="deployment/epoch4/dark/"+sha(pkg)+".zip"
    try:
        s3.put_object(Bucket=BUCKET,Key=key,Body=pkg,IfNoneMatch="*",
                      ContentType="application/zip",
                      Metadata={"sha256":sha(pkg)})
    except Exception as ex:
        code=(getattr(ex,"response",{}) or {}).get("Error",{}).get("Code")
        if code not in ("PreconditionFailed","412"):raise
    head=s3.head_object(Bucket=BUCKET,Key=key)
    version=head.get("VersionId")
    require(version not in (None,"","null") and
            head.get("ContentLength")==len(pkg) and
            (head.get("Metadata") or {}).get("sha256")==sha(pkg),
            "ARTIFACT_VERSION_OR_SHA_FAILED")
    obj=s3.get_object(Bucket=BUCKET,Key=key,VersionId=version)
    require(obj["Body"].read(ZIP_LIMIT+1)==pkg,
            "ARTIFACT_PINNED_BYTES_DIFFER")
    return key


def _existing(cfn):
    try:
        r=cfn.describe_stacks(StackName=STACK).get("Stacks",[])
    except Exception as ex:
        if (getattr(ex,"response",{}) or {}).get("Error",{}).get(
             "Code")=="ValidationError" and "does not exist" in str(ex):
            return None
        raise
    return r[0] if len(r)==1 else None


def execute(clients,repo,stage):
    attestation=approval.inspect(clients)
    require(attestation.get("approval_sha256")==approval.EXPECTED_SHA256,
            "APPROVAL_RECHECK_FAILED")
    original,cfg=baseline.authenticated_download(
        clients["sts"],clients["lambda"])
    pkg=package(original,repo)
    expected=base64.b64encode(hashlib.sha256(pkg).digest()).decode()
    report={"status":"ST_EPOCH4_DARK_PREDEPLOY_CHECKS_PASS",
            "expected_lambda_code_sha256_b64":expected,
            "old_st_paper_schedule_disabled":True,
            "new_epoch_paper_or_continuity_written":False,
            "broker_orders":False}
    if not stage:
        return {**report,"aws_mutations":False,
                "new_lambda_created":False},0
    stack=_existing(clients["cloudformation"])
    if stack is None:
        key=_artifact(clients["s3"],pkg)
        cft=template(key,cfg)
        require({x["Type"] for x in cft["Resources"].values()}==
                {"AWS::IAM::Role","AWS::Logs::LogGroup",
                 "AWS::Lambda::Function"},
                "UNEXPECTED_ST_STACK_RESOURCE")
        clients["cloudformation"].create_stack(
            StackName=STACK,TemplateBody=json.dumps(cft),
            Capabilities=["CAPABILITY_IAM"])
        try:
            clients["cloudformation"].get_waiter(
                "stack_create_complete").wait(
                    StackName=STACK,WaiterConfig={
                        "Delay":10,"MaxAttempts":48})
        except Exception:
            return {**report,
                    "status":"ST_DARK_CFN_CREATED_CHECK_STACK_EVENTS",
                    "aws_mutations":True,
                    "paper_write_enabled":False},4
        stack=_existing(clients["cloudformation"])
    require(stack and stack.get("StackStatus")=="CREATE_COMPLETE",
            "DARK_STACK_UNSTABLE_OR_NOT_CREATED")
    fn=clients["lambda"].get_function_configuration(FunctionName=FUNCTION)
    require(fn.get("CodeSha256")==expected and
            fn.get("Handler")==HANDLER and
            fn.get("State")=="Active" and
            fn.get("LastUpdateStatus")=="Successful" and
            fn.get("Environment",{}).get("Variables",{}).get(
                "STOCKLENS_EPOCH4_WRITE_ENABLED")=="false",
            "DARK_LAMBDA_NOT_PINNED_OR_NOT_DISABLED")
    invoked=clients["lambda"].invoke(
        FunctionName=FUNCTION,InvocationType="RequestResponse",
        Payload=json.dumps(
            {"mode":"STAGING_EPOCH4_DARK_READINESS"}).encode())
    raw=invoked["Payload"].read(15000)
    require(invoked.get("StatusCode")==200 and
            not invoked.get("FunctionError"),
            "DARK_READONLY_LAMBDA_PREFLIGHT_INVOKE_FAILED")
    result=json.loads(raw)
    require(result.get("status")==
            "EPOCH4_DARK_LAMBDA_READINESS_S3_READ_ONLY"
            and result.get("approval_sha256")==approval.EXPECTED_SHA256
            and result.get("new_epoch_paper_or_continuity_written") is False
            and result.get("broker_orders") is False,
            "DARK_READONLY_PREFLIGHT_NOT_VERIFIED")
    approval.inspect(clients)  # old ST and PROD state rechecked after deploy.
    return {**report,
        "status":"ST_EPOCH4_DARK_LAMBDA_DEPLOYED_READINESS_GREEN",
        "aws_mutations":True,"new_lambda_created":True,
        "eventbridge_schedule_enabled":False,
        "paper_write_enabled":False,
        "old_st_paper_lambda_untouched":True,
        "prod_untouched":True},0


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--stage-dark",action="store_true")
    args=parser.parse_args()
    import boto3
    session=boto3.session.Session(region_name=REGION)
    clients={k:session.client(k) for k in
             ("sts","s3","lambda","cloudformation","events")}
    try:
        report,rc=execute(
            clients,Path(__file__).resolve().parents[2],
            stage=args.stage_dark)
    except Exception as ex:
        report={"status":"ST_EPOCH4_DARK_DEPLOYMENT_BLOCKED",
                "error_type":type(ex).__name__,
                "reason":str(ex)[:260],
                "broker_orders":False,
                "paper_or_continuity_written":False,
                "prod_untouched":True}
        rc=4
    print(json.dumps(report,indent=2,sort_keys=True))
    return rc


if __name__=="__main__":
    sys.exit(main())
