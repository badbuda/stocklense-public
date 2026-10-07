from __future__ import annotations
import json, math, hashlib
from pathlib import Path
from simulator_contract import COST_SENSITIVITY_BPS,DEFAULT_TRANSACTION_COST_BPS,EVIDENCE_CLASS,EXECUTION_PARITY,AUTOMATIC_MODEL_CHANGE,as_dict as simulator_contract
from publication_identity import identity as publication_identity
from backtest_contract import FrozenExposureReplayAdapter, stocklens_8_request
from backtest_engine import run_backtest


def _validate_inputs(initial,monthly,cost_bps):
 vals=(float(initial),float(monthly),float(cost_bps))
 if not all(math.isfinite(x) for x in vals): raise RuntimeError("SIMULATOR_INPUT_NON_FINITE")
 if vals[0]<=0: raise RuntimeError("SIMULATOR_INITIAL_CAPITAL_MUST_BE_POSITIVE")
 if vals[1]<0: raise RuntimeError("SIMULATOR_NEGATIVE_MONTHLY_CONTRIBUTION_UNSUPPORTED")
 if vals[2]<0: raise RuntimeError("SIMULATOR_NEGATIVE_TRANSACTION_COST_UNSUPPORTED")
 return vals

def run_cost_path(rows,initial,monthly,cost_bps):
 initial,monthly,cost_bps=_validate_inputs(initial,monthly,cost_bps)
 nav=float(initial); total_cost=0.0; last_month=rows[0]["date"][:7]
 for i in range(1,len(rows)):
  r,p=rows[i],rows[i-1]; month=r["date"][:7]
  if month!=last_month: nav+=monthly; last_month=month
  nav*=1+(r["close"]/p["close"]-1)*p["leverage"]
  if r.get("event"):
   cost=nav*abs(r["leverage"]-p["leverage"])*cost_bps/10000; nav-=cost; total_cost+=cost
 return {"end_equity":nav,"total_estimated_transaction_cost":total_cost}

def run(path="docs/workbench.json", initial=100000.0, monthly=3500.0, cost_bps=DEFAULT_TRANSACTION_COST_BPS, out=None):
 initial,monthly,cost_bps=_validate_inputs(initial,monthly,cost_bps)
 d=json.loads(Path(path).read_text())
 contract=d.get("simulator_contract")
 expected=simulator_contract()
 if not contract: raise RuntimeError("SIMULATOR_CONTRACT_MISSING")
 if contract!=expected: raise RuntimeError("SIMULATOR_CONTRACT_DRIFT")
 rows=d.get("replay",{}).get("rows") or []
 adapter=FrozenExposureReplayAdapter()
 try: adapter.validate_rows(rows)
 except ValueError as exc: raise RuntimeError("SIMULATOR_REPLAY_INVALID:"+str(exc)) from exc
 request=stocklens_8_request(initial,monthly,cost_bps,rows[0]["date"],rows[-1]["date"])
 generic_run=run_backtest(rows,request,adapter)
 nav=qnav=paid=float(initial); peak=nav; maxdd=0.0; changes=0; total_costs=0.0
 last_month=rows[0]["date"][:7]
 capital_ledger=[{"date":rows[0]["date"],"nav_before_contribution":0.0,"contribution":float(initial),"nav_after_contribution":nav,"gross_market_pl":0.0,"nav_before_cost":nav,"estimated_cost":0.0,"net_nav":nav,"paid_capital":paid,"drawdown":0.0}]
 cost_ledger=[]
 for i in range(1,len(rows)):
  r,p=rows[i],rows[i-1]; month=r["date"][:7]; contribution=0.0
  if month!=last_month:
   contribution=float(monthly); nav+=contribution; qnav+=contribution; paid+=contribution; last_month=month
  nav_before_market=nav; qret=r["close"]/p["close"]-1; gross_market_pl=nav_before_market*qret*adapter.target_exposure(p,r)
  nav+=gross_market_pl; qnav*=1+qret
  if not math.isfinite(nav) or nav<=0: raise RuntimeError("SIMULATOR_CAPITAL_DEPLETED_BEFORE_COST")
  cost=0.0
  if r.get("event"):
   turnover=abs(r["leverage"]-p["leverage"]); cost=nav*turnover*cost_bps/10000; nav-=cost; total_costs+=cost; changes+=1
   cost_ledger.append({"date":r["date"],"event":r["event"],"turnover":turnover,"estimated_cost":cost,"cumulative_cost":total_costs,"nav_after_cost":nav})
  peak=max(peak,nav); dd=nav/peak-1; maxdd=min(maxdd,dd)
  capital_ledger.append({"date":r["date"],"nav_before_contribution":nav_before_market-contribution,"contribution":contribution,"nav_after_contribution":nav_before_market,"gross_market_pl":gross_market_pl,"nav_before_cost":nav+cost,"estimated_cost":cost,"net_nav":nav,"paid_capital":paid,"drawdown":dd})
 vals=[nav,qnav,paid,maxdd,total_costs]
 if not all(math.isfinite(x) for x in vals): raise RuntimeError("SIMULATOR_NON_FINITE_OUTPUT")
 if nav<=0 or paid<=0: raise RuntimeError("SIMULATOR_INVALID_CAPITAL_PATH")
 eps=1e-9
 row_reconciliation_failures=sum(1 for x in capital_ledger[1:] if not (math.isclose(x["nav_after_contribution"]+x["gross_market_pl"],x["nav_before_cost"],rel_tol=eps,abs_tol=eps) and math.isclose(x["nav_before_cost"]-x["estimated_cost"],x["net_nav"],rel_tol=eps,abs_tol=eps)))
 nav_continuity_failures=sum(1 for i in range(1,len(capital_ledger)) if not math.isclose(capital_ledger[i]["nav_before_contribution"],capital_ledger[i-1]["net_nav"],rel_tol=eps,abs_tol=eps))
 paid_capital_continuity_failures=sum(1 for i in range(1,len(capital_ledger)) if not math.isclose(capital_ledger[i]["paid_capital"],capital_ledger[i-1]["paid_capital"]+capital_ledger[i]["contribution"],rel_tol=eps,abs_tol=eps))
 market_pl_failures=sum(1 for i in range(1,len(capital_ledger)) if not math.isclose(capital_ledger[i]["gross_market_pl"],capital_ledger[i]["nav_after_contribution"]*(rows[i]["close"]/rows[i-1]["close"]-1)*adapter.target_exposure(rows[i-1],rows[i]),rel_tol=eps,abs_tol=eps))
 invariants={
  "ledger_rows_match":len(capital_ledger)==len(rows),
  "ending_nav_matches":math.isclose(capital_ledger[-1]["net_nav"],nav,rel_tol=eps,abs_tol=eps),
  "paid_capital_matches":math.isclose(capital_ledger[-1]["paid_capital"],paid,rel_tol=eps,abs_tol=eps),
  "cost_total_matches":math.isclose(sum(x["estimated_cost"] for x in capital_ledger),total_costs,rel_tol=eps,abs_tol=eps),
  "event_cost_rows_match":len(cost_ledger)==changes,
  "every_session_reconciles":row_reconciliation_failures==0,
  "nav_continuity":nav_continuity_failures==0,
  "paid_capital_continuity":paid_capital_continuity_failures==0,
  "market_pl_formula":market_pl_failures==0,
 }
 if not all(invariants.values()): raise RuntimeError("SIMULATOR_ACCOUNTING_INVARIANT_FAILED")
 parity_fields={"end_equity":(generic_run["end_equity"],nav),"paid_capital":(generic_run["paid_capital"],paid),"max_drawdown":(generic_run["max_drawdown"],maxdd),"total_estimated_transaction_cost":(generic_run["total_estimated_transaction_cost"],total_costs)}
 generic_parity={k:math.isclose(a,b,rel_tol=eps,abs_tol=eps) for k,(a,b) in parity_fields.items()}
 if not all(generic_parity.values()): raise RuntimeError("GENERIC_ENGINE_FROZEN_PARITY_FAILED")
 sensitivity=[]
 for bps in COST_SENSITIVITY_BPS:
  x=run_cost_path(rows,initial,monthly,bps)
  sensitivity.append({"cost_bps":bps,**x})
 contract_payload=simulator_contract()
 contract_sha256=hashlib.sha256(json.dumps(contract_payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
 replay_fingerprint=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(",",":")).encode()).hexdigest()
 result={"publication_identity":publication_identity(path),"backtest_request":request.__dict__,"strategy_contract":{"strategy_id":adapter.strategy_id,"evidence_class":adapter.evidence_class},"generic_engine":{"status":"PASS","result_kind":generic_run["kind"],"request_sha256":generic_run["request_sha256"],"rows_sha256":generic_run["rows_sha256"],"ledger_sha256":generic_run["ledger_sha256"],"frozen_accounting_parity":generic_parity,"analytics":generic_run.get("analytics",{})},"status":"PASS","sessions":len(rows),"start":rows[0]["date"],"end":rows[-1]["date"],"replay_dataset_sha256":d.get("replay",{}).get("dataset_sha256"),"replay_rows_sha256":replay_fingerprint,"contract_sha256":contract_sha256,"replay_evidence":d.get("replay",{}).get("evidence"),"provenance":{"status":"PASS","dataset_sha256":d.get("replay",{}).get("dataset_sha256"),"replay_rows_sha256":replay_fingerprint,"contract_sha256":contract_sha256,"generation_id":publication_identity(path).get("generation_id"),"evidence_class":EVIDENCE_CLASS,"full_lean_execution_parity":False},"end_equity":nav,"qqq_end_equity":qnav,"paid":paid,"replay_profit_loss":nav-paid,"ending_to_paid_multiple":nav/paid,"max_drawdown":maxdd,"exposure_changes":changes,"total_estimated_transaction_cost":total_costs,"cost_sensitivity":sensitivity,"cost_ledger":cost_ledger,"accounting_invariants":{"status":"PASS",**invariants},"contract":contract_payload,"evidence":EVIDENCE_CLASS+"_NOT_LEAN_EXECUTION_PARITY","full_lean_execution_parity":EXECUTION_PARITY,"automatic_model_change":AUTOMATIC_MODEL_CHANGE}
 if out:
  p=Path(out); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(result,indent=2)+chr(10))
 return result

if __name__=="__main__":
 print(json.dumps(run(out="docs/simulator_smoke.json"),indent=2))
