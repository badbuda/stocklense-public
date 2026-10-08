from __future__ import annotations
import json
from pathlib import Path
SHOCKS=(-.05,-.10,-.20,-.30)
def build_stress(signal_path="shadow_history/latest.json",out="shadow_history/stress_scenarios.json"):
    s=json.loads(Path(signal_path).read_text());x=s["latest"];lev=float(x["target_leverage"]);invest=float(x.get("invested_fraction",.985))
    scenarios=[]
    for q in SHOCKS:
        linear=invest*lev*q
        scenarios.append({"qqq_shock":q,"linearized_portfolio_impact":linear,"ending_value_per_100":100*(1+linear)})
    r={"mode":"ILLUSTRATIVE_LINEAR_STRESS_NOT_FORECAST","level":x["level"],"target_leverage":lev,"invested_fraction":invest,"scenarios":scenarios,"limitations":["TQQQ path dependence, compounding, volatility drag, gaps, fees and tracking error make realized outcomes differ.","Does not change the frozen signal."]}
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build_stress(),indent=2))
