from __future__ import annotations
import csv,json,math
from datetime import date
from pathlib import Path
LEAN=Path("governance/qc_lean_daily_portfolio.csv")
REFERENCE=Path("governance/qc_lean_portfolio_reference.csv")
OUT=Path("shadow_history/qc_portfolio_path_parity.json")
NAV_REL_TOL=1e-8
CASH_ABS_TOL=1e-6
QTY_ABS_TOL=1e-8
FIELDS=("total_portfolio_value","cash","tqqq_quantity","qld_quantity","qqq_quantity")
def _rows(p):
 with Path(p).open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
def _metrics(rows):
 if len(rows)<2:return None
 start=date.fromisoformat(rows[0]["date"]);end=date.fromisoformat(rows[-1]["date"]);years=(end-start).days/365.2425
 first=float(rows[0]["total_portfolio_value"]);last=float(rows[-1]["total_portfolio_value"])
 return {"start":rows[0]["date"],"end":rows[-1]["date"],"start_nav":first,"end_nav":last,"nav_multiple":last/first,"calendar_years":years,"cagr":(last/first)**(1/years)-1 if first>0 and years>0 else None}
def compare(lean=LEAN,reference=REFERENCE,out=OUT):
 lp,rp=Path(lean),Path(reference)
 if not lp.exists() or not rp.exists():
  r={"status":"BLOCKED_MISSING_PORTFOLIO_PATH","portfolio_path_parity_proven":False,"return_parity_proven":False,"compared_sessions":0,"missing":[str(p) for p in (lp,rp) if not p.exists()],"tolerances":{"nav_rel":NAV_REL_TOL,"cash_abs":CASH_ABS_TOL,"quantity_abs":QTY_ABS_TOL}}
  Path(out).parent.mkdir(parents=True,exist_ok=True);Path(out).write_text(json.dumps(r,indent=2)+"\n");return r
 l=_rows(lp);ref=_rows(rp);rd={x["date"]:x for x in ref};m=[];matched=0
 for x in l:
  y=rd.get(x["date"]);ok=y is not None
  if ok:
   ok=math.isclose(float(x["total_portfolio_value"]),float(y["total_portfolio_value"]),rel_tol=NAV_REL_TOL,abs_tol=1e-6)
   ok &= math.isclose(float(x["cash"]),float(y["cash"]),abs_tol=CASH_ABS_TOL)
   for k in ("tqqq_quantity","qld_quantity","qqq_quantity"):ok &= math.isclose(float(x[k]),float(y[k]),abs_tol=QTY_ABS_TOL)
  if ok:matched+=1
  elif len(m)<20:m.append({"date":x["date"],"lean":{k:x.get(k) for k in FIELDS},"reference":({k:y.get(k) for k in FIELDS} if y else None)})
 exact_dates=len(l)==len(ref)==len(rd) and [x["date"] for x in l]==[x["date"] for x in ref]
 path_proven=bool(l) and exact_dates and matched==len(l);lm,rm=_metrics(l),_metrics(ref)
 return_proven=bool(path_proven and lm and rm and math.isclose(lm["nav_multiple"],rm["nav_multiple"],rel_tol=NAV_REL_TOL) and math.isclose(lm["cagr"],rm["cagr"],rel_tol=NAV_REL_TOL))
 r={"status":"EXACT_MATCH" if return_proven else "MISMATCH","portfolio_path_parity_proven":path_proven,"return_parity_proven":return_proven,"compared_sessions":len(l),"matched_sessions":matched,"mismatch_count":len(l)-matched,"exact_date_path":exact_dates,"lean_metrics":lm,"reference_metrics":rm,"first_mismatches":m,"tolerances":{"nav_rel":NAV_REL_TOL,"cash_abs":CASH_ABS_TOL,"quantity_abs":QTY_ABS_TOL},"scope":"LEAN-exported portfolio path versus independently retained common-start portfolio reference. No Yahoo reconstruction can satisfy this evidence class."}
 Path(out).parent.mkdir(parents=True,exist_ok=True);Path(out).write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(compare(),indent=2))
