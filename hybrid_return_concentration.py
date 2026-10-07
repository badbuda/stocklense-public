from __future__ import annotations
import json,math
from collections import defaultdict
from datetime import date
from pathlib import Path
from tqqq_reality_check import _aligned,_delay_rows

OUT=Path("research/hybrid_return_concentration.json")

def _series(rows,tqqq,delay=0):
    ex=_delay_rows(rows,delay); out=[]
    for i in range(1,len(rows)):
        exp=float(ex[i-1]["leverage"])
        q=float(rows[i]["close"])/float(rows[i-1]["close"])-1.0
        r=tqqq[rows[i]["date"]]/tqqq[rows[i-1]["date"]]-1.0 if exp==3.0 else q*exp
        out.append({"date":rows[i]["date"],"year":rows[i]["date"][:4],"return":r,"exposure":exp})
    return out

def _metrics(xs,start,end):
    nav=peak=1.0; dd=0.0
    for r in xs:
        nav*=1+r; peak=max(peak,nav); dd=min(dd,nav/peak-1)
    years=(date.fromisoformat(end)-date.fromisoformat(start)).days/365.2425
    return {"growth_multiple":nav,"cagr":nav**(1/years)-1 if years>0 and nav>0 else None,"max_drawdown":dd}

def build(out=OUT):
    rows,tqqq,_,_=_aligned(); s=_series(rows,tqqq); rets=[x["return"] for x in s]
    base=_metrics(rets,rows[0]["date"],rows[-1]["date"])
    ranked=sorted(range(len(s)),key=lambda i:s[i]["return"],reverse=True)
    top_days=[]
    for n in (1,5,10,20,50):
        cut=set(ranked[:n]); m=_metrics([r if i not in cut else 0.0 for i,r in enumerate(rets)],rows[0]["date"],rows[-1]["date"])
        top_days.append({"removed_best_sessions":n,**m,"removed_dates":[s[i]["date"] for i in ranked[:min(n,10)]]})
    by=defaultdict(list)
    for x in s:by[x["year"]].append(x["return"])
    annual=[{"year":y,**_metrics(v,y+"-01-01",y+"-12-31")} for y,v in sorted(by.items())]
    best_years=sorted(annual,key=lambda x:x["growth_multiple"],reverse=True)
    year_ablation=[]
    for n in (1,2,3,5):
        removed={x["year"] for x in best_years[:n]}
        kept=[x["return"] for x in s if x["year"] not in removed]
        year_ablation.append({"removed_best_years":n,"years":sorted(removed),**_metrics(kept,rows[0]["date"],rows[-1]["date"])})
    rolling=[]
    for yrs in (1,3,5):
        span=252*yrs; vals=[]
        for i in range(0,len(s)-span+1,21):
            chunk=s[i:i+span]; m=_metrics([x["return"] for x in chunk],chunk[0]["date"],chunk[-1]["date"])
            vals.append({"start":chunk[0]["date"],"end":chunk[-1]["date"],**m})
        worst=min(vals,key=lambda x:x["cagr"]) if vals else None
        rolling.append({"years":yrs,"windows":len(vals),"worst":worst})
    result={"schema_version":1,"status":"PASS","kind":"HYBRID_OBSERVED_TQQQ_RETURN_CONCENTRATION","promotion_allowed":False,"frozen_model_mutated":False,
      "claim_boundary":"Observed TQQQ returns are used only when frozen execution exposure is 3x; 1.25x/2x remain QQQ-times-exposure synthetic. No costs are applied here so this isolates return concentration, not executable net performance.",
      "period":{"start":rows[0]["date"],"end":rows[-1]["date"],"sessions":len(rows)},"baseline_gross":base,
      "best_session_ablation":top_days,"calendar_years":annual,"best_year_ablation":year_ablation,"rolling_worst_windows":rolling}
    Path(out).write_text(json.dumps(result,indent=2)+"\n"); return result
if __name__=="__main__":print(json.dumps(build(),indent=2))
