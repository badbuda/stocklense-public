from __future__ import annotations
import csv,json,hashlib,math
from pathlib import Path
from json_artifacts import write_json_atomic
from publication_identity import identity as publication_identity

FIELDS=["execution_session","signal_date","symbol","side","qty","expected_reference_price","actual_fill_price","actual_fee","source","note"]
ALLOWED_SOURCES={"MANUAL","BROKER_EXPORT","PAPER"}

def _f(x):
 try:return float(x)
 except:return None

def build(path="execution_observation/observations.csv",out="docs/execution_observation.json"):
 p=Path(path); rows=list(csv.DictReader(p.open())) if p.exists() else []
 problems=[];items=[]
 for i,r in enumerate(rows,1):
  side=(r.get("side") or "").upper(); qty=_f(r.get("qty")); ref=_f(r.get("expected_reference_price")); fill=_f(r.get("actual_fill_price")); fee=_f(r.get("actual_fee"))
  if side not in ("BUY","SELL"):problems.append(f"INVALID_SIDE:{i}")
  if qty is None or qty<=0:problems.append(f"INVALID_QTY:{i}")
  if ref is None or ref<=0 or fill is None or fill<=0:problems.append(f"INVALID_PRICE:{i}")
  if fee is None or fee<0:problems.append(f"INVALID_FEE:{i}")
  if not r.get("execution_session"):problems.append(f"MISSING_EXECUTION_SESSION:{i}")
  if not r.get("signal_date"):problems.append(f"MISSING_SIGNAL_DATE:{i}")
  if not r.get("symbol"):problems.append(f"MISSING_SYMBOL:{i}")
  source=(r.get("source") or "").upper()
  if source not in ALLOWED_SOURCES:problems.append(f"INVALID_SOURCE:{i}")
  slip_bps=None
  if ref and fill and side in ("BUY","SELL"):
   signed=(fill/ref-1)*(1 if side=="BUY" else -1); slip_bps=signed*10000
  core={k:r.get(k,"") for k in FIELDS}
  oid=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()[:20]
  items.append({"observation_id":oid,**core,"realized_slippage_bps":slip_bps})
 status="FAIL" if problems else ("ACTIVE" if items else "WAITING_FOR_MANUAL_OBSERVATIONS")
 slips=[x["realized_slippage_bps"] for x in items if x["realized_slippage_bps"] is not None]
 fees=[_f(x.get("actual_fee")) or 0.0 for x in items]
 total_notional=sum((_f(x.get("qty")) or 0)*(_f(x.get("actual_fill_price")) or 0) for x in items)
 adverse=[x for x in slips if x>0]; favorable=[x for x in slips if x<0]
 stats={"mean_realized_slippage_bps":sum(slips)/len(slips) if slips else None,"max_realized_slippage_bps":max(slips) if slips else None,"min_realized_slippage_bps":min(slips) if slips else None,"adverse_fill_count":len(adverse),"favorable_fill_count":len(favorable),"zero_slippage_fill_count":sum(1 for x in slips if x==0),"total_actual_fees":sum(fees),"total_actual_notional":total_notional,"actual_fee_bps_on_notional":sum(fees)/total_notional*10000 if total_notional else None}
 result={"schema_version":2,"publication_identity":publication_identity(),"kind":"STOCKLENS_EXECUTION_OBSERVATION","status":status,"observations":len(items),"problems":problems[:50],"statistics":stats,"quality":{"status":"PASS" if not problems else "FAIL","allowed_sources":sorted(ALLOWED_SOURCES),"validated_rows":len(items),"problem_count":len(problems)},"items":items[-100:],"broker_automation":False,"automatic_trading_authorized":False,"note":"Manual execution-observation ledger only. Actual fills may be entered after a human independently chooses to execute; this artifact never creates or authorizes orders."}
 write_json_atomic(out,result)
 if problems:raise RuntimeError("EXECUTION_OBSERVATION_INVALID:"+",".join(problems[:5]))
 return result

if __name__=="__main__":print(json.dumps(build(),indent=2))
