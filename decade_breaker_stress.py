from __future__ import annotations
import json
from pathlib import Path
from execution_realistic_rolling_stress_grid import _path
from execution_realistic_rolling_distribution import _window
from leveraged_instrument_reality_check import _load
from tqqq_reality_check import _aligned
OUT=Path("research/decade_breaker_stress.json")
COSTS=(100,150,200);FINANCING=(0.10,0.15,0.20);SPAN=2520;STEP=21
def _delay_rows(rows,delay):
 if delay==0:return rows
 x=[]
 for i,r in enumerate(rows):
  z=dict(r);z["leverage"]=rows[max(0,i-delay)]["leverage"];x.append(z)
 return x
def build(out=OUT):
 rows,tqqq,_,_=_aligned();qld=_load("QLD","2006-06-21");cases=[]
 for delay in (0,1,2,5):
  rr=_delay_rows(rows,delay)
  for cost in COSTS:
   for fin in FINANCING:
    p=_path(rr,tqqq,qld,cost,fin);ws=[_window(p,rr,i,SPAN) for i in range(0,len(p)-SPAN+1,STEP)]
    cases.append({"delay_sessions":delay,"cost_bps":cost,"financing_rate":fin,"windows":len(ws),"positive_fraction":sum(x["strategy_cagr"]>0 for x in ws)/len(ws),"beat_qqq_fraction":sum(x["cagr_excess_vs_qqq"]>0 for x in ws)/len(ws),"min_cagr":min(x["strategy_cagr"] for x in ws),"min_excess_cagr":min(x["cagr_excess_vs_qqq"] for x in ws),"worst_max_drawdown":min(x["strategy_max_drawdown"] for x in ws)})
 x={"schema_version":1,"status":"PASS","kind":"DECADE_BREAKER_STRESS","scenario_count":len(cases),"grid":{"decision_delay_sessions":[0,1,2,5],"cost_bps":list(COSTS),"annual_financing_rate":list(FINANCING),"span_sessions":SPAN,"step_sessions":STEP,"selection":"NONE_PREDECLARED_ADVERSE_GRID"},"cases":cases,"worst":{"positive_fraction":min(x["positive_fraction"] for x in cases),"beat_qqq_fraction":min(x["beat_qqq_fraction"] for x in cases),"min_cagr":min(x["min_cagr"] for x in cases),"min_excess_cagr":min(x["min_excess_cagr"] for x in cases),"worst_max_drawdown":min(x["worst_max_drawdown"] for x in cases)},"promotion_allowed":False,"retuning_authorized":False,"frozen_model_mutated":False,"claim_boundary":"Deliberately adverse historical execution stress, not a probability model or forecast. Delays are applied to frozen exposure decisions without retuning."}
 Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))
