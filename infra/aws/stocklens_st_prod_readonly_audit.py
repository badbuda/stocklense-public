#!/usr/bin/env python3
"""Strict read-only AWS ST/PROD inspection. No schedule, broker, or S3 writes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ACCOUNT = "634740393398"
REGION = "eu-central-1"
ENV = {
    "ST": ("stocklens-st", "stocklens-st-candidatedata-6jj7i9fxjmfr"),
    "PROD": ("stocklens-prod", "stocklens-prod-candidatedata-c3yge4ymwb7u"),
}
RULES = ("CandidateSignalOnlyRuleName","CandidatePaperOnlyRuleName",
         "CandidateOrchestratorRuleName")
FUNCTIONS = ("CandidateFunctionName","CandidatePaperFunctionName",
             "CandidateOrchestratorFunctionName",
             "CandidatePaperPreflightFunctionName",
             "CandidateSessionWatchdogFunctionName")
SOURCE_COMMIT="8fe5ebdb7f7e2d3a9bc6bc9109d2b2745aae9bea"
DATA = {
    "results.json":"afca16734fbb4bdc340c42b9e10f727d3ac2f573",
    "curves.csv":"e6d4825d8f697b0704e8886171f26561043acb99",
}
READ_ONLY = {
    ("sts","get-caller-identity"),
    ("cloudformation","describe-stacks"),
    ("s3api","get-bucket-versioning"),
    ("s3api","get-public-access-block"),
    ("s3api","head-object"),
    ("s3api","get-object"),
    ("lambda","get-function-configuration"),
    ("events","describe-rule"),
}
class Blocked(Exception):
    pass

def aws(*args):
    if tuple(args[:2]) not in READ_ONLY:
        raise Blocked("UNSAFE_AWS_METHOD_REJECTED")
    try:
        p=subprocess.run(["aws","--region",REGION,*args,"--output","json"],
                         capture_output=True,text=True,timeout=30,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise Blocked("AWS_ACCESS_OR_TIMEOUT:"+"/".join(args[:2])) from exc
    if p.returncode:
        raise Blocked("AWS_MISSING_OR_DENIED:"+"/".join(args[:2]))
    try: obj=json.loads(p.stdout)
    except ValueError as exc:
        raise Blocked("AWS_NON_JSON:"+"/".join(args[:2])) from exc
    if not isinstance(obj,dict):
        raise Blocked("AWS_NON_OBJECT:"+"/".join(args[:2]))
    return obj

def gitblob(b):
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()

def inspect_stack(label,reader=aws):
    name,expected=ENV[label]
    o={"stack":name,"expected_bucket":expected,"status":"BLOCKED",
       "rules":{},"functions":{},"problems":[]}
    bad=o["problems"]
    try:
        stacks=reader("cloudformation","describe-stacks","--stack-name",name).get("Stacks",[])
        if len(stacks)!=1:
            raise Blocked("STACK_NOT_UNIQUE")
        stack=stacks[0]
        outputs={x["OutputKey"]:x["OutputValue"] for x in stack.get("Outputs",[])}
        o["actual_bucket"]=outputs.get("CandidateDataBucket")
        if stack.get("StackStatus") not in ("CREATE_COMPLETE","UPDATE_COMPLETE"):
            bad.append("STACK_NOT_STABLE")
        if o["actual_bucket"]!=expected:
            bad.append("WRONG_ENVIRONMENT_BUCKET")
        else:
            if reader("s3api","get-bucket-versioning","--bucket",expected).get("Status")!="Enabled":
                bad.append("S3_VERSIONING_DISABLED")
            config=reader("s3api","get-public-access-block","--bucket",expected).get("PublicAccessBlockConfiguration",{})
            if not all(config.get(k) is True for k in ("BlockPublicAcls","IgnorePublicAcls","BlockPublicPolicy","RestrictPublicBuckets")):
                bad.append("S3_PUBLIC_ACCESS_NOT_BLOCKED")
        for key in RULES:
            rule=outputs.get(key)
            if not rule:
                bad.append("RULE_OUTPUT_MISSING:"+key)
                continue
            s=reader("events","describe-rule","--name",rule).get("State")
            o["rules"][key]=s
            if s!="DISABLED":
                bad.append("TRADING_SCHEDULE_NOT_DISABLED:"+key)
        for key in FUNCTIONS:
            fn=outputs.get(key)
            if not fn:
                bad.append("FUNCTION_OUTPUT_MISSING:"+key)
                continue
            cfg=reader("lambda","get-function-configuration","--function-name",fn)
            # No env variables, role policies or secrets included in report.
            o["functions"][key]={"state":cfg.get("State"),
                  "update":cfg.get("LastUpdateStatus"),
                  "code_sha256":cfg.get("CodeSha256")}
            if cfg.get("State")!="Active" or cfg.get("LastUpdateStatus")!="Successful":
                bad.append("FUNCTION_NOT_READY:"+key)
    except Blocked as exc:
        bad.append(str(exc))
    o["status"]="CONTROL_PLANE_PASS_NOT_PAPER" if not bad else "BLOCKED"
    return o

def verify_st_research(reader=aws):
    bucket=ENV["ST"][1]
    prefix="research/experiments/SL9-031/"+SOURCE_COMMIT+"/"
    result={}
    for name,sha in DATA.items():
        key=prefix+name
        try:
            metadata=reader("s3api","head-object","--bucket",bucket,"--key",key)
            if not metadata.get("VersionId"):
                raise Blocked("MISSING_S3_VERSION_ID")
            with tempfile.TemporaryDirectory() as folder:
                dest=Path(folder)/name
                reader("s3api","get-object","--bucket",bucket,"--key",key,str(dest))
                if gitblob(dest.read_bytes())!=sha:
                    raise Blocked("ST_RESEARCH_BLOB_SHA_MISMATCH")
            result[name]={"status":"READBACK_HASH_VERIFIED"}
        except (Blocked,OSError) as exc:
            result[name]={"status":"MISSING_OR_UNVERIFIED",
                          "reason":str(exc) if isinstance(exc,Blocked) else "LOCAL_READ_ERROR"}
    return {"status":"ST_RESEARCH_S3_PASS" if all(
        x["status"]=="READBACK_HASH_VERIFIED" for x in result.values()
        ) else "ST_RESEARCH_S3_NOT_VERIFIED",
        "objects":result,
        "paper": "NOT_PROVEN_BY_HISTORICAL_RESEARCH_OBJECTS"}

def inspect(reader=aws):
    if reader("sts","get-caller-identity").get("Account")!=ACCOUNT:
        raise Blocked("WRONG_AWS_ACCOUNT_NO_FURTHER_READ")
    st=inspect_stack("ST",reader)
    prod=inspect_stack("PROD",reader)
    if st.get("actual_bucket")==prod.get("actual_bucket"):
        st["problems"].append("CROSS_ENV_BUCKET_COLLISION")
        prod["problems"].append("CROSS_ENV_BUCKET_COLLISION")
        st["status"]=prod["status"]="BLOCKED"
    return {
        "kind":"STOCKLENS_ST_PROD_READ_ONLY_AUDIT",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "account_verified":True,
        "ST":st,"PROD":prod,
        "ST_research":verify_st_research(reader) if st["status"]!="BLOCKED" else
                      {"status":"ST_CONTROL_PLANE_BLOCKED"},
        "actual_forward_paper":"NOT_VERIFIED",
        "independent_provider_parity":"NOT_VERIFIED",
        "aws_mutation":False,"broker_orders":False,
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=None)
    args=parser.parse_args()
    try: report=inspect()
    except Blocked as exc:
        report={"kind":"STOCKLENS_ST_PROD_READ_ONLY_AUDIT",
                "status":"BLOCKED","reason":str(exc),
                "aws_mutation":False,"broker_orders":False}
    txt=json.dumps(report,indent=2,ensure_ascii=False,sort_keys=True)
    print(txt)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(txt+"\n",encoding="utf-8")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
