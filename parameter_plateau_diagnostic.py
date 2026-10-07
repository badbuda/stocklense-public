from __future__ import annotations
import json,math
from pathlib import Path
SRC=Path("research/frozen8_sensitivity.json"); COST=Path("research/frozen8_parameter_start_sensitivity.json")
OUT=Path("research/parameter_plateau_diagnostic.json")
CLIFF_CAGR_DELTA=0.10
WIDE_SPREAD=0.15

def build(src=SRC,cost=COST,out=OUT):
 a=json.loads(Path(src).read_text());b=json.loads(Path(cost).read_text())
 if not a.get("baseline_exact_frozen_parity"):raise RuntimeError("PARAMETER_DIAGNOSTIC_REQUIRES_EXACT_FROZEN_PARITY")
 neigh=a["parameter_neighborhood"]; deltas=[float(x["cagr_delta_vs_frozen"]) for x in neigh]
 absmax=max(abs(x) for x in deltas); spread=max(float(x["cagr"]) for x in neigh)-min(float(x["cagr"]) for x in neigh)
 local_cliff=absmax>=CLIFF_CAGR_DELTA or spread>=WIDE_SPREAD
 starts=a["start_date_sensitivity"]; sc=[float(x["cagr"]) for x in starts]
 costvars=b["parameter_variants"]; cc=[float(x["cagr"]) for x in costvars]
 result={"schema_version":1,"status":"PASS","kind":"FROZEN8_PARAMETER_PLATEAU_DIAGNOSTIC",
  "promotion_allowed":False,"retuning_authorized":False,"frozen_model_mutated":False,
  "thresholds_predeclared":{"local_cliff_abs_cagr_delta":CLIFF_CAGR_DELTA,"wide_local_cagr_spread":WIDE_SPREAD},
  "classification":"LOCAL_CLIFF_DETECTED" if local_cliff else "LOCAL_PLATEAU_NO_10PP_CLIFF_DETECTED",
  "local":{"max_abs_cagr_delta":absmax,"neighbor_cagr_spread":spread,
    "worst_neighbor":min(neigh,key=lambda x:float(x["cagr"]))["name"],
    "best_neighbor":max(neigh,key=lambda x:float(x["cagr"]))["name"]},
  "start_date":{"count":len(sc),"min_cagr":min(sc),"max_cagr":max(sc),"spread":max(sc)-min(sc),
    "all_positive":all(x>0 for x in sc)},
  "cost_aware_predeclared_grid":{"count":len(cc),"min_cagr":min(cc),"max_cagr":max(cc),"spread":max(cc)-min(cc)},
  "interpretation":"PASS means the diagnostic was computed and retained, not that parameters are robust. Read classification explicitly; LOCAL_CLIFF_DETECTED is adverse evidence and must not be hidden.",
  "claim_boundary":"Thresholds classify local sensitivity only and are not optimization targets, promotion criteria, forecasts, or permission to retune Frozen 8.0."}
 if not all(math.isfinite(x) for x in deltas+sc+cc):raise RuntimeError("NONFINITE_PARAMETER_DIAGNOSTIC")
 Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))
