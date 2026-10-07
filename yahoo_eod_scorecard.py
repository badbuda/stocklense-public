from __future__ import annotations
import json
from pathlib import Path
SRC=Path("research/yahoo_long_history.json"); OUT=Path("research/yahoo_end_of_day_scorecard.json")
def build(src=SRC,out=OUT):
    r=json.loads(Path(src).read_text()); pure=r["strategy_no_contributions"]; qqq=r["qqq_buy_hold_no_contributions"]
    sc={"schema_version":1,"status":r["research_verdict"]["status"],"evidence_class":r["kind"],"research_verdict":r["research_verdict"],
      "period":{"start":r["start"],"end":r["end"],"sessions":r["sessions"]},"source_audit":r["source_audit"],
      "canonical":{"strategy_cagr":pure["cagr"],"qqq_cagr":qqq["cagr"],"excess_cagr":r["comparison"]["strategy_minus_qqq_cagr"],
        "strategy_max_drawdown":pure["max_drawdown"],"qqq_max_drawdown":qqq["max_drawdown"],
        "strategy_end_equity":pure["end_equity"],"qqq_end_equity":qqq["end_equity"],"ending_equity_ratio":r["comparison"]["strategy_to_qqq_ending_equity_ratio"]},
      "monthly_3500":{"strategy_end_equity":r["strategy_with_monthly_3500"]["end_equity"],"qqq_end_equity":r["qqq_with_monthly_3500"]["end_equity"],
        "paid_capital":r["strategy_with_monthly_3500"]["paid_capital"],"matched_cost_assumption":r["contribution_comparison"]["matched_cost_assumption"],"strategy_minus_qqq":r["contribution_comparison"]["strategy_minus_qqq_end_equity"]},
      "robustness":{"annual":r["annual_summary"],"rolling":r["rolling_windows"],"cost_stress":r["cost_stress"],"downside_windows":r["downside_windows"],"underwater":r["underwater"],"drawdown_profile":r["drawdown_profile"]},"canonical_lean_cagr_unlocked":False,"canonical_lean_cagr_status":"BLOCKED_PENDING_FULL_SAME_RUN_LEAN_EXPORT",
      "exposure":r["exposure_mix"],"retroactive_extension":r["retroactive_extension"],"retroactive_subperiods":r["retroactive_subperiods"],"retroactive_coverage":r["retroactive_coverage"],"claim_boundary":r["claim_boundary"],"instrument_semantics":r["instrument_semantics"]}
    Path(out).parent.mkdir(parents=True,exist_ok=True);Path(out).write_text(json.dumps(sc,indent=2)+"\n");return sc
if __name__=="__main__": print(json.dumps(build(),indent=2))
