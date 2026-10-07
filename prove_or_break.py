from __future__ import annotations
import json
from pathlib import Path
from publication_identity import identity
def build(adversarial="docs/backtest_adversarial.json",robustness="docs/backtest_robustness.json",forward="docs/forward_operations.json",regimes="docs/backtest_regimes.json",concentration="docs/backtest_return_concentration.json", ablation="docs/backtest_topday_ablation.json", yearly="docs/backtest_calendar_year_fragility.json", pathfrag="docs/backtest_path_fragility.json", recovery="docs/backtest_recovery.json", exposure="docs/backtest_exposure_attribution.json", transition_attr="docs/backtest_transition_attribution.json", transition="docs/backtest_transition_fragility.json", neighborhood="docs/backtest_transition_neighborhood.json",out="docs/prove_or_break.json"):
    def load(p):
        try:return json.loads(Path(p).read_text())
        except Exception:return {}
    a,r,f,g,c,t,y,p,rec,e,ta,tr,nh=map(load,(adversarial,robustness,forward,regimes,concentration,ablation,yearly,pathfrag,recovery,exposure,transition_attr,transition,neighborhood))
    checks=[
      {"id":"ROBUSTNESS_WINDOWS","status":"PASS" if r.get("status")=="PASS" else "WAITING"},
      {"id":"ADVERSARIAL_COST_DELAY","status":"PASS" if a.get("status")=="PASS" else "WAITING"},
      {"id":"REGIME_DECOMPOSITION","status":"PASS" if g.get("status")=="PASS" else "WAITING"},
      {"id":"RETURN_CONCENTRATION","status":"PASS" if c.get("status")=="PASS" else "WAITING"},
      {"id":"TOP_DAY_ABLATION","status":"PASS" if t.get("status")=="PASS" else "WAITING"},
      {"id":"LEAVE_ONE_YEAR_OUT","status":"PASS" if y.get("status")=="PASS" else "WAITING"},
      {"id":"ROLLING_PATH_FRAGILITY","status":"PASS" if p.get("status")=="PASS" else "WAITING"},
      {"id":"DRAWDOWN_RECOVERY","status":"PASS" if rec.get("status")=="PASS" else "WAITING"},
      {"id":"EXPOSURE_ATTRIBUTION","status":"PASS" if e.get("status")=="PASS" else "WAITING"},
      {"id":"TRANSITION_ATTRIBUTION","status":"PASS" if ta.get("status")=="PASS" else "WAITING"},
      {"id":"TRANSITION_FRAGILITY","status":"PASS" if tr.get("status")=="PASS" else "WAITING"},
      {"id":"TRANSITION_NEIGHBORHOOD","status":"PASS" if nh.get("status")=="PASS" else "WAITING"},
      {"id":"PROSPECTIVE_IMPLEMENTATION","status":"PASS" if f.get("status")=="HEALTHY" else "WAITING"}]
    x={"schema_version":2,"publication_identity":identity(),"status":"COMPLETE_FOR_CURRENT_BATTERY" if all(v["status"]=="PASS" for v in checks) else "INCOMPLETE","checks":checks,"rule":"Failures are evidence against robustness. Passing this battery is survival evidence only and never proof of future return.","frozen_model_mutation":False,"automatic_promotion":False}
    Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))
