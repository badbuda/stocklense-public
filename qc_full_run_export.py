from __future__ import annotations
import csv,hashlib,json,math
from pathlib import Path
from json_artifacts import write_json_atomic
SCHEMA=Path("governance/qc_lean_full_run_export_schema.json")
DAILY=Path("governance/qc_lean_full_daily.csv")
ORDERS=Path("governance/qc_lean_full_orders.csv")

def _sha(rows,cols):
 return hashlib.sha256(chr(10).join(",".join(str(r.get(k,"")) for k in cols) for r in rows).encode()).hexdigest()

def _transition_fingerprint(rows):
 transitions=[];prev=None
 for r in rows:
  lev=float(r["leverage"])
  if prev is None or lev!=prev: transitions.append([r["date"],lev])
  prev=lev
 canonical=json.dumps(transitions,separators=(",",":"))
 return transitions,hashlib.sha256(canonical.encode()).hexdigest()

def validate(daily=DAILY,orders=ORDERS):
 s=json.loads(SCHEMA.read_text());errors=[];details={}
 for name,path,cols in (("daily",Path(daily),s["daily_required_columns"]),("orders",Path(orders),s["orders_required_columns"])):
  if not path.exists():errors.append(name.upper()+"_MISSING");continue
  rows=list(csv.DictReader(path.open(newline="",encoding="utf-8")));missing=[c for c in cols if c not in (rows[0] if rows else {})]
  details[name]={"rows":len(rows),"sha256":_sha(rows,cols),"missing_columns":missing}
  if missing:errors.append(name.upper()+"_COLUMNS");continue
  if name=="daily":
   dates=[r["date"] for r in rows];c=s["run_contract"]
   if len(rows)!=c["expected_sessions"]:errors.append("DAILY_SESSION_COUNT")
   if not rows or dates[0]!=c["first_date"] or dates[-1]!=c["last_date"]:errors.append("DAILY_BOUNDARIES")
   if len(dates)!=len(set(dates)):errors.append("DAILY_DUPLICATE_DATES")
   finite=True
   for r in rows:
    for k in ("close","sma50","sma200","vol20","mom12","leverage","equity","cash","holdings_value"):
     try:finite=finite and math.isfinite(float(r[k]))
     except:finite=False
   if not finite:errors.append("DAILY_NONFINITE")
   transitions,tsha=_transition_fingerprint(rows);details[name]["derived_transition_count"]=len(transitions);details[name]["derived_transition_sha256"]=tsha
   if len(transitions)!=s["golden_constraints"]["transition_count"]:errors.append("TRANSITION_COUNT")
   if tsha!=s["golden_constraints"]["transition_sha256"]:errors.append("TRANSITION_SHA")
  else:
   if len(rows)!=s["golden_constraints"]["order_count"]:errors.append("ORDER_COUNT")
   if details[name]["sha256"]!=s["golden_constraints"]["order_sha256"]:errors.append("ORDER_SHA")
 errors=sorted(set(errors))
 return {"status":"VALID" if not errors else ("MISSING" if errors and all(x.endswith("_MISSING") for x in errors) else "INVALID"),"execution_parity_ready":not errors,"errors":errors,"details":details,"automatic_model_change":False}

def _xirr(cashflows,guess=.15):
 # dated money-weighted return; positive=money received, negative=capital contributed
 from datetime import date
 if not cashflows or not any(v<0 for _,v in cashflows) or not any(v>0 for _,v in cashflows): return None
 d0=cashflows[0][0]
 def f(rate): return sum(v/((1+rate)**((d-d0).days/365.2425)) for d,v in cashflows)
 lo,hi=-.9999,10.0
 flo,fhi=f(lo),f(hi)
 for _ in range(20):
  if flo*fhi<=0: break
  hi*=2;fhi=f(hi)
 if flo*fhi>0:return None
 for _ in range(200):
  mid=(lo+hi)/2;fm=f(mid)
  if abs(fm)<1e-8:return mid
  if flo*fm<=0:hi=mid
  else:lo=mid;flo=fm
 return (lo+hi)/2

def performance_metrics(daily=DAILY):
 from datetime import date
 p=Path(daily)
 if not p.exists():return {"status":"BLOCKED_MISSING_FULL_EXPORT"}
 rows=list(csv.DictReader(p.open(newline="",encoding="utf-8")))
 if not rows:return {"status":"BLOCKED_EMPTY_FULL_EXPORT"}
 start=date.fromisoformat(rows[0]["date"]);end=date.fromisoformat(rows[-1]["date"])
 start_equity=float(rows[0]["equity"]);end_equity=float(rows[-1]["equity"])
 # Equity alone cannot identify external contributions. Require explicit cashflow column before money-weighted CAGR is claimed.
 has_cf="external_cashflow" in rows[0]
 flows=[]
 if has_cf:
  flows=[(date.fromisoformat(r["date"]),-float(r.get("external_cashflow") or 0)) for r in rows if float(r.get("external_cashflow") or 0)!=0]
  flows.insert(0,(start,-start_equity));flows.append((end,end_equity))
 return {"status":"READY" if has_cf else "BLOCKED_CASHFLOW_SEMANTICS","start_equity":start_equity,"end_equity":end_equity,"years":(end-start).days/365.2425,"money_weighted_annual_return":_xirr(flows) if has_cf else None,"cashflow_semantics_proven":has_cf,"note":"No CAGR/annual-return claim is emitted from equity endpoints when external cash-flow semantics are absent."}

def build(out="shadow_history/qc_full_run_export.json"):
 r=validate();r["performance_metrics"]=performance_metrics();write_json_atomic(out,r);return r
if __name__=="__main__":print(json.dumps(build(),indent=2))
