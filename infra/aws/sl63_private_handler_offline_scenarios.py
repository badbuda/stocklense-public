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
              "RETRY_DUPLICATE", "UNKNOWN_MODE",
              "SEQUENCE_BUY_SELL_BUY", "CONTINUITY_RETRY_RECOVERY",
              "VIRTUAL_CLOCK_BUY_SELL_BUY")
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
import io, json, os, sys, socket, hashlib, datetime, importlib, contextlib, traceback
from pathlib import Path
root=Path(os.environ["SL63_FAKE_ROOT"]).resolve()
case=os.environ["SL63_CASE"]
repo=Path(os.environ["SL63_PUBLIC_ROOT"]).resolve()
# Five-session probe MUST only use completed XNYS sessions as of Nov19
# morning. Trying Nov19/20/23/24 before they have closed is legitimately
# rejected by production's no-future-session guard.
DAY=("2026-11-12" if case=="SEQUENCE_BUY_SELL_BUY" else "2026-11-18")
PRIOR=("2026-11-11" if case=="SEQUENCE_BUY_SELL_BUY" else "2026-11-17")
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
        self.continuity_failed_once=False
        self.immutable_conflict_roles=[]
        # Simulate archived session commit on its OWN market date, not
        # CloudShell current wall clock. Otherwise next day's causal receipt
        # checks can reject an impossible future LastModified timestamp.
        self.fake_s3_commit_utc=datetime.datetime.fromisoformat(
            DAY+"T23:00:00+00:00")
    def seed(self,key,body,stamp=None):
        self.counter+=1
        raw=json.dumps(body,sort_keys=True,separators=(",",":")).encode()
        timestamp=stamp or body.get("generated_at_utc")
        if not timestamp:
            raise RuntimeError("SYNTHETIC_SIGNAL_NEEDS_UTC_TIMESTAMP")
        self.items[key]=(raw,"fake-version-"+str(self.counter),
                         datetime.datetime.fromisoformat(
                             timestamp.replace("Z","+00:00")))
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
        if (case=="CONTINUITY_RETRY_RECOVERY" and
                "continuity" in Key and not self.continuity_failed_once):
            self.continuity_failed_once=True
            raise RuntimeError("SYNTHETIC_FIRST_CONTINUITY_WRITE_FAILED")
        if IfNoneMatch=="*" and Key in self.items:
            role=("genesis" if "genesis" in Key else
                  "continuity" if "continuity" in Key else
                  "paper" if "sessions/" in Key else "other")
            self.immutable_conflict_roles.append(role)
            raise ClientError({"Error":{"Code":"PreconditionFailed"}},"PutObject")
        raw=Body if isinstance(Body,bytes) else (
            Body.encode() if isinstance(Body,str) else Body.read())
        if len(raw)>2_000_000:raise RuntimeError("FAKE_S3_OVERSIZED_WRITE")
        self.counter+=1;version="fake-write-"+str(self.counter)
        now=self.fake_s3_commit_utc
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
current=frozen(DAY,"CASH") if case in (
    "SEQUENCE_BUY_SELL_BUY","VIRTUAL_CLOCK_BUY_SELL_BUY") else frozen(DAY,target)
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
# Contract-safe error fingerprints. We DO NOT output private source, private
# function names, exception text, object keys, traceback lines or credentials.
ERROR_TAGS=(
    "date","session","previous","prior","genesis","book","continuity",
    "signal","market","timestamp","time","latest","expected","version",
    "invalid","already","duplicate","parse","format","missing","chain",
    "receipt","before","after","next","future","stale",
)
def exception_evidence(exc):
    msg=str(exc).lower()
    frames=[]
    for tb in traceback.walk_tb(exc.__traceback__):
        frame,_=tb
        name=frame.f_code.co_filename.replace("\\","/")
        if "/stocklens/paper.py" in name or "/stocklens/core.py" in name:
            kind="DEPLOYED_ECONOMIC_MODEL"
        elif "/infra/aws/independent_paper.py" in name:
            kind="DEPLOYED_PRIVATE_HANDLER"
        elif "/infra/aws/" in name:
            kind="DEPLOYED_INFRA_HELPER"
        elif "/exchange_calendars/" in name:
            kind="XNYS_CALENDAR_DEPENDENCY"
        elif "/botocore/" in name:
            kind="FAKE_AWS_SDK_EXCEPTION"
        elif name=="<string>":
            kind="OFFLINE_HARNESS"
        else:
            kind="OTHER_DEPENDENCY"
        frames.append(kind)
    return {
        "class":type(exc).__name__,
        "last_frame_category":frames[-1] if frames else "UNKNOWN",
        "frame_categories":list(dict.fromkeys(frames))[-8:],
        "message_sha256":hashlib.sha256(str(exc).encode()).hexdigest(),
        "known_error_token_presence":[t for t in ERROR_TAGS if t in msg],
        "raw_error_not_disclosed":True,
    }

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
attempts=2 if case in ("RETRY_DUPLICATE","CONTINUITY_RETRY_RECOVERY") else 1
import types
fake_context=types.SimpleNamespace(
    aws_request_id="SL63-OFFLINE-FAKE-INVOCATION",
    function_name="stocklens-st-paper-candidate",
    invoked_function_arn=("arn:aws:lambda:eu-central-1:634740393398:"
                          "function:stocklens-st-paper-candidate"),
    memory_limit_in_mb="512",
    get_remaining_time_in_millis=lambda:45000,
)
# The production Handler may correctly require each session to have
# *already* completed. Virtual-clock scenario advances wall time IN THIS
# LOCAL CHILD ONLY. No future market data, AWS read, or actual Paper receipt.
# Original production date guards remain in place: they see the simulated time.
def run_handler_with_time(event, day):
    if case!="VIRTUAL_CLOCK_BUY_SELL_BUY":
        return module.handler(event,fake_context)
    from freezegun import freeze_time
    next_morning=(datetime.date.fromisoformat(day)+
                  datetime.timedelta(days=1)).isoformat()+"T10:00:00Z"
    with freeze_time(next_morning):
        return module.handler(event,fake_context)
output=[]
for _ in range(attempts):
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            reply=run_handler_with_time(event,DAY)
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
                       "exception_class":type(exc).__name__,
                       "safe_failure_evidence":exception_evidence(exc)})
def observed_sides_for_keys(keys):
    def recurse(v):
        if isinstance(v,dict):
            if v.get("side") in ("BUY","SELL"):
                yield v["side"]
            for child in v.values():
                yield from recurse(child)
        elif isinstance(v,list):
            for child in v:
                yield from recurse(child)
    found=[]
    for key in keys:
        try:
            record=json.loads(s3.items[key][0])
            found.extend(recurse(record))
        except (KeyError,ValueError,TypeError):
            pass
    return sorted(set(found))

# Same FakeS3 and the same private module across multiple completed exchange
# sessions. This forces SELL on Nov19 after Nov18's L3 BUY; also forces
# subsequent BUY and target rebalances. No S3 signal is backdated/rewritten.
sequence=[]
if case in ("SEQUENCE_BUY_SELL_BUY","VIRTUAL_CLOCK_BUY_SELL_BUY"):
    schedule=(
        (("2026-11-18","2026-11-17","L3","CASH",True),
         ("2026-11-19","2026-11-18","CASH","L2",False),
         ("2026-11-20","2026-11-19","L2","L1",False),
         ("2026-11-23","2026-11-20","L1","L3",False),
         ("2026-11-24","2026-11-23","L3","CASH",False))
        if case=="VIRTUAL_CLOCK_BUY_SELL_BUY" else (
         ("2026-11-12","2026-11-11","L3","CASH",True),
         ("2026-11-13","2026-11-12","CASH","L2",False),
         ("2026-11-16","2026-11-13","L2","L1",False),
         ("2026-11-17","2026-11-16","L1","L3",False),
         ("2026-11-18","2026-11-17","L3","CASH",False))
    )
    # First step was executed in the existing loop, whose starting signal
    # 17 Nov was L3 and 18 Nov's *next-day* frozen target was CASH.
    def step_proof(day,newkeys,successful):
        return {
            "session":day,
            "private_handler_returned_verified":successful,
            "paper_receipt_written":("paper/sessions/"+day+".json" in newkeys),
            "continuity_receipt_written":(
                "paper/continuity/"+day+".json" in newkeys),
            "modeled_sides_in_receipt":observed_sides_for_keys(newkeys),
            "new_unique_s3_writes":len(newkeys),
        }
    sequence.append(step_proof(schedule[0][0],list(s3.writes),
                      bool(output and
                           output[0].get("status")=="STAGED_PAPER_VERIFIED")))
    for day,prev,prior_target,next_target,bootstrap in schedule[1:]:
        DAY=day
        PRIOR=prev
        s3.fake_s3_commit_utc=datetime.datetime.fromisoformat(
            day+"T23:00:00+00:00")
        # Prior signal was already frozen and is present. Seed ONLY the new
        # post-session Signal to support the next *following* session.
        s3.seed("signals/"+day+".json",frozen(day,next_target),
                stamp=day+"T22:30:00+00:00")
        if "signals/"+prev+".json" not in s3.items:
            raise RuntimeError("TEST_HARNESS_LOST_PREVIOUS_SIGNAL")
        event={"mode":"STAGING_PAPER_ONLY",
               "expected_session":day, "bootstrap":bootstrap}
        before=len(s3.writes)
        result={"outcome":"handler_exception"}
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                ret=run_handler_with_time(event,day)
            observed=ret.get("status") if isinstance(ret,dict) else None
            result={"outcome":"handler_returned",
                    "status":(observed if observed=="STAGED_PAPER_VERIFIED"
                              else "NOT_VERIFIED_STATUS_REDACTED")}
        except Exception as exc:
            result={"outcome":"handler_exception",
                    "exception_class":type(exc).__name__,
                    "safe_failure_evidence":exception_evidence(exc)}
        output.append(result)
        sequence.append(step_proof(day,s3.writes[before:],
                          result.get("status")=="STAGED_PAPER_VERIFIED"))
counts,sides=inspect_new_writes()
recovery_detail=None
if case=="CONTINUITY_RETRY_RECOVERY":
    recovery_detail={
        "first_continuity_write_failed_injected":s3.continuity_failed_once,
        "immutable_precondition_conflict_roles":list(s3.immutable_conflict_roles),
        "paper_receipt_persisted":(
            "paper/sessions/2026-11-18.json" in s3.items),
        "continuity_receipt_persisted":(
            "paper/continuity/2026-11-18.json" in s3.items),
        "retry_reported_verified":(
            len(output)>1 and
            output[1].get("status")=="STAGED_PAPER_VERIFIED"),
        "duplicate_written_keys":len(s3.writes)-len(set(s3.writes)),
        "error_classes":[x.get("exception_class") for x in output
                         if x.get("outcome")=="handler_exception"],
    }
print(json.dumps({"case":case,
    "handler_called_locally":True,
    "true_private_handler_imported_from_deployed_zip":True,
    "all_sdk_calls_fake":True,"network_disabled":True,"real_aws_mutations":False,
    "broker_orders":False,
    "handler_results":output,
    "fake_s3_paper_write_counts":counts,
    "fake_s3_reads_count":sum(x in ("GET","HEAD") for x in s3.ops),
    "synthetic_storage_lastmodified_is_session_scoped":True,
    "fake_s3_writes_count":len(s3.writes),
    "fake_s3_duplicate_key_writes":len(s3.writes)-len(set(s3.writes)),
    "fake_s3_precondition_conflict_roles":list(s3.immutable_conflict_roles),
    "fake_s3_modeled_sides_observed":sides,
    "consecutive_session_proofs":sequence,
    "partial_write_recovery_proof":recovery_detail,
    "both_buy_sell_not_proven_by_single_case":True,
    "virtual_clock_isolated_child_only":case=="VIRTUAL_CLOCK_BUY_SELL_BUY",
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
    negative={"MISSING_PRIOR","MISSING_CURRENT","BAD_WEIGHTS","UNKNOWN_MODE"}
    unsafe=[x["case"] for x in report["cases"]
            if (x.get("case") in negative and
                x.get("fake_s3_writes_count",0)>0)
               or (x.get("case")=="RETRY_DUPLICATE" and
                   x.get("fake_s3_duplicate_key_writes",0)>0)]
    # An injected Continuity failure with a committed Paper receipt is
    # evidence of partial-write/recovery risk, not a test PASS.
    partial=[x["case"] for x in report["cases"]
             if x.get("case")=="CONTINUITY_WRITE_ERROR"
             and x.get("fake_s3_paper_write_counts",{}).get("session",0)>0]
    report["unsafe_negative_cases"]=unsafe
    report["partial_write_review_required_cases"]=partial
    sequence=next((x for x in report["cases"]
                   if x.get("case")=="SEQUENCE_BUY_SELL_BUY"),{})
    steps=sequence.get("consecutive_session_proofs",[])
    required_dates=("2026-11-12","2026-11-13","2026-11-16",
                    "2026-11-17","2026-11-18")
    report["legacy_private_handler_multisession_sides"]=(
        sequence.get("fake_s3_modeled_sides_observed",[]))
    report["legacy_private_handler_multisession_proven"]=bool(
        sequence.get("child_exit")==0 and len(steps)==len(required_dates)
        and all(s.get("session")==day
                and s.get("private_handler_returned_verified")
                and s.get("paper_receipt_written")
                and s.get("continuity_receipt_written")
                for s,day in zip(steps,required_dates))
        and {"BUY","SELL"}.issubset(set(
            sequence.get("fake_s3_modeled_sides_observed",[])))
        and sequence.get("fake_s3_duplicate_key_writes")==0)
    future_case=next((x for x in report["cases"]
                      if x.get("case")=="VIRTUAL_CLOCK_BUY_SELL_BUY"),{})
    virtual_steps=future_case.get("consecutive_session_proofs",[])
    virtual_days=("2026-11-18","2026-11-19","2026-11-20",
                  "2026-11-23","2026-11-24")
    report["virtual_clock_private_handler_buy_sell_proven"]=bool(
        future_case.get("child_exit")==0
        and future_case.get("virtual_clock_isolated_child_only")
        and len(virtual_steps)==len(virtual_days)
        and all(s.get("session")==day
                and s.get("private_handler_returned_verified")
                and s.get("paper_receipt_written")
                and s.get("continuity_receipt_written")
                for s,day in zip(virtual_steps,virtual_days))
        and {"BUY","SELL"}.issubset(set(
            future_case.get("fake_s3_modeled_sides_observed",[])))
        and future_case.get("fake_s3_duplicate_key_writes")==0)
    recovery=next((x for x in report["cases"]
                   if x.get("case")=="CONTINUITY_RETRY_RECOVERY"),{})
    proof=recovery.get("partial_write_recovery_proof") or {}
    report["continuity_failure_then_retry_recovered_proven"]=bool(
        recovery.get("child_exit")==0 and
        proof.get("first_continuity_write_failed_injected")
        and proof.get("paper_receipt_persisted")
        and proof.get("continuity_receipt_persisted")
        and proof.get("retry_reported_verified")
        and proof.get("duplicate_written_keys")==0)
    report["new_epoch_runtime_deployed"]=False
    report["private_handler_real_aws_s3_write_tested"]=False
    # Never call single-session BUYs successful E2E. Require multi-session
    # BUY+SELL and continuous receipts, explicit recovery from a failed
    # write, and native support for the new approved Epoch4 book.
    okay=(bool(successes) and not unsafe
          and report["legacy_private_handler_multisession_proven"]
          and report["continuity_failure_then_retry_recovered_proven"]
          and structure["new_epoch_book_literal_found"])
    report["status"]=(
        "PRIVATE_HANDLER_FAKE_EPOCH4_MULTIDAY_AND_RECOVERY_PROVEN_NOT_REAL_AWS"
        if okay else "PRIVATE_HANDLER_EPOCH4_MULTIDAY_OR_RECOVERY_NOT_PROVEN_BLOCKED")
    return report, 0 if okay else 4


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
