from __future__ import annotations
import json
from pathlib import Path
from publication_identity import identity

def classify(row):
    close=float(row["close"]);s50=float(row["sma50"]);s200=float(row["sma200"]);vol=float(row["vol20"])
    trend="BULL" if close>s50>s200 else "BEAR" if close<s50<s200 else "MIXED"
    vol_bucket="HIGH_VOL" if vol>=0.25 else "MID_VOL" if vol>=0.15 else "LOW_VOL"
    return trend+"_"+vol_bucket

def build(workbench="docs/workbench.json",out="docs/backtest_regimes.json"):
    w=json.loads(Path(workbench).read_text());rows=w.get("replay",{}).get("rows") or []
    if len(rows)<20:raise RuntimeError("REGIME_REPLAY_MISSING")
    buckets={}
    for i in range(1,len(rows)):
        p,c=rows[i-1],rows[i];k=classify(p);q=float(c["close"])/float(p["close"])-1;sr=q*float(p["leverage"])
        z=buckets.setdefault(k,{"sessions":0,"strategy_gross_sum":0.0,"qqq_sum":0.0,"positive_strategy_sessions":0})
        z["sessions"]+=1;z["strategy_gross_sum"]+=sr;z["qqq_sum"]+=q;z["positive_strategy_sessions"]+=int(sr>0)
    for z in buckets.values():z["positive_strategy_session_share"]=z["positive_strategy_sessions"]/z["sessions"] if z["sessions"] else None
    x={"schema_version":1,"publication_identity":identity(),"status":"PASS","regime_definition":{"trend":"BULL close>SMA50>SMA200; BEAR close<SMA50<SMA200; otherwise MIXED","volatility":"Diagnostic buckets: LOW <15%; MID 15%-25%; HIGH >=25% using VOL20. These 15%/25% cutoffs are fixed reporting bins, NOT StockLens 8.0 decision thresholds."},"regimes":buckets,"semantics":"Descriptive predeclared mechanical regime decomposition of gross replay returns. The volatility bins are reporting thresholds only, not frozen-model thresholds. Sums are diagnostics, not compounded CAGR or alpha.","retuning_authorized":False,"automatic_promotion":False}
    Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))
