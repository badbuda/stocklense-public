from __future__ import annotations
import json
from pathlib import Path
from statistics import median
from datetime import date
from leveraged_instrument_reality_check import _load
from tqqq_reality_check import _aligned
from hybrid_rolling_distribution import _q
OUT=Path("research/execution_realistic_rolling_distribution.json")
SPANS=(252,756,1260);STEP=21;COST_BPS=5;FINANCING_RATE=0.06;BORROWED_FRACTION=0.25
def _path(rows,tqqq,qld):
 nav=peak=1.0;prev=0.0;out=[]
 for i in range(1,len(rows)):
  exp=float(rows[i-1]["leverage"]);d0=rows[i-1]["date"];d1=rows[i]["date"];q=float(rows[i]["close"])/float(rows[i-1]["close"])-1
  if exp==3.0 and d0 in tqqq and d1 in tqqq:r=tqqq[d1]/tqqq[d0]-1;source="TQQQ"
  elif exp==2.0 and d0 in qld and d1 in qld:r=qld[d1]/qld[d0]-1;source="QLD"
  else:r=q*exp;source="QQQ_1_25_SYNTHETIC" if exp==1.25 else "QQQ_SYNTHETIC"
  nav*=1+r
  if exp==1.25:nav-=nav*BORROWED_FRACTION*FINANCING_RATE/252
  nav-=nav*abs(exp-prev)*COST_BPS/10000
  peak=max(peak,nav);out.append({"date":d1,"nav":nav,"source":source});prev=exp
 return out
def _window(path,rows,start,span):
 chunk=path[start:start+span];base=path[start-1]["nav"] if start else 1.0;growth=chunk[-1]["nav"]/base
 years=(date.fromisoformat(chunk[-1]["date"])-date.fromisoformat(rows[start]["date"])).days/365.2425
 cagr=growth**(1/years)-1;pk=base;dd=0
 for x in chunk:pk=max(pk,x["nav"]);dd=min(dd,x["nav"]/pk-1)
 q0=float(rows[start]["close"]);q1=float(rows[start+span]["close"]);qc=(q1/q0)**(1/years)-1
 return {"start":rows[start]["date"],"end":chunk[-1]["date"],"strategy_cagr":cagr,"strategy_max_drawdown":dd,"qqq_cagr":qc,"cagr_excess_vs_qqq":cagr-qc}
def build(out=OUT):
 rows,tqqq,_,_=_aligned();qld=_load("QLD","2006-06-21");path=_path(rows,tqqq,qld);rolling=[]
 for span in SPANS:
  ws=[_window(path,rows,i,span) for i in range(0,len(path)-span+1,STEP)];cs=[x["strategy_cagr"] for x in ws];ex=[x["cagr_excess_vs_qqq"] for x in ws]
  rolling.append({"years":span//252,"sessions":span,"windows":len(ws),"strategy_cagr_distribution":{"min":min(cs),"p05":_q(cs,.05),"median":median(cs),"p95":_q(cs,.95),"max":max(cs),"positive_fraction":sum(x>0 for x in cs)/len(cs)},"vs_qqq":{"beat_fraction":sum(x>0 for x in ex)/len(ex),"excess_cagr_p05":_q(ex,.05),"excess_cagr_median":median(ex),"excess_cagr_p95":_q(ex,.95)},"worst_cagr_window":min(ws,key=lambda x:x["strategy_cagr"]),"worst_excess_window":min(ws,key=lambda x:x["cagr_excess_vs_qqq"])})
 x={"schema_version":1,"status":"PASS","kind":"EXECUTION_REALISTIC_ROLLING_WINDOW_DISTRIBUTION","promotion_allowed":False,"retuning_authorized":False,"frozen_model_mutated":False,"assumptions":{"turnover_cost_bps":COST_BPS,"annual_financing_rate_1_25x":FINANCING_RATE,"borrowed_fraction_1_25x":BORROWED_FRACTION,"3x":"actual adjusted TQQQ","2x":"actual adjusted QLD","1.25x":"QQQ times 1.25 with explicit financing"},"window_policy":{"spans_sessions":list(SPANS),"step_sessions":STEP,"selection":"NONE","predeclared":True},"rolling":rolling,"selection":"NONE","claim_boundary":"Execution-realism diagnostic, not a forecast. TQQQ/QLD adjusted prices embed fund drag; 1.25x remains synthetic underlying with explicit fixed financing. Taxes, spread, intraday fills and borrow availability remain outside."}
 Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))
