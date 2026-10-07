from __future__ import annotations
import json,math
from pathlib import Path
from statistics import median
from hybrid_return_concentration import _series,_metrics
from tqqq_reality_check import _aligned

OUT=Path("research/hybrid_rolling_distribution.json")
SPANS=(252,756,1260)
STEP=21

def _q(xs,p):
    ys=sorted(xs)
    if not ys:return None
    k=(len(ys)-1)*p; lo=int(k); hi=min(lo+1,len(ys)-1); w=k-lo
    return ys[lo]*(1-w)+ys[hi]*w

def build(out=OUT):
    rows,tqqq,_,_=_aligned(); series=_series(rows,tqqq)
    result=[]
    for span in SPANS:
        windows=[]
        for i in range(0,len(series)-span+1,STEP):
            chunk=series[i:i+span]; rs=[x["return"] for x in chunk]
            sm=_metrics(rs,chunk[0]["date"],chunk[-1]["date"])
            qqq=[float(rows[i+j+1]["close"])/float(rows[i+j]["close"])-1.0 for j in range(span)]
            qm=_metrics(qqq,chunk[0]["date"],chunk[-1]["date"])
            windows.append({"start":chunk[0]["date"],"end":chunk[-1]["date"],"strategy_cagr":sm["cagr"],"strategy_max_drawdown":sm["max_drawdown"],"qqq_cagr":qm["cagr"],"cagr_excess_vs_qqq":sm["cagr"]-qm["cagr"]})
        cs=[x["strategy_cagr"] for x in windows]; ex=[x["cagr_excess_vs_qqq"] for x in windows]
        result.append({"years":span//252,"sessions":span,"windows":len(windows),
          "strategy_cagr_distribution":{"min":min(cs),"p05":_q(cs,.05),"median":median(cs),"p95":_q(cs,.95),"max":max(cs),"positive_fraction":sum(x>0 for x in cs)/len(cs)},
          "vs_qqq":{"beat_fraction":sum(x>0 for x in ex)/len(ex),"excess_cagr_p05":_q(ex,.05),"excess_cagr_median":median(ex),"excess_cagr_p95":_q(ex,.95)},
          "worst_cagr_window":min(windows,key=lambda x:x["strategy_cagr"]),
          "worst_excess_window":min(windows,key=lambda x:x["cagr_excess_vs_qqq"])})
    x={"schema_version":1,"status":"PASS","kind":"HYBRID_ROLLING_WINDOW_DISTRIBUTION","promotion_allowed":False,"retuning_authorized":False,"frozen_model_mutated":False,
      "window_policy":{"spans_sessions":list(SPANS),"step_sessions":STEP,"predeclared":True,"selection":"NONE"},
      "claim_boundary":"Descriptive rolling-window falsification, not a forecast. Observed TQQQ is used only at frozen 3x exposure; 1.25x/2x remain QQQ-times-exposure synthetic. Gross returns; no execution costs.",
      "rolling":result}
    Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))
