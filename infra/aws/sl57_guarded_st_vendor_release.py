#!/usr/bin/env python3
"""SL-57 guarded ST-only candidate release. No broker/PROD/alarm reset or Paper backfill.

inspect: read deployed ST ZIP, validate exact source identity and release plan.
apply --yes --acknowledge-st-cfn-drift: repeat preflight then update only ST
Signal/Watchdog Lambda ZIPs, prospective Watchdog env and two ST schedules.
Stop on any unknown configuration/source difference. Never execute CFN change sets.
Direct changes to CFN-managed resources REQUIRE explicit CFN-drift acknowledgement.
"""
from __future__ import annotations
import argparse, base64, hashlib, io, json, sys, urllib.request, zipfile
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

ACCOUNT="634740393398"
REGION="eu-central-1"
ST="stocklens-st"
PROD="stocklens-prod"
REF="772f1184b0c417bead55fb27d203c1f05f836cad"
REPO="badbuda/stocklense-public"
PAPER_FILE="infra/aws/independent_paper.py"
WATCHDOG_FILE="infra/aws/independent_session_watchdog.py"
WATCHDOG_CHANGES=(
    (
        "            read_signal_saved_at=None, paper_rule_state: str | None = None) -> dict:",
        "            read_signal_saved_at=None, paper_rule_state: str | None = None,\n"
        "            signal_v2_start_session: str | None = None) -> dict:",
    ),
    (
        "                    due = due_signal_sessions(now, signal_activation_at)",
        "                    due = due_signal_sessions(\n"
        "                        now, signal_activation_at,\n"
        "                        v2_start_session=signal_v2_start_session,\n"
        "                    )",
    ),
    (
        "                     signal_activation_at=signal_activation_at,\n"
        '                     read_signal_saved_at=lambda day: read_last_modified(f"signals/{day}.json"))',
        "                     signal_activation_at=signal_activation_at,\n"
        '                     signal_v2_start_session=os.environ.get("SIGNAL_V2_START_SESSION") or None,\n'
        '                     read_signal_saved_at=lambda day: read_last_modified(f"signals/{day}.json"))',
    ),
)

PAPER_BEFORE="""    from infra.aws.independent_orchestrator import current_completed_session

    day = current_completed_session(now)"""
PAPER_AFTER="""    from infra.aws.independent_pipeline import completed_session_for_scheduled_attempt

    day = completed_session_for_scheduled_attempt(now)"""

START="2026-11-10"  # prospective new policy; never reclassify historic incidents
EXPECTED={
 "infra/aws/independent_pipeline.py":(
  "b826dfafb5ceb4c7dd83c9d1c3c357a252e94a64",
  "a519d8800d58dc60b65d9e474b51f1153bb00d0c"),
 "infra/aws/independent_signal_monitor.py":(
  "cdcd9d14690d8e6ecb0e68434c6f1714ea81af17",
  "34388ab6692a46535a3314773650fb5121318b83"),
 "infra/aws/independent_session_watchdog.py":(
  "7e8929d464dc50e0747e2c7bb6fc4df5470684c9",
  "0cd48632c8e063570c8131cb583576a0bcd029ff"),
 "stocklens/st_signal_retry_policy.py":(
  None,"e48600308e3c4ad191713ea591151f17fe0cec70"),
}
UPDATED={
 "CandidateSignalOnlyRuleName":"cron(30 5,8,11,12 ? * TUE-SAT *)",
 "CandidatePaperOnlyRuleName":"cron(45 12 ? * TUE-SAT *)",
}
OLD={
 "CandidateSignalOnlyRuleName":"cron(30 2 ? * TUE-SAT *)",
 "CandidatePaperOnlyRuleName":"cron(20 3 ? * TUE-SAT *)",
}
FN={
 "CandidateSignalOnlyRuleName":"CandidateFunctionName",
 "CandidatePaperOnlyRuleName":"CandidatePaperFunctionName",
}
LAMBDA_KEYS=("CandidateFunctionName","CandidatePaperFunctionName",
 "CandidateSessionWatchdogFunctionName","CandidatePaperPreflightFunctionName",
 "CandidateOrchestratorFunctionName")

def check(cond,code):
 if not cond: raise RuntimeError(code)

def blob(data):
 return hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()

def sha256b64(data):
 return base64.b64encode(hashlib.sha256(data).digest()).decode()

def latest_source(path):
 req=urllib.request.Request(
  f"https://raw.githubusercontent.com/{REPO}/{REF}/{path}",
  headers={"User-Agent":"stocklens-sl57-release-gate"})
 with urllib.request.urlopen(req,timeout=35) as resp:
  return resp.read(240_000)

def patch_private_watchdog(source: bytes) -> bytes:
 """Preserve private isolated metrics/epoch logic and add ONLY three audited V2 edits.

 The original complete file's SHA need not match if its unrelated private
 monitoring implementation differs. Each exact modified call/signature must
 still match the audited baseline; unexpected variants fail before any write.
 """
 import ast
 try:
  original=source.decode("utf-8")
  tree=ast.parse(original,filename=WATCHDOG_FILE)
 except (UnicodeError,SyntaxError) as exc:
  raise RuntimeError("PRIVATE_WATCHDOG_SOURCE_INVALID") from exc
 functions={x.name for x in tree.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))}
 check({"inspect","handler"} <= functions, "PRIVATE_WATCHDOG_HANDLERS_CHANGED")
 check("from infra.aws.independent_signal_monitor import due_signal_sessions" in original,
       "PRIVATE_WATCHDOG_MONITOR_IMPORT_CHANGED")
 check("cw.put_metric_data(" in original and "read_signal_activation" in original,
       "PRIVATE_WATCHDOG_METRICS_OR_ANCHOR_CHANGED")
 updated=original
 for index,(before,after) in enumerate(WATCHDOG_CHANGES):
  check(updated.count(before)==1, "PRIVATE_WATCHDOG_V2_ANCHOR_CHANGED:"+str(index))
  check(updated.count(after)==0, "PRIVATE_WATCHDOG_V2_ALREADY_PRESENT:"+str(index))
  updated=updated.replace(before,after,1)
 try:
  ast.parse(updated,filename=WATCHDOG_FILE)
 except SyntaxError as exc:
  raise RuntimeError("PATCHED_PRIVATE_WATCHDOG_NOT_PYTHON") from exc
 restored=updated
 for before,after in reversed(WATCHDOG_CHANGES):
  restored=restored.replace(after,before,1)
 check(restored==original,"PRIVATE_WATCHDOG_UNEXPECTED_PATCH_SCOPE")
 return updated.encode("utf-8")


def prepare_zip(source_zip,fetch=latest_source):
 """One pinned 4-file mutation; preserve all other deployed ZIP members."""
 patches={}
 for path,(_,new_sha) in EXPECTED.items():
  data=fetch(path)
  check(blob(data)==new_sha,"PINNED_NEW_SOURCE_MISMATCH:"+path)
  patches[path]=data
 target=io.BytesIO()
 with zipfile.ZipFile(io.BytesIO(source_zip)) as old:
  rows=old.infolist()
  names=[x.filename for x in rows]
  check(len(rows)>100 and len(names)==len(set(names)),"INVALID_OR_DUPLICATE_DEPLOYED_ZIP")
  for path,(previous,_) in EXPECTED.items():
   if previous:
    check(path in names,"BASELINE_MEMBER_MISSING:"+path)
    if path != WATCHDOG_FILE:
     check(blob(old.read(path))==previous,"PRIVATE_LAMBDA_SOURCE_CHANGED:"+path)
   else:
    check(path not in names,"POLICY_ALREADY_EXISTS_REVIEW")
  if WATCHDOG_FILE in EXPECTED:
   private_watchdog=old.read(WATCHDOG_FILE)
   patched_watchdog=patch_private_watchdog(private_watchdog)
   patches[WATCHDOG_FILE]=patched_watchdog
   # Audit the three V2 changes against the pinned *reference* baseline.
   # If baseline code has the expected SHA, transforming it must result in
   # the exact pinned candidate watchdog SHA.
   if blob(private_watchdog)==EXPECTED[WATCHDOG_FILE][0]:
    check(blob(patched_watchdog)==EXPECTED[WATCHDOG_FILE][1],
          "REFERENCE_WATCHDOG_PATCH_NOT_PINNED")
  # Preserve ALL private Paper accounting changes. Alter only its scheduled
  # trading-day resolver; 12:45 UTC is a pre-open New York morning.
  import ast
  check(PAPER_FILE in names,"DEPLOYED_PAPER_HANDLER_MISSING")
  paper=old.read(PAPER_FILE).decode("utf-8")
  check(paper.count(PAPER_BEFORE)==1,"PRIVATE_PAPER_SCHEDULE_RESOLVER_CHANGED")
  patched_paper=paper.replace(PAPER_BEFORE,PAPER_AFTER)
  ast.parse(patched_paper,filename=PAPER_FILE)
  patches[PAPER_FILE]=patched_paper.encode("utf-8")
  with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as out:
   for z in rows:
    out.writestr(z, patches.get(z.filename,old.read(z.filename)))
   out.writestr("stocklens/st_signal_retry_policy.py",patches["stocklens/st_signal_retry_policy.py"])
 data=target.getvalue()
 check(len(data)<49_000_000,"DIRECT_UPDATE_PACKAGE_TOO_LARGE")
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  check(len(z.namelist())==len(set(z.namelist())),"CANDIDATE_DUPLICATE_MEMBERS")
  for path,(_,new_sha) in EXPECTED.items():
   if path == WATCHDOG_FILE:
    check(z.read(path)==patches[path],"PRIVATE_WATCHDOG_PATCH_BYTES_CHANGED")
    check(z.read(path)!=private_watchdog,"PRIVATE_WATCHDOG_NOOP")
   else:
    check(blob(z.read(path))==new_sha,"CANDIDATE_MEMBER_SHA_MISMATCH:"+path)
 return data

def outputs(cf,stack):
 records=cf.describe_stacks(StackName=stack)["Stacks"]
 check(len(records)==1 and records[0]["StackStatus"] in ("CREATE_COMPLETE","UPDATE_COMPLETE"),"STACK_NOT_STABLE:"+stack)
 return {x["OutputKey"]:x["OutputValue"] for x in records[0].get("Outputs",[])}

def rule(events,name):
 r=events.describe_rule(Name=name)
 ts=events.list_targets_by_rule(Rule=name).get("Targets",[])
 check(len(ts)==1 and r.get("EventBusName") in (None,"default"),"INVALID_EVENT_TARGET_OR_BUS:"+name)
 check(not r.get("EventPattern") and not r.get("RoleArn"),"UNEXPECTED_EVENT_RULE_PROPERTIES:"+name)
 return r,ts[0]

def read_state(session):
 check(session.client("sts").get_caller_identity()["Account"]==ACCOUNT,"WRONG_AWS_ACCOUNT")
 cf,ev,lm,s3=(session.client(x) for x in ("cloudformation","events","lambda","s3"))
 st,prod=outputs(cf,ST),outputs(cf,PROD)
 check(st.get("CandidateDataBucket") and prod.get("CandidateDataBucket")
  and st["CandidateDataBucket"]!=prod["CandidateDataBucket"],"BUCKET_NOT_ISOLATED")
 check(s3.get_bucket_versioning(Bucket=st["CandidateDataBucket"]).get("Status")=="Enabled","ST_BUCKET_NOT_VERSIONED")
 funcs={}
 for key in LAMBDA_KEYS:
  name=st[key]
  check(name.startswith(ST+"-"),"WRONG_ST_FUNCTION:"+key)
  cfg=lm.get_function_configuration(FunctionName=name)
  check(cfg.get("State")=="Active" and cfg.get("LastUpdateStatus")=="Successful"
   and cfg.get("RevisionId") and cfg.get("CodeSha256"),"LAMBDA_NOT_STABLE:"+key)
  funcs[key]=(name,cfg)
 check(len({funcs[k][1]["CodeSha256"] for k in
  ("CandidateFunctionName","CandidatePaperFunctionName","CandidateSessionWatchdogFunctionName")})==1,
  "SIGNAL_PAPER_WATCHDOG_ZIPS_NOT_IDENTICAL")
 for key in (*FN.keys(),"CandidateOrchestratorRuleName"):
  r,t=rule(ev,st[key])
  check(r["State"]==("DISABLED" if key=="CandidateOrchestratorRuleName" else "ENABLED"),
   "ST_RULE_UNEXPECTED_STATE:"+key)
  f=FN.get(key,"CandidateOrchestratorFunctionName")
  check(t["Arn"].rsplit(":",1)[-1]==funcs[f][0],"ST_RULE_TARGET_CHANGED:"+key)
  if key in OLD: check(r["ScheduleExpression"]==OLD[key],"ST_RULE_SCHEDULE_CHANGED:"+key)
  check(rule(ev,prod[key])[0]["State"]=="DISABLED","PROD_RULE_ACTIVE:"+key)
 variables=funcs["CandidateSessionWatchdogFunctionName"][1].get("Environment",{}).get("Variables",{})
 check(variables.get("STOCKLENS_DATA_BUCKET")==st["CandidateDataBucket"],"WD_BUCKET_DIFFERENT")
 check("SIGNAL_V2_START_SESSION" not in variables,"V2_ALREADY_CONFIGURED_STOP")
 check(funcs["CandidateFunctionName"][1].get("Environment",{}).get("Variables",{}).get("STOCKLENS_DATA_BUCKET")==st["CandidateDataBucket"],"SIGNAL_BUCKET_DIFFERENT")
 return ev,lm,st,prod,funcs,variables

def get_deployed_zip(lm,name,current):
 response=lm.get_function(FunctionName=name)
 check(response["Configuration"]["CodeSha256"]==current,"ZIP_REVISION_CHANGED")
 with urllib.request.urlopen(response["Code"]["Location"],timeout=90) as f:
  data=f.read(60_000_001)
 check(len(data)<60_000_000 and sha256b64(data)==current,"DEPLOYED_ZIP_SHA_MISMATCH")
 return data

def wait_verified(lm,fn,sha):
 lm.get_waiter("function_updated_v2").wait(FunctionName=fn,
  WaiterConfig={"Delay":5,"MaxAttempts":45})
 cfg=lm.get_function_configuration(FunctionName=fn)
 check(cfg.get("CodeSha256")==sha and cfg["State"]=="Active"
  and cfg["LastUpdateStatus"]=="Successful","POST_UPDATE_LAMBDA_BAD:"+fn)
 return cfg

def apply(ev,lm,st,prod,funcs,env,payload):
 target=sha256b64(payload)
 # Existing private Paper source is surgically updated only at the scheduled
 # session resolver; its accounting code, receipts and all PROD functions stay unchanged.
 for key in ("CandidateFunctionName","CandidatePaperFunctionName","CandidateSessionWatchdogFunctionName"):
  name,cfg=funcs[key]
  result=lm.update_function_code(FunctionName=name,ZipFile=payload,
   RevisionId=cfg["RevisionId"],Publish=False)
  check(result.get("CodeSha256")==target,"CODE_WRITE_RETURN_MISMATCH:"+key)
  wait_verified(lm,name,target)
  print("ST_LAMBDA_CODE_VERIFIED",key,flush=True)
 wd=funcs["CandidateSessionWatchdogFunctionName"][0]
 newcfg=lm.get_function_configuration(FunctionName=wd)
 lm.update_function_configuration(FunctionName=wd,RevisionId=newcfg["RevisionId"],
  Environment={"Variables":{**env,"SIGNAL_V2_START_SESSION":START}})
 wait_verified(lm,wd,target)
 check(lm.get_function_configuration(FunctionName=wd)["Environment"]["Variables"].get("SIGNAL_V2_START_SESSION")==START,
  "WATCHDOG_V2_ACTIVATION_MISSING")
 print("ST_WATCHDOG_V2_VERIFIED",START,flush=True)
 for key,new_schedule in UPDATED.items():
  old,_=rule(ev,st[key])
  ev.put_rule(Name=st[key],ScheduleExpression=new_schedule,State="ENABLED",
    Description=old.get("Description",""))
  current,target_rule=rule(ev,st[key])
  check(current["State"]=="ENABLED" and current["ScheduleExpression"]==new_schedule
    and target_rule["Arn"].rsplit(":",1)[-1]==funcs[FN[key]][0],
    "RULE_AFTER_UPDATE_UNVERIFIED:"+key)
  print("ST_RULE_UPDATED",key,flush=True)
 for key in (*FN.keys(),"CandidateOrchestratorRuleName"):
  check(rule(ev,prod[key])[0]["State"]=="DISABLED","PROD_SCHEDULE_CHANGED")
 return {"status":"ST_RELEASE_APPLIED_AWAITING_PROSPECTIVE_SESSION_ACCEPTANCE",
  "new_lambda_sha256_b64":target,"v2_start":START,
  "paper_chain_gap_old_still_exists":True,"prod_untouched":True,
  "no_broker":True,"no_synthetic_paper":True,"old_alarm_history_unmodified":True}

def main():
 p=argparse.ArgumentParser()
 p.add_argument("mode",choices=["inspect","apply"])
 p.add_argument("--yes",action="store_true")
 p.add_argument("--acknowledge-st-cfn-drift",action="store_true")
 args=p.parse_args()
 check(args.mode=="inspect" or (args.yes and args.acknowledge_st_cfn_drift),
  "APPLY_REQUIRES_EXPLICIT_APPROVAL_FLAGS")
 now=datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
 check(date.fromisoformat(START)>=now.date(),"PINNED_V2_ACTIVATION_DATE_IS_HISTORIC")
 import boto3
 session=boto3.session.Session(region_name=REGION)
 ev,lm,st,prod,funcs,env=read_state(session)
 fn,cfg=funcs["CandidateFunctionName"]
 oldzip=get_deployed_zip(lm,fn,cfg["CodeSha256"])
 payload=prepare_zip(oldzip)
 print(json.dumps({"status":"ST_RELEASE_PREFLIGHT_PASS","mode":args.mode,
  "pinned_git_ref":REF,"candidate_zip_sha256_b64":sha256b64(payload),
  "original_zip_sha256_b64":cfg["CodeSha256"],"proposed_signal_cron":UPDATED["CandidateSignalOnlyRuleName"],
  "proposed_paper_cron":UPDATED["CandidatePaperOnlyRuleName"],
  "monitoring_v2_start":START,"prod_schedules_all_disabled":True,
  "s3_receipts_unchanged":True,"no_broker":True},sort_keys=True),flush=True)
 if args.mode=="inspect": print("INSPECT_PASS_NO_AWS_WRITES")
 else:
  print("EXPLICIT_OPERATOR_APPROVAL_ST_ONLY_CFN_DRIFT",flush=True)
  print(json.dumps(apply(ev,lm,st,prod,funcs,env,payload),sort_keys=True))

if __name__=="__main__":
 try: main()
 except Exception as exc:
  print(json.dumps({"status":"BLOCKED_OR_PARTIAL_ST_RELEASE_REQUIRES_REVIEW",
    "error":str(exc)[:250],"no_prod_mutations":True,"no_broker":True}),file=sys.stderr)
  sys.exit(2)
