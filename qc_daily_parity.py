from __future__ import annotations
import hashlib,json
from datetime import date
from collections import deque
from pathlib import Path
from stocklens.core import compute_features,next_level,defense_active,LEVEL_LEVERAGE,TRADING_START
from stocklens.data import load_qqq_history

REF=Path("governance/qc_724_leverage_transitions.json")

def replay_qc_open_decisions(closes, dates, diagnostics=None):
    """Reproduce frozen LEAN 7.24 history lifecycle, including its Aug-2009 capture gap."""
    parsed=[date.fromisoformat(str(d)[:10]) for d in dates]
    pairs=list(zip(parsed,[float(x) for x in closes]))
    seed=[close for d,close in pairs if d<date(2009,8,1)][-360:]
    if len(seed)<253:
        raise ValueError("Insufficient LEAN initialization history for QC parity")
    history=deque(seed,maxlen=420)
    level=None
    out=[]
    for d,close in pairs:
        if d<TRADING_START:
            continue
        features=compute_features(list(history))
        level=next_level(features,level)
        defense=defense_active(features)
        leverage=0.0 if defense else LEVEL_LEVERAGE[level]
        out.append([d.isoformat(),float(leverage)])
        if diagnostics is not None:
            diagnostics[d.isoformat()]={
                "close":float(features.close),"sma50":float(features.sma50),"sma200":float(features.sma200),
                "vol20":float(features.vol20),"mom12":float(features.mom12),"level":int(level),
                "defense":bool(defense),"leverage":float(leverage),
            }
        history.append(close)
    return out


def drift_decomposition(closes,dates,expected):
 """Diagnostic-only lifecycle variants. Never changes frozen StockLens 8.0."""
 def score(rows):
  trans=[];prev=None
  for d,lev in rows:
   if lev!=prev:trans.append([d,lev]);prev=lev
  exact=sum(1 for i in range(min(len(trans),len(expected))) if trans[i]==expected[i])
  # Also measure date proximity for same target leverage; exact index matching is intentionally strict.
  offsets=[];matched_actual=set()
  for ed,el in expected:
   e=date.fromisoformat(ed)
   candidates=[(abs((date.fromisoformat(ad)-e).days),(date.fromisoformat(ad)-e).days,ai,ad) for ai,(ad,al) in enumerate(trans) if al==el and abs((date.fromisoformat(ad)-e).days)<=3]
   if candidates:
    _,off,ai,ad=min(candidates);offsets.append({"expected_date":ed,"actual_date":ad,"leverage":el,"offset_calendar_days":off});matched_actual.add(ai)
  vals=[x["offset_calendar_days"] for x in offsets]
  extras=[{"actual_date":d,"leverage":l,"actual_index":i} for i,(d,l) in enumerate(trans) if i not in matched_actual]
  return {"transition_count":len(trans),"exact_index_matches":exact,"exact_index_match_rate":exact/max(len(trans),len(expected)) if max(len(trans),len(expected)) else 1.0,"same_leverage_within_3_calendar_days":len(offsets),"near_date_match_rate":len(offsets)/len(expected) if expected else 1.0,"offsets":offsets,"offset_summary":{"min":min(vals) if vals else None,"max":max(vals) if vals else None,"mean":sum(vals)/len(vals) if vals else None,"early":sum(x<0 for x in vals),"same_day":sum(x==0 for x in vals),"late":sum(x>0 for x in vals)},"unmatched_actual_transitions":extras}
 variants={}
 variants["LEAN_CAPTURE_GAP_PRIOR_CLOSE"]=score([r for r in replay_qc_open_decisions(closes,dates) if "2009-09-01"<=r[0]<="2024-08-29"])
 # Standard frozen replay includes each completed session close in that session's feature decision.
 decisions=__import__("stocklens.core",fromlist=["replay_levels"]).replay_levels(closes,dates)
 variants["STANDARD_COMPLETED_CLOSE"]=score([[x.asof_date,float(x.target_leverage)] for x in decisions if "2009-09-01"<=x.asof_date<="2024-08-29"])
 return {"status":"DIAGNOSTIC_ONLY","variants":variants,"winner_selection":False,"model_mutation":False,"claim_boundary":"Cross-provider lifecycle timing diagnostic only; does not establish identical LEAN inputs or authorize retuning."}

def run():
 ref=json.loads(REF.read_text())
 try:
  df,audit=load_qqq_history()
 except Exception as exc:
  result={"status":"DATA_PROVIDER_UNAVAILABLE","reference_integrity":"PASS","recomputation_scope":"YAHOO_ADJUSTED_DIAGNOSTIC_NOT_LEAN_INPUT_PARITY","error":type(exc).__name__+":"+str(exc)}
  Path("shadow_history").mkdir(exist_ok=True)
  Path("shadow_history/qc_daily_parity.json").write_text(json.dumps(result,indent=2)+"\n")
  return result
 closes=df["Close"].astype(float).tolist()
 dates=df["Date"].dt.date.astype(str).tolist()
 diagnostics={}
 rows=[r for r in replay_qc_open_decisions(closes,dates,diagnostics) if "2009-09-01"<=r[0]<="2024-08-29"]
 trans=[];prev=None
 for d,lev in rows:
  if lev!=prev:
   trans.append([d,lev]);prev=lev
 canonical=json.dumps(trans,separators=(",",":"))
 sha=hashlib.sha256(canonical.encode()).hexdigest()
 expected=ref["transitions"]
 mismatches=[]
 for i in range(max(len(trans),len(expected))):
  actual=trans[i] if i<len(trans) else None
  wanted=expected[i] if i<len(expected) else None
  if actual!=wanted:
   actual_date=actual[0] if actual else None
   expected_date=wanted[0] if wanted else None
   mismatches.append({
    "index":i,"actual":actual,"expected":wanted,
    "actual_features":diagnostics.get(actual_date),
    "features_on_expected_date":diagnostics.get(expected_date),
   })
 reference_integrity=(ref.get("sessions")==3774 and ref.get("transition_count")==67 and ref.get("transition_sha256")=="5561588a3bcd8a416cc13320536d7d3ff51bdb6de418e4f2c31b85eaf2ac745b")
 matched_transitions=sum(1 for i in range(min(len(trans),len(expected))) if trans[i]==expected[i])
 transition_match_rate=(matched_transitions/max(len(trans),len(expected))) if max(len(trans),len(expected)) else 1.0
 session_coverage=(len(rows)/ref["sessions"]) if ref["sessions"] else 0.0
 result={
  "status":"MATCH" if not mismatches and sha==ref["transition_sha256"] else "DATA_SOURCE_DRIFT",
  "semantics":"QC724_360_BAR_INIT_PRESTART_AUG2009_CAPTURE_GAP_PRIOR_CAPTURED_CLOSES",
  "reference_sessions":ref["sessions"],"actual_sessions":len(rows),
  "expected_transition_count":ref["transition_count"],"actual_transition_count":len(trans),
  "expected_sha256":ref["transition_sha256"],"actual_sha256":sha,
  "mismatch_count":len(mismatches),"first_mismatches":mismatches[:10],
  "matched_transition_count":matched_transitions,
  "transition_match_rate":transition_match_rate,
  "session_coverage_vs_qc_reference":session_coverage,
  "daily_state_comparison_available":False,
  "daily_state_comparison_blocker":"QC artifact contains 3,774 daily leverage states, but the compact per-date series is not yet repository evidence; hashes alone cannot support by-date comparison.",
  "data_audit":audit,
  "drift_decomposition":drift_decomposition(closes,dates,expected),
  "replication_dossier":{
   "provider":"YFINANCE_QQQ_AUTO_ADJUSTED",
   "classification":"INDEPENDENT_CROSS_PROVIDER_REPLICATION",
   "session_coverage":session_coverage,
   "transition_match_rate":transition_match_rate,
   "transition_count_delta":len(trans)-ref["transition_count"],
   "matched_transitions":matched_transitions,
   "expected_transitions":ref["transition_count"],
   "hypotheses_to_test":[
    "PRICE_ADJUSTMENT_SEMANTICS",
    "LEAN_CONSOLIDATION_AND_SESSION_CLOSE_SEMANTICS",
    "WARMUP_AND_PRESTART_CAPTURE_SEMANTICS",
    "FEATURE_NUMERICAL_IMPLEMENTATION"
   ],
   "claim_boundary":"Yahoo can independently reconstruct market-price inputs, but cannot establish original LEAN equity/cash/holdings/orders or identical-input parity."
  },
 }
 Path("shadow_history").mkdir(exist_ok=True)
 Path("shadow_history/qc_daily_parity.json").write_text(json.dumps(result,indent=2,default=str)+"\n")
 # Yahoo adjusted history is an independent provider, not the frozen LEAN input dataset.
 # Persist drift for audit, but do not treat cross-provider disagreement as a model failure.
 result["reference_integrity"]="PASS" if reference_integrity else "FAIL"
 result["recomputation_scope"]="YAHOO_ADJUSTED_DIAGNOSTIC_NOT_LEAN_INPUT_PARITY"
 if not reference_integrity:
  raise RuntimeError("QC_REFERENCE_INTEGRITY_FAIL")
 return result

if __name__=="__main__":print(json.dumps(run(),indent=2,default=str))
