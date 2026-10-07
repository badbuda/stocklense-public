from __future__ import annotations
import json
from pathlib import Path

OUT=Path("research/research_decision_gate.json")
SOURCES={
 "volatility_drag":"research/volatility_drag_lmax_megabatch.json",
 "frontier":"research/next_frontier_multidirection_megabatch.json",
 "gap15_final":"research/gap15_final_falsification_megabatch.json",
 "accel_vcap":"research/accel_vcap_independent_redteam.json",
 "two_of_three":"research/two_of_three_timing_attribution_megabatch.json",
}
def _read(p):
 q=Path(p)
 return json.loads(q.read_text()) if q.exists() else None
def build(out=OUT):
 src={k:_read(v) for k,v in SOURCES.items()}
 missing=[k for k,v in src.items() if v is None]
 candidates=[]
 vd=src.get("volatility_drag") or {}
 for name,g in vd.get("continuation_gates",{}).items():
  candidates.append({"family":"volatility_drag","candidate":name,
   "historical_continue":bool(g.get("continue_gate",False)),
   "wealth_ratio":g.get("wealth_ratio_vs_baseline"),"dd_improvement":g.get("maxdd_improvement_vs_baseline"),
   "independent_redteam_required":True})
 fr=src.get("frontier") or {}
 survivors=set(fr.get("broad_survivors",[]))
 for name,c in fr.get("comparison",{}).items():
  stress=fr.get("execution_stress",{}).get(name,{})
  stress_ok=bool(stress) and all((x.get("wealth_ratio",0)>=.80 and x.get("dd_improvement",-1)>=0) for x in stress.values())
  windows=fr.get("nonoverlap_3y",{}).get(name,[])
  gen_ok=bool(windows) and sum(x.get("dd_improvement",0)>0 for x in windows)>=max(1,len(windows)//2)
  candidates.append({"family":"frontier","candidate":name,"historical_continue":name in survivors,
   "wealth_ratio":c.get("wealth_ratio"),"dd_improvement":c.get("dd_improvement"),
   "execution_stress_nonnegative_dd":stress_ok,"window_generalization_support":gen_ok,
   "independent_redteam_required":True})
 result={"schema_version":1,"kind":"RESEARCH_DECISION_GATE","frozen_model":"StockLens 8.0",
  "frozen_model_mutated":False,"promotion_allowed":False,"missing_sources":missing,"candidates":candidates,
  "policy":{"historical_survivor_is_not_winner":True,"requires_independent_redteam":True,
   "requires_execution_stress":True,"requires_lag_robustness":True,"requires_nonoverlap_generalization":True,
   "requires_prospective_evidence_before_capital_claim":True},
  "decision":"NO_AUTOMATIC_PROMOTION",
  "claim_boundary":"This gate ranks evidence completeness only. It cannot promote a challenger, authorize live trading, or claim future drawdown control."}
 Path(out).write_text(json.dumps(result,indent=2)+"\n")
 return result
if __name__=="__main__": print(json.dumps(build(),indent=2))
