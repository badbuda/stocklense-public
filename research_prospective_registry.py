from __future__ import annotations
import csv,json
from datetime import date,datetime,timezone
from pathlib import Path
import pandas as pd
from market_calendar import completed_sessions
from prospective_gate import GATE
from publication_identity import _git_sha
from prospective_lineage import lineage

REGISTRY="research/prospective/registry.json"
HEADER="asof_date,strategy_return,baseline_return,strategy_exposure,baseline_exposure"

def _ensure_ledger(path):
 p=Path(path);good=HEADER+chr(10)
 if not p.exists():p.write_text(good);return
 if p.read_text()==HEADER+r"\n":p.write_text(good)

def _completed_xnys_sessions(now_utc=None,start_date=None):
 return {s.date().isoformat() for s in completed_sessions(now_utc,start_date=start_date)}

def update(registry_path=REGISTRY,now_utc=None):
 p=Path(registry_path);p.parent.mkdir(parents=True,exist_ok=True)
 registry=json.loads(p.read_text()) if p.exists() else {"schema_version":1,"candidates":[]}
 original={x["experiment_id"]:(x.get("inception_date"),x.get("fingerprint"),x.get("status"),x.get("automatic_promotion"),x.get("definition_fingerprint")) for x in registry.get("candidates",[])}
 q=json.loads(Path("research/queue.json").read_text());d=json.loads(Path("research/validation/challenger_dossiers.json").read_text())
 dossiers={x["experiment_id"]:x for x in d.get("dossiers",d.get("experiments",[]))};known={x["experiment_id"]:x for x in registry["candidates"]};clock=now_utc or datetime.now(timezone.utc);today=str(clock.date())
 for e in q.get("experiments",[]):
  eid=e["experiment_id"];disp=(dossiers.get(eid) or {}).get("disposition")
  if disp=="PREDECLARED_OBJECTIVE_MET_NOT_PROMOTED":known.setdefault(eid,{"experiment_id":eid,"inception_date":today,"fingerprint":e.get("fingerprint"),"status":"ACTIVE_RESEARCH_ONLY","automatic_promotion":False})
 registry["candidates"]=list(known.values())
 for candidate in registry["candidates"]:
  eid=candidate["experiment_id"]
  if eid in original and original[eid][:4]!=(candidate.get("inception_date"),candidate.get("fingerprint"),candidate.get("status"),candidate.get("automatic_promotion")):
   raise RuntimeError("PROSPECTIVE_REGISTRATION_MUTATED:"+eid)
  if candidate.get("status")!="ACTIVE_RESEARCH_ONLY" or candidate.get("automatic_promotion") is not False or not candidate.get("inception_date") or not candidate.get("fingerprint"):
   raise RuntimeError("PROSPECTIVE_REGISTRATION_GOVERNANCE_INVALID:"+eid)
 updates=[];audits=[]
 for candidate in registry["candidates"]:
  eid=candidate["experiment_id"];hist=Path("research/prospective")/(eid+".csv");_ensure_ledger(hist)
  experiment=next((x for x in q["experiments"] if x["experiment_id"]==eid),None)
  queue_fingerprint=(experiment or {}).get("fingerprint")
  lineage_state=lineage(eid,candidate.get("fingerprint")) if experiment else None
  definition_fp=(lineage_state or {}).get("definition_fingerprint")
  registered_definition_fp=candidate.get("definition_fingerprint")
  if not registered_definition_fp:
   candidate["definition_fingerprint"]=definition_fp;registered_definition_fp=definition_fp
  elif eid in original and original[eid][4] and original[eid][4]!=registered_definition_fp:
   raise RuntimeError("PROSPECTIVE_DEFINITION_REGISTRATION_MUTATED:"+eid)
  definition_matches=bool(definition_fp and registered_definition_fp==definition_fp)
  fingerprint_matches=bool(queue_fingerprint and queue_fingerprint==candidate.get("fingerprint"))
  returns_path=(experiment or {}).get("returns_csv")
  if not experiment or not returns_path or not Path(returns_path).exists():
   audits.append({"experiment_id":eid,"source_status":"MISSING_RETURNS_SOURCE","registered_fingerprint":candidate.get("fingerprint"),"queue_fingerprint":queue_fingerprint,"fingerprint_matches_registration":fingerprint_matches,"registered_definition_fingerprint":registered_definition_fp,"current_definition_fingerprint":definition_fp,"definition_matches_registration":definition_matches,"returns_csv":returns_path,"source_rows":None,"after_inception_rows":None,"accepted_completed_xnys_rows":None,"persisted_prospective_rows":max(0,len(hist.read_text().splitlines())-1),"rejected_pre_or_at_inception":None,"rejected_not_completed_xnys":None,"gate":GATE})
   continue
  completed_sessions=_completed_xnys_sessions(now_utc,candidate["inception_date"]);df=pd.read_csv(experiment["returns_csv"]);source_rows=len(df);after=df[df.date.astype(str)>candidate["inception_date"]];accepted=after[after.date.astype(str).isin(completed_sessions)];audits.append({"experiment_id":eid,"source_status":"AVAILABLE","registered_fingerprint":candidate.get("fingerprint"),"queue_fingerprint":queue_fingerprint,"fingerprint_matches_registration":fingerprint_matches,"registered_definition_fingerprint":registered_definition_fp,"current_definition_fingerprint":definition_fp,"definition_matches_registration":definition_matches,"returns_csv":returns_path,"source_rows":source_rows,"after_inception_rows":len(after),"accepted_completed_xnys_rows":len(accepted),"rejected_pre_or_at_inception":source_rows-len(after),"rejected_not_completed_xnys":len(after)-len(accepted),"gate":GATE});df=accepted
  if df.empty:
   audits[-1]["persisted_prospective_rows"]=max(0,len(hist.read_text().splitlines())-1);continue
  with hist.open(newline="") as fh:existing={r["asof_date"] for r in csv.DictReader(fh)}
  with hist.open("a") as fh:
   for _,row in df.iterrows():
    ds=str(row["date"])
    if ds in existing:continue
    existing.add(ds)
    baseline_return=row["baseline_return"] if "baseline_return" in row.index else row["benchmark_return"]
    fh.write(f'{ds},{row["strategy_return"]},{baseline_return},{row["strategy_exposure"]},{row["baseline_exposure"]}'+chr(10));updates.append([eid,ds])
  audits[-1]["persisted_prospective_rows"]=max(0,len(hist.read_text().splitlines())-1)
 candidate_ids=[x["experiment_id"] for x in registry["candidates"]];audit_ids=[x["experiment_id"] for x in audits]
 if len(audit_ids)!=len(set(audit_ids)) or set(audit_ids)!=set(candidate_ids):
  raise RuntimeError("PROSPECTIVE_AUDIT_COVERAGE_INVALID")
 registry["updated_at_utc"]=clock.isoformat();registry["producer_git_sha"]=_git_sha();registry["ingestion_gate"]=GATE;registry["candidate_count"]=len(candidate_ids);registry["audit_count"]=len(audit_ids);registry["last_ingestion_audit"]=audits;p.write_text(json.dumps(registry,indent=2)+chr(10))
 if not registry["producer_git_sha"]:raise RuntimeError("PROSPECTIVE_PRODUCER_GIT_SHA_MISSING")
 return {"registry":registry,"new_rows":updates,"ingestion_audit":audits}
if __name__=="__main__":print(json.dumps(update(),indent=2))
