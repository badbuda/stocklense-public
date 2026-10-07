from __future__ import annotations
import json,math
from datetime import date
from pathlib import Path
from stocklens.data import load_qqq_history,load_tqqq_history
from stocklens.core import compute_features,defense_active,LEVEL_LEVERAGE,TRADING_START
from yahoo_long_history import _rows
from hybrid_return_concentration import _metrics

OUT=Path("research/frozen8_sensitivity.json")
BASE={"retain":0.99,"reentry":1.01,"up":0.28,"l3drop":0.32,"l1mid":0.38,"l2drop":0.42}

def _next(f,prev,p):
    prev=prev if prev is not None else 1
    trend=f.close>=f.sma200*p["retain"] if prev>1 else f.close>f.sma200*p["reentry"]
    if not trend:return 1
    if prev==3:return 2 if f.vol20>=p["l3drop"] else 3
    if prev==2:
        if f.vol20<p["up"]:return 3
        if f.vol20>=p["l2drop"]:return 1
        return 2
    if f.vol20<p["up"]:return 3
    if f.vol20<p["l1mid"]:return 2
    return 1

def _variant_rows(df,p):
    dates=df["Date"].dt.date.astype(str).tolist(); closes=df["Close"].astype(float).tolist()
    start=next(i for i,d in enumerate(dates) if date.fromisoformat(d)>=TRADING_START)
    level=None;out=[];prev=None
    for i in range(start,len(closes)):
        f=compute_features(closes[:i+1]);level=_next(f,level,p);defn=defense_active(f);lev=0.0 if defn else float(LEVEL_LEVERAGE[level])
        out.append({"date":dates[i],"close":closes[i],"leverage":lev,"level":level,"defense":defn,"event":prev is not None and lev!=prev})
        prev=lev
    return out

def _hybrid(rows,tqqq):
    s=[]
    for i in range(1,len(rows)):
        exp=float(rows[i-1]["leverage"]);q=float(rows[i]["close"])/float(rows[i-1]["close"])-1
        r=tqqq[rows[i]["date"]]/tqqq[rows[i-1]["date"]]-1 if exp==3.0 else q*exp
        s.append(r)
    return _metrics(s,rows[0]["date"],rows[-1]["date"])

def build(out=OUT):
    qdf,_=load_qqq_history();tdf,_=load_tqqq_history(); t={d.date().isoformat():float(c) for d,c in zip(tdf["Date"],tdf["Close"])}
    frozen,_=_rows(qdf,None); baseline=_variant_rows(qdf,BASE)
    parity=len(frozen)==len(baseline) and all((a["date"],float(a["leverage"]),int(a["level"]),bool(a["defense"]))==(b["date"],float(b["leverage"]),int(b["level"]),bool(b["defense"])) for a,b in zip(frozen,baseline))
    if not parity:raise RuntimeError("SENSITIVITY_BASELINE_NOT_EXACT_FROZEN_8")
    overlap=lambda rs:[r for r in rs if r["date"] in t and r["date"]>="2010-02-09"]
    base_rows=overlap(baseline); bm=_hybrid(base_rows,t)
    variants=[]
    specs=[
      ("trend_tighter",{"retain":1.00,"reentry":1.02}),("trend_looser",{"retain":0.98,"reentry":1.00}),
      ("vol_all_minus_2pp",{"up":0.26,"l3drop":0.30,"l1mid":0.36,"l2drop":0.40}),
      ("vol_all_plus_2pp",{"up":0.30,"l3drop":0.34,"l1mid":0.40,"l2drop":0.44}),
      ("l3drop_minus_2pp",{"l3drop":0.30}),("l3drop_plus_2pp",{"l3drop":0.34}),
      ("upshift_minus_2pp",{"up":0.26}),("upshift_plus_2pp",{"up":0.30})]
    for name,delta in specs:
        p={**BASE,**delta};rs=overlap(_variant_rows(qdf,p));m=_hybrid(rs,t)
        variants.append({"name":name,"parameters":p,**m,"cagr_delta_vs_frozen":m["cagr"]-bm["cagr"],"dd_delta_vs_frozen":m["max_drawdown"]-bm["max_drawdown"]})
    starts=[]
    for y in (2011,2012,2013,2014,2015,2016,2017,2018,2019,2020):
        rs=[r for r in base_rows if r["date"]>=f"{y}-01-01"]
        if len(rs)>252:starts.append({"start_year":y,"sessions":len(rs),**_hybrid(rs,t)})
    x={"schema_version":1,"status":"PASS","kind":"FROZEN_8_NON_OPTIMIZING_SENSITIVITY","promotion_allowed":False,"retuning_authorized":False,"frozen_model_mutated":False,
       "baseline_exact_frozen_parity":parity,"claim_boundary":"Falsification only. Fixed local perturbations are not searched, ranked, selected, or authorized for model changes. Hybrid uses observed TQQQ only at 3x; other exposures remain synthetic.",
       "baseline_parameters":BASE,"baseline_hybrid_gross":bm,"parameter_neighborhood":variants,"start_date_sensitivity":starts}
    Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))
