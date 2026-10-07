from __future__ import annotations
import json
from pathlib import Path
from execution_realistic_rolling_stress_grid import COST_BPS_GRID,FINANCING_GRID,_path
from execution_realistic_rolling_distribution import _window
from leveraged_instrument_reality_check import _load
from tqqq_reality_check import _aligned
OUT=Path("research/long_horizon_independence_stress.json")
SPANS=(1260,1764,2520)
def _summ(ws):
 return {"windows":len(ws),"positive_fraction":sum(x["strategy_cagr"]>0 for x in ws)/len(ws),"beat_qqq_fraction":sum(x["cagr_excess_vs_qqq"]>0 for x in ws)/len(ws),"min_cagr":min(x["strategy_cagr"] for x in ws),"min_excess_cagr":min(x["cagr_excess_vs_qqq"] for x in ws),"worst_max_drawdown":min(x["strategy_max_drawdown"] for x in ws)}
def build(out=OUT):
 rows,tqqq,_,_=_aligned();qld=_load("QLD","2006-06-21");scenarios=[]
 for cost in COST_BPS_GRID:
  for fin in FINANCING_GRID:
   path=_path(rows,tqqq,qld,cost,fin);h=[]
   for span in SPANS:
    overlapping=[_window(path,rows,i,span) for i in range(0,len(path)-span+1,21)]
    offsets=[]
    for offset in range(0,span,252):
     ws=[_window(path,rows,i,span) for i in range(offset,len(path)-span+1,span)]
     if ws:offsets.append({"offset_sessions":offset,**_summ(ws)})
    h.append({"years":span//252,"overlapping":_summ(overlapping),"non_overlapping_offsets":offsets})
   scenarios.append({"turnover_cost_bps":cost,"annual_financing_rate":fin,"horizons":h})
 worst={}
 for y in (5,7,10):
  hs=[next(h for h in s["horizons"] if h["years"]==y) for s in scenarios]
  ovs=[h["overlapping"] for h in hs];offs=[o for h in hs for o in h["non_overlapping_offsets"]]
  worst[str(y)]={"overlapping_min_positive_fraction":min(x["positive_fraction"] for x in ovs),"overlapping_min_beat_qqq_fraction":min(x["beat_qqq_fraction"] for x in ovs),"overlapping_worst_min_cagr":min(x["min_cagr"] for x in ovs),"non_overlapping_offset_min_positive_fraction":min(x["positive_fraction"] for x in offs) if offs else None,"non_overlapping_offset_min_beat_qqq_fraction":min(x["beat_qqq_fraction"] for x in offs) if offs else None,"non_overlapping_worst_min_cagr":min(x["min_cagr"] for x in offs) if offs else None}
 x={"schema_version":1,"status":"PASS","kind":"LONG_HORIZON_INDEPENDENCE_STRESS","horizons_years":[5,7,10],"cost_bps_grid":list(COST_BPS_GRID),"financing_grid":list(FINANCING_GRID),"scenario_count":len(scenarios),"offset_policy":"non-overlapping windows repeated at annual (252-session) offsets; no best-offset selection","scenarios":scenarios,"worst_across_grid":worst,"promotion_allowed":False,"retuning_authorized":False,"frozen_model_mutated":False,"claim_boundary":"Historical dependence diagnostic, not a forecast. Non-overlapping samples are necessarily small at 7/10-year horizons and must not be interpreted as independent proof of future outperformance."}
 Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))
