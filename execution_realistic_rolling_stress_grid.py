from __future__ import annotations
import json
from pathlib import Path
from execution_realistic_rolling_distribution import SPANS,STEP,BORROWED_FRACTION,_window
from leveraged_instrument_reality_check import _load
from tqqq_reality_check import _aligned
OUT=Path("research/execution_realistic_rolling_stress_grid.json")
COST_BPS_GRID=(5,25,50,100);FINANCING_GRID=(0.0,0.06,0.10)
def _path(rows,tqqq,qld,cost_bps,financing_rate):
 nav=1.0;prev=0.0;out=[]
 for i in range(1,len(rows)):
  exp=float(rows[i-1]["leverage"]);d0=rows[i-1]["date"];d1=rows[i]["date"];q=float(rows[i]["close"])/float(rows[i-1]["close"])-1
  if exp==3.0 and d0 in tqqq and d1 in tqqq:r=tqqq[d1]/tqqq[d0]-1
  elif exp==2.0 and d0 in qld and d1 in qld:r=qld[d1]/qld[d0]-1
  else:r=q*exp
  nav*=1+r
  if exp==1.25:nav-=nav*BORROWED_FRACTION*financing_rate/252
  nav-=nav*abs(exp-prev)*cost_bps/10000
  out.append({"date":d1,"nav":nav});prev=exp
 return out
def build(out=OUT):
 rows,tqqq,_,_=_aligned();qld=_load("QLD","2006-06-21");scenarios=[]
 for cost in COST_BPS_GRID:
  for fin in FINANCING_GRID:
   path=_path(rows,tqqq,qld,cost,fin);wins=[]
   for span in SPANS:
    ws=[_window(path,rows,i,span) for i in range(0,len(path)-span+1,STEP)]
    wins.append({"years":span//252,"windows":len(ws),"positive_fraction":sum(x["strategy_cagr"]>0 for x in ws)/len(ws),"beat_qqq_fraction":sum(x["cagr_excess_vs_qqq"]>0 for x in ws)/len(ws),"min_cagr":min(x["strategy_cagr"] for x in ws),"min_excess_cagr":min(x["cagr_excess_vs_qqq"] for x in ws),"worst_max_drawdown":min(x["strategy_max_drawdown"] for x in ws)})
   scenarios.append({"turnover_cost_bps":cost,"annual_financing_rate":fin,"windows":wins})
 def yr(s,y):return next(x for x in s["windows"] if x["years"]==y)
 worst={}
 for y in (1,3,5):
  worst[str(y)]={"min_positive_fraction":min(yr(s,y)["positive_fraction"] for s in scenarios),"min_beat_qqq_fraction":min(yr(s,y)["beat_qqq_fraction"] for s in scenarios),"worst_min_cagr":min(yr(s,y)["min_cagr"] for s in scenarios),"worst_min_excess_cagr":min(yr(s,y)["min_excess_cagr"] for s in scenarios),"worst_max_drawdown":min(yr(s,y)["worst_max_drawdown"] for s in scenarios)}
 x={"schema_version":1,"status":"PASS","kind":"EXECUTION_REALISTIC_ROLLING_STRESS_GRID","grid":{"turnover_cost_bps":list(COST_BPS_GRID),"annual_financing_rates":list(FINANCING_GRID),"borrowed_fraction_1_25x":BORROWED_FRACTION,"window_spans_sessions":list(SPANS),"step_sessions":STEP,"selection":"NONE_PREDECLARED_GRID"},"scenario_count":len(scenarios),"scenarios":scenarios,"worst_across_grid":worst,"promotion_allowed":False,"retuning_authorized":False,"frozen_model_mutated":False,"claim_boundary":"Sensitivity grid over fixed execution assumptions, not a forecast. Actual adjusted TQQQ/QLD are used at exact 3x/2x states; 1.25x remains QQQ-based with explicit financing. Taxes, spread, intraday fills and borrow availability remain outside."}
 Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))
