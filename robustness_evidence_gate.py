from __future__ import annotations
import json
from pathlib import Path
SRC=Path("research/hybrid_rolling_distribution.json")
EXEC=Path("research/execution_realistic_rolling_distribution.json")
OUT=Path("research/robustness_evidence_gate.json")
def build(src=SRC,out=OUT,exec_src=EXEC):
 d=json.loads(Path(src).read_text());ep=Path(exec_src);exd=json.loads(ep.read_text()) if ep.exists() else {};by={int(x["years"]):x for x in d["rolling"]};exby={int(x["years"]):x for x in exd.get("rolling",[])}
 one,three,five=by[1],by[3],by[5]
 checks={"gross_structural_rolling_source_pass":d.get("status")=="PASS","execution_realistic_rolling_source_pass":exd.get("status")=="PASS","one_year_has_material_loss_risk":one["strategy_cagr_distribution"]["positive_fraction"]<0.90,"one_year_can_materially_lag_qqq":one["vs_qqq"]["excess_cagr_p05"]<0,"three_year_all_sampled_positive":three["strategy_cagr_distribution"]["positive_fraction"]==1.0,"five_year_all_sampled_positive":five["strategy_cagr_distribution"]["positive_fraction"]==1.0,"five_year_all_sampled_beat_qqq":five["vs_qqq"]["beat_fraction"]==1.0}
 status="PASS" if all(checks.values()) else "FAIL"
 x={"schema_version":2,"status":status,"kind":"ROBUSTNESS_EVIDENCE_GATE","promotion_allowed":False,"retuning_authorized":False,"frozen_model_mutated":False,"checks":checks,"evidence_classes":{"gross_structural_rolling":d.get("kind"),"execution_realistic_rolling":exd.get("kind"),"execution_realistic_one_year":exby.get(1)},"observations":{"one_year_positive_fraction":one["strategy_cagr_distribution"]["positive_fraction"],"one_year_beat_qqq_fraction":one["vs_qqq"]["beat_fraction"],"one_year_worst_cagr_window":one["worst_cagr_window"],"one_year_worst_excess_window":one["worst_excess_window"],"three_year_positive_fraction":three["strategy_cagr_distribution"]["positive_fraction"],"three_year_beat_qqq_fraction":three["vs_qqq"]["beat_fraction"],"five_year_positive_fraction":five["strategy_cagr_distribution"]["positive_fraction"],"five_year_beat_qqq_fraction":five["vs_qqq"]["beat_fraction"]},"interpretation":"PASS means evidence classes were retained consistently; it is not an investability or promotion verdict.","claim_boundary":"Gross structural and execution-realistic rolling evidence are separate classes. Neither is a forecast or promotion criterion; adverse short-horizon evidence must remain visible."}
 Path(out).write_text(json.dumps(x,indent=2)+"\n")
 if status!="PASS":raise RuntimeError("ROBUSTNESS_EVIDENCE_GATE_FAILED")
 return x
if __name__=="__main__":print(json.dumps(build(),indent=2))
