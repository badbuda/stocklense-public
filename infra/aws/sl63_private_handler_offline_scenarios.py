#!/usr/bin/env python3
"""SL-63: probe real deployed PRIVATE Paper handler with strictly fake AWS/network.

This is a DIAGNOSTIC, not release acceptance: the deployed private handler may
not support forced-signal injection or the new Epoch4 book. Honest failures
remain BLOCKED; never count a refused branch as a successful BUY/SELL.
CloudShell parent only calls sts:GetCallerIdentity + lambda:GetFunction.
No Lambda Invoke, real S3 I/O, EventBridge, PROD or brokerage, ever.
All AWS client calls INSIDE child are replaced with in-memory fakes; socket,
subprocess, process exec and os.system audited off. Actual source is never
printed or uploaded and disappears after each run.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from infra.aws import sl63_deployed_paper_source_parity as existing

ZIP_LIMIT = 100_000_000
PRIVATE = "infra/aws/independent_paper.py"
BOOK = "NEW_AWS_INDEPENDENT_STAGING_BOOK_EPOCH4_20261119"
SAFE_CASES = ("CASH", "L1", "L2", "L3", "MISSING_PRIOR",
              "MISSING_CURRENT", "BAD_WEIGHTS", "CONTINUITY_WRITE_ERROR",
              "RETRY_DUPLICATE", "UNKNOWN_MODE")
WRITE_METHODS = {"put_object","copy_object","delete_object","upload_file",
                 "put_item","update_item","transact_write_items"}
READ_METHODS = {"get_object","head_object","list_object_versions",
                "list_objects_v2","get_bucket_versioning"}
KNOWN_MARKERS = ("STAGING_PAPER_ONLY","STAGING_PAPER_BOOTSTRAP_PREFLIGHT",
                 "STAGING_PAPER_SCHEDULE_READINESS",
                 "NEW_AWS_INDEPENDENT_STAGING_BOOK_EPOCH4_20261119",
                 "paper/epochs/")

def is_project_python_member(name):
    """Inspect/extract only StockLens project code, never dependency packages."""
    return (name.endswith(".py") and
            (name.startswith(("infra/","stocklens/")) or "/" not in name))

ALLOWED_STATES = {"handler_completed","handler_exception","offline_guard_blocked",
                  "handler_did_not_write","protocol_unverified"}


def require(value, reason):
    if not value: raise RuntimeError(reason)


def topology(raw):
    """All Python ZIP members, not just the entrypoint. No source disclosure."""
    members={}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        allnames=z.namelist()
        require(len(allnames)==len(set(allnames)), "DUPLICATE_ZIP_MEMBERS")
        require(all(not x.startswith("/") and ".." not in Path(x).parts
                    and "\\" not in x for x in allnames),"UNSAFE_ZIP_PATH")
        require(PRIVATE in allnames,"DEPLOYED_HANDLER_NOT_FOUND")
        for info in z.infolist():
            if not is_project_python_member(info.filename):
                continue
            require(info.file_size<=1_500_000,"OVERSIZE_PYTHON_MODULE")
            if len(members)>2000:raise RuntimeError("EXCESSIVE_ZIP_MODULES")
            contents=z.read(info.filename)
            tree=ast.parse(contents,filename="<private-source-redacted>")
            calls={v:0 for v in WRITE_METHODS|READ_METHODS}
            for n in ast.walk(tree):
                if isinstance(n,ast.Call):
                    f=n.func
                    name=f.attr if isinstance(f,ast.Attribute) else (
                        f.id if isinstance(f,ast.Name) else "")
                    if name in calls:calls[name]+=1
            literals={n.value for n in ast.walk(tree)
                      if isinstance(n,ast.Constant) and isinstance(n.value,str)}
            members[info.filename]=(calls,literals)
    handler_calls=members[PRIVATE][0]
    total_calls={key:sum(parts[0][key] for parts in members.values())
                 for key in WRITE_METHODS|READ_METHODS}
    all_literals=set().union(*(x[1] for x in members.values()))
    return {
        "project_python_member_count":len(members),
        "handler_sha256":hashlib.sha256(
            next_source(raw,PRIVATE)).hexdigest(),
        "aws_storage_method_ast_occurrences_project_zip_modules":dict(sorted(total_calls.items())),
        "aws_storage_method_ast_occurrences_private_handler":dict(sorted(handler_calls.items())),
        "reviewed_known_mode_and_epoch_literal_presence":{
            m:m in all_literals for m in KNOWN_MARKERS},
        "new_epoch_book_literal_found":BOOK in all_literals,
        "source_disclosed":False,
        "static_call_counts_not_execution_evidence":True,
    }


def next_source(raw,path):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        return z.read(path)


def prepare_zip(raw,base):
    """Extract vetted Python sources only into temp. Never export private code."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist()
        require(len({v.filename for v in infos})==len(infos),"DUPLICATE_ZIP_PATHS")
        bytes_total=0
        for info in infos:
            # Validate *every* archive name first, even if the dependency
            # member is not going to be extracted. Skipping must never hide
            # an attempted absolute/traversal path.
            name=info.filename
            require(not name.startswith("/") and ".." not in Path(name).parts
                    and "\\" not in name and len(name)<230,"UNSAFE_ZIP_MEMBER_NAME")
            if not is_project_python_member(name):continue
            require(info.file_size<=1_500_000,"ZIP_MODULE_OVERSIZE")
            bytes_total+=info.file_size
            require(bytes_total<30_000_000,"EXTRACTED_CODE_TOO_LARGE")
            dest=base/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(z.read(info))


CHILD = r'''
from __future__ import annotations
import io, json, os, sys, socket, hashlib, datetime, importlib, contextlib
from pathlib import Path
root=Path(os.environ["SL63_FAKE_ROOT"]).resolve()
case=os.environ["SL63_CASE"]
repo=Path(os.environ["SL63_PUBLIC_ROOT"]).resolve()
DAY="2026-11-18"
PRIOR="2026-11-17"
BUCKET="stocklens-st-candidatedata-6jj7i9fxjmfr"
sys.path.insert(0,str(root))
sys.path.insert(1,str(repo))
os.chdir(root)
os.environ["STOCKLENS_DATA_BUCKET"]=BUCKET
os.environ["AWS_DEFAULT_REGION"]="eu-central-1"
os.environ["AWS_REGION"]="eu-central-1"
os.environ["AWS_EC2_METADATA_DISABLED"]="true"
os.environ["PYTHONDONTWRITEBYTECODE"]="1"
for k in list(os.environ):
    if k.startswith("AWS_") and k not in (
        "AWS_DEFAULT_REGION","AWS_REGION","AWS_EC2_METADATA_DISABLED"):
        del os.environ[k]
def DENY(*args,**kwargs):
    raise RuntimeError("NO_NETWORK_OR_REAL_AWS_IN_PRIVATE_HANDLER_PROBE")
def audit(event,args):
    if event in ("socket.connect","subprocess.Popen","os.system","os.exec",
                 "os.spawn","os.posix_spawn","os.fork","os.forkpty"):
        DENY()
sys.addaudithook(audit)
socket.create_connection=DENY
socket.socket.connect=DENY
import urllib.request
urllib.request.urlopen=DENY
# Fast Guard's lean Python environment may not install boto3/botocore.
# Use an explicit fake module IN THE CHILD only, never real AWS.
try:
    import boto3
except ImportError:
    import types
    boto3=types.ModuleType("boto3")
    boto3.session=types.SimpleNamespace()
    sys.modules["boto3"]=boto3
try:
    from botocore.exceptions import ClientError
except ImportError:
    class ClientError(Exception):
        def __init__(self,response,operation):
            super().__init__("FAKE_CLIENT_ERROR")
            self.response=response

def missing(key):
    return ClientError({"Error":{"Code":"NoSuchKey","Message":"fake"}},
                       "GetObject")
class FakeS3:
    def __init__(self):
        self.items={}
        self.writes=[]
        self.ops=[]
        self.counter=0
    def seed(self,key,body,stamp="2026-11-18T02:00:00+00:00"):
        self.counter+=1
        raw=json.dumps(body,sort_keys=True,separators=(",",":")).encode()
        self.items[key]=(raw,"fake-version-"+str(self.counter),
                         datetime.datetime.fromisoformat(stamp))
    def _check(self,bucket):
        if bucket!=BUCKET:raise RuntimeError("S3_BUCKET_ESCAPE_DENIED")
    def head_object(self,Bucket,Key,**kw):
        self._check(Bucket);self.ops.append("HEAD")
        if Key not in self.items:raise missing(Key)
        raw,version,when=self.items[Key]
        return {"ContentLength":len(raw),"VersionId":version,"LastModified":when,
                "ETag":'"'+hashlib.md5(raw).hexdigest()+'"'}
    def get_object(self,Bucket,Key,VersionId=None,**kw):
        self._check(Bucket);self.ops.append("GET")
        if Key not in self.items:raise missing(Key)
        raw,version,when=self.items[Key]
        if VersionId and VersionId!=version:raise missing(Key)
        return {"Body":io.BytesIO(raw),"VersionId":version,"ContentLength":len(raw),
                "LastModified":when,"ETag":'"'+hashlib.md5(raw).hexdigest()+'"'}
    def put_object(self,Bucket,Key,Body,IfNoneMatch=None,**kw):
        self._check(Bucket);self.ops.append("PUT")
        if case=="CONTINUITY_WRITE_ERROR" and ("continuity" in Key):
            raise RuntimeError("SYNTHETIC_CONTINUITY_WRITE_FAILED")
        if IfNoneMatch=="*" and Key in self.items:
            raise ClientError({"Error":{"Code":"PreconditionFailed"}},"PutObject")
        raw=Body if isinstance(Body,bytes) else (
            Body.encode() if isinstance(Body,str) else Body.read())
        if len(raw)>2_000_000:raise RuntimeError("FAKE_S3_OVERSIZED_WRITE")
        self.counter+=1;version="fake-write-"+str(self.counter)
        now=datetime.datetime.now(datetime.timezone.utc)
        self.items[Key]=(raw,version,now)
        self.writes.append(Key)
        return {"VersionId":version,"ETag":'"'+hashlib.md5(raw).hexdigest()+'"'}
    def get_bucket_versioning(self,Bucket,**kw):
        self._check(Bucket);return {"Status":"Enabled"}
    def list_object_versions(self,Bucket,Prefix="",**kw):
        self._check(Bucket)
        return {"Versions":[{"Key":k,"VersionId":v[1],"IsLatest":True}
                            for k,v in self.items.items() if k.startswith(Prefix)],
                "DeleteMarkers":[],"IsTruncated":False}
    def list_objects_v2(self,Bucket,Prefix="",**kw):
        self._check(Bucket)
        return {"Contents":[{"Key":k,"Size":len(v[0])}
                             for k,v in self.items.items() if k.startswith(Prefix)],
                "IsTruncated":False}
    def __getattr__(self,name):
        def unexpected(*args,**kwargs):
            raise RuntimeError("UNSUPPORTED_FAKE_S3_METHOD")
        return unexpected
s3=FakeS3()
class FakeSTS:
    def get_caller_identity(self):
        return {"Account":"634740393398","Arn":"arn:aws:sts::634740393398:assumed-role/fake",
                "UserId":"FAKE"}
class FakeSession:
    def __init__(self,*a,**kw):pass
    def client(self,service_name,*a,**kw):return fake_client(service_name)
    def resource(self,*a,**kw):DENY()
def fake_client(name,*args,**kwargs):
    if name=="s3":return s3
    if name=="sts":return FakeSTS()
    raise RuntimeError("AWS_SERVICE_NOT_FAKE_IMPLEMENTED")
boto3.client=fake_client
boto3.resource=DENY
boto3.session.Session=FakeSession
# Stub direct requests too; socket-level barrier is the primary fail-closed.
try:
    import requests
    requests.sessions.Session.request=DENY
except ImportError:pass
try:
    import subprocess
    subprocess.Popen=DENY
except ImportError:pass
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION,LEVEL_LEVERAGE
from stocklens.paper import SessionMarket
import stocklens.paper as pp
assert Path(pp.__file__).resolve().is_relative_to(root)
def frozen(day,target):
    defensive=target=="CASH"
    level=1 if defensive else int(target[-1])
    lev=0. if defensive else LEVEL_LEVERAGE[level]
    q,t=weights_for_leverage(lev)
    return {"version":"8.0.0-shadow",
        "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
        "action":"EXPOSURE_CHANGE",
        "generated_at_utc":day+"T22:30:00Z",
        "signal_source":"QQQ_ADJUSTED_DAILY_CLOSE",
        "execution_plan":{"broker_actions_enabled":False},
        "latest":{"asof_date":day,"level":level,
            "defense_active":defensive,"target_leverage":lev,
            "qqq_weight":q*TARGET_INVESTED_FRACTION,
            "tqqq_weight":t*TARGET_INVESTED_FRACTION}}
def selected_target():
    return "L3" if case in ("MISSING_PRIOR","MISSING_CURRENT",
                             "CONTINUITY_WRITE_ERROR","RETRY_DUPLICATE",
                             "BAD_WEIGHTS") else case if case in (
        "CASH","L1","L2","L3") else "L3"
target=selected_target()
prior=frozen(PRIOR,target)
current=frozen(DAY,target)
if case=="BAD_WEIGHTS":
    prior["latest"]["qqq_weight"]=-0.2
if case!="MISSING_PRIOR":
    s3.seed("signals/"+PRIOR+".json",prior)
if case!="MISSING_CURRENT":
    s3.seed("signals/"+DAY+".json",current,
            stamp="2026-11-18T22:30:00+00:00")
def stub_market(*a,**kw):
    return SessionMarket(DAY,
        {"QQQ":100.,"TQQQ":50.},
        {"QQQ":100.,"TQQQ":50.},
        {"QQQ":100.,"TQQQ":50.},
        {"QQQ":0.,"TQQQ":0.},
        {"QQQ":0.,"TQQQ":0.})
pp.fetch_execution_market=stub_market
module=importlib.import_module("infra.aws.independent_paper")
assert Path(module.__file__).resolve().is_relative_to(root)
if hasattr(module,"fetch_execution_market"):
    setattr(module,"fetch_execution_market",stub_market)
def inspect_new_writes():
    import collections
    buckets=collections.Counter()
    for key in s3.writes:
        if "continuity" in key:buckets["continuity"]+=1
        elif "sessions/" in key:buckets["session"]+=1
        elif "genesis" in key:buckets["genesis"]+=1
        elif "epochs/" in key:buckets["epoch"]+=1
        else:buckets["other"]+=1
    def sides(x):
        if isinstance(x,dict):
            v=x.get("side")
            if v in ("BUY","SELL"):yield v
            for y in x.values():yield from sides(y)
        elif isinstance(x,list):
            for y in x:yield from sides(y)
    trade_sides=[]
    for key in s3.writes:
        raw=s3.items[key][0]
        try: value=json.loads(raw)
        except Exception:continue
        trade_sides.extend(sides(value))
    return dict(buckets),sorted(set(trade_sides))
event={"mode":"STAGING_PAPER_ONLY",
       "expected_session":DAY, "bootstrap":True}
if case=="UNKNOWN_MODE":event["mode"]="NOT_SUPPORTED_FAKE_SIMULATE_MODE"
attempts=2 if case=="RETRY_DUPLICATE" else 1
output=[]
for _ in range(attempts):
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            reply=module.handler(event,None)
        if isinstance(reply,dict):
            state=reply.get("status")
            # Only statuses from our known safety vocabulary can be shown.
            expected={"STAGED_PAPER_VERIFIED","STAGING_PAPER_SCHEDULE_READINESS_PASS_READ_ONLY",
                       "FAIL_CLOSED","BLOCKED","HALTED"}
            output.append({"outcome":"handler_returned",
                           "status":state if state in expected else "UNRECOGNIZED_REDACTED"})
        else:output.append({"outcome":"handler_non_dict_return"})
    except Exception as exc:
        output.append({"outcome":"handler_exception",
                       "exception_class":type(exc).__name__})
counts,sides=inspect_new_writes()
print(json.dumps({"case":case,
    "handler_called_locally":True,
    "true_private_handler_imported_from_deployed_zip":True,
    "all_sdk_calls_fake":True,"network_disabled":True,"real_aws_mutations":False,
    "broker_orders":False,
    "handler_results":output,
    "fake_s3_paper_write_counts":counts,
    "fake_s3_reads_count":sum(x in ("GET","HEAD") for x in s3.ops),
    "fake_s3_writes_count":len(s3.writes),
    "fake_s3_modeled_sides_observed":sides,
    "both_buy_sell_not_proven_by_single_case":True,
},sort_keys=True))
'''


def childcase(root, repo, name):
    env={k:v for k,v in os.environ.items()
         if not k.startswith("AWS_") and not k.startswith("BOTO")}
    env["SL63_FAKE_ROOT"]=str(root)
    env["SL63_PUBLIC_ROOT"]=str(repo)
    env["SL63_CASE"]=name
    env["AWS_EC2_METADATA_DISABLED"]="true"
    env["PYTHONDONTWRITEBYTECODE"]="1"
    process=subprocess.run(
        [sys.executable,"-B","-c",CHILD],cwd=root,env=env,
        capture_output=True,text=True,timeout=30,check=False)
    try:
        lines=[x for x in process.stdout.splitlines() if x.startswith('{"')]
        result=json.loads(lines[-1])
    except Exception:
        # The failing private ZIP source is NEVER emitted, only a fixed
        # exception-class allowlist; CI toy fixtures remain debuggable.
        last=process.stderr.strip().splitlines()
        candidate=last[-1].split(":",1)[0].strip() if last else ""
        allowed={"ModuleNotFoundError","ImportError","AssertionError",
                 "RuntimeError","TypeError","AttributeError","OSError",
                 "SyntaxError","ValueError","NameError","KeyError"}
        return {"case":name,"status":"OFFLINE_PRIVATE_HANDLER_RUNTIME_UNVERIFIED",
                "child_exit":process.returncode,
                "exception_class":candidate if candidate in allowed else "UNCLASSIFIED_CHILD_FAILURE",
                "stderr_sha256":hashlib.sha256(process.stderr.encode()).hexdigest(),
                "private_stdout_disclosed":False}
    return {"case":name,"status":"OBSERVED_PRIVATE_HANDLER_WITH_IN_MEMORY_AWS",
            "child_exit":process.returncode,**result,
            "private_source_disclosed":False}


def run():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("review","forced-offline"),default="review")
    args=p.parse_args()
    import boto3
    ses=boto3.session.Session(region_name=existing.REGION)
    raw,cfg=existing.authenticated_download(ses.client("sts"),ses.client("lambda"))
    modules,handler=existing.inspect_zip(raw,Path("."))
    require(all(v["matches_tested_code"] for v in modules.values()),
            "DEPLOYED_ECONOMIC_MODULE_PARITY_FAILED")
    require(handler["module_bundled"],"PRIVATE_HANDLER_NOT_BUNDLED")
    structure=topology(raw)
    require(structure["handler_sha256"]==handler["module_sha256"],
            "PRIVATE_HANDLER_SHA_UNEXPECTED")
    report={
        "kind":"SL63_EXACT_DEPLOYED_PRIVATE_HANDLER_ISOLATED_E2E_DIAGNOSTIC",
        "st_lambda":existing.NAME,
        "authenticated_aws_zip_sha256_b64":cfg["CodeSha256"],
        "deployed_economic_module_parity_verified":True,
        "all_real_aws_requests_read_only":True,
        "lambda_invocations":False,"aws_mutations":False,
        "prod_mutations":False,"broker_orders":False,
        "private_source_disclosed":False,
        "private_handler_sha256":structure["handler_sha256"],
        "private_handler_structural_proof":structure,
    }
    if args.mode=="review":
        report["status"]="DELEGATED_WRITERS_STATIC_MAP_ONLY_NOT_E2E"
        return report,0
    repo=Path(__file__).resolve().parents[2]
    require(repo.joinpath("tests/test_paper_order_lifecycle_matrix.py").is_file(),
            "TEST_SOURCE_CHECKOUT_REQUIRED")
    with tempfile.TemporaryDirectory(prefix="sl63-exact-private-fake-") as tmp:
        root=Path(tmp)
        prepare_zip(raw,root)
        report["cases"]=[childcase(root,repo,case) for case in SAFE_CASES]
    # A green outcome requires the handler to create isolated fake PAPER,
    # CONTINUITY and a matching modeled BUY and SELL, which is not guaranteed.
    # In particular this baseline handler is not wired to the new epoch book.
    successes=[
        c for c in report["cases"]
        if c.get("child_exit")==0 and
           c.get("fake_s3_paper_write_counts",{}).get("session",0)>0 and
           c.get("fake_s3_paper_write_counts",{}).get("continuity",0)>0
    ]
    report["positive_local_fake_paper_and_continuity_cases"]=len(successes)
    report["new_epoch_runtime_deployed"]=False
    report["private_handler_real_aws_s3_write_tested"]=False
    # A technical invocation with no actual Paper/Continuity is a BLOCKER,
    # not a green run: tests cannot pass by simply refusing to execute.
    report["status"]=("PRIVATE_HANDLER_FAKE_STORAGE_RECEIPTS_OBSERVED_NOT_LIVE_E2E"
                      if successes else
                      "PRIVATE_HANDLER_FORCED_BUY_SELL_E2E_NOT_PROVEN_BLOCKED")
    return report, 0 if successes else 4


def main():
    try:
        data,code=run()
    except Exception as exc:
        data={"status":"SL63_PRIVATE_HANDLER_OFFLINE_DIAGNOSTIC_BLOCKED",
              "reason":str(exc)[:220],
              "exception_type":type(exc).__name__,
              "aws_mutations":False,"lambda_invocations":False,"broker_orders":False,
              "private_source_disclosed":False}
        code=2
    print(json.dumps(data,indent=2,sort_keys=True))
    return code


if __name__=="__main__":
    raise SystemExit(main())
