from __future__ import annotations
import json
from pathlib import Path
SRC=Path("research/decade_breaker_stress.json");OUT=Path("research/decade_claim_boundary.json")
def build(src=SRC,out=OUT):
 d=json.loads(Path(src).read_text());w=d["worst"]
 positive=w["positive_fraction"]==1.0
 beats=w["beat_qqq_fraction"]==1.0
 x={"schema_version":1,"status":"PASS","kind":"DECADE_CLAIM_BOUNDARY","historical_observation":{"all_tested_decade_windows_positive_across_adverse_grid":positive,"all_tested_decade_windows_beat_qqq_across_adverse_grid":beats,"worst_min_cagr":w["min_cagr"],"worst_beat_qqq_fraction":w["beat_qqq_fraction"],"worst_min_excess_cagr":w["min_excess_cagr"],"worst_max_drawdown":w["worst_max_drawdown"],"scenario_count":d["scenario_count"]},"allowed_claims":["All tested historical 10-year windows remained positive across the predeclared adverse execution grid."] if positive else [],"forbidden_claims":["A 10-year holding period is safe or guaranteed.","StockLens is guaranteed to beat QQQ over 10 years.","Historical 100% positivity is a probability estimate for future 10-year outcomes.","The tested windows establish capital preservation."],"outperformance_guarantee_supported":False,"safety_guarantee_supported":False,"promotion_allowed":False,"retuning_authorized":False,"frozen_model_mutated":False,"interpretation":"Historical decade positivity is retained as an observation only. Outperformance is explicitly not universal under adverse execution stress, and neither positivity nor outperformance may be converted into a future guarantee."}
 Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))
