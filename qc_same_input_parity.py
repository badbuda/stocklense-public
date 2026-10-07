from __future__ import annotations
import csv,json,math
from pathlib import Path
from stocklens.core import Features,next_level,defense_active,LEVEL_LEVERAGE
from json_artifacts import write_json_atomic
def compare(path="governance/qc_lean_daily_features.csv",out="shadow_history/qc_same_input_parity.json"):
    p=Path(path)
    if not p.exists():
        r={"status":"BLOCKED_MISSING_IDENTICAL_INPUT_EXPORT","same_input_parity_proven":False,"compared_sessions":0}
        write_json_atomic(out,r);return r
    rows=list(csv.DictReader(p.open(encoding="utf-8",newline="")));prev=None;m=[];matched=0
    for r in rows:
        f=Features(close=float(r["close"]),sma50=float(r["sma50"]),sma200=float(r["sma200"]),vol20=float(r["vol20"]),mom12=float(r["mom12"]))
        level=next_level(f,prev);defense=defense_active(f);lev=0.0 if defense else LEVEL_LEVERAGE[level]
        exp_level=int(float(r["level"]));exp_def=str(r["defense"]).strip().lower() in ("1","true","yes");exp_lev=float(r["leverage"])
        ok=level==exp_level and defense==exp_def and math.isclose(lev,exp_lev,abs_tol=1e-12)
        if ok:matched+=1
        elif len(m)<20:m.append({"date":r["date"],"python":{"level":level,"defense":defense,"leverage":lev},"lean":{"level":exp_level,"defense":exp_def,"leverage":exp_lev},"features":{k:float(r[k]) for k in ("close","sma50","sma200","vol20","mom12")}})
        prev=level
    proven=bool(rows) and matched==len(rows)
    result={"status":"EXACT_MATCH" if proven else "MISMATCH","same_input_parity_proven":proven,"compared_sessions":len(rows),"matched_sessions":matched,"mismatch_count":len(rows)-matched,"match_rate":matched/len(rows) if rows else 0,"first_mismatches":m,"scope":"Python state machine evaluated from LEAN-exported identical daily feature inputs."}
    write_json_atomic(out,result);return result
if __name__=="__main__":print(json.dumps(compare(),indent=2))
