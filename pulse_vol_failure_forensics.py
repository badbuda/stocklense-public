from __future__ import annotations
import json, random
from pathlib import Path
from statistics import median
from dynamic_overlay_tail_validation import MODES, _daily
from orthogonal_tail_validation import BLOCKS, BOOTSTRAPS, SEED, _block_indices, _path_metrics, _quantiles
from risk_overlay_multifactor import _download
from risk_overlay_deep_dive import _augment
from tqqq_reality_check import _aligned
import pandas as pd

OUT=Path("research/pulse_vol_failure_forensics.json")
MODE="pulse_vol"

def _sample_stats(base,overlay,idx):
    b=[base[i] for i in idx];o=[overlay[i] for i in idx]
    bm=_path_metrics(b);om=_path_metrics(o)
    delta=om["max_drawdown"]-bm["max_drawdown"]
    wr=om["end_equity"]/bm["end_equity"] if bm["end_equity"] else None
    diffs=[o[j]-b[j] for j in range(len(idx))]
    intervention=sum(abs(x)>1e-15 for x in diffs)
    positive_missed=sum(1 for j,x in enumerate(diffs) if abs(x)>1e-15 and b[j]>0 and o[j]<b[j])
    negative_saved=sum(1 for j,x in enumerate(diffs) if abs(x)>1e-15 and b[j]<0 and o[j]>b[j])
    return {"dd_improvement":delta,"wealth_ratio":wr,"intervention_sessions":intervention,
            "positive_sessions_sacrificed":positive_missed,"negative_sessions_cushioned":negative_saved}

def _group(rows):
    if not rows:return {}
    return {"paths":len(rows),
      "dd_improvement_quantiles":_quantiles([x["dd_improvement"] for x in rows]),
      "wealth_ratio_quantiles":_quantiles([x["wealth_ratio"] for x in rows]),
      "median_intervention_sessions":median(x["intervention_sessions"] for x in rows),
      "median_positive_sessions_sacrificed":median(x["positive_sessions_sacrificed"] for x in rows),
      "median_negative_sessions_cushioned":median(x["negative_sessions_cushioned"] for x in rows)}

def build(out=OUT):
    rows,tq,_,_=_aligned();start=rows[0]["date"];end=(pd.Timestamp(rows[-1]["date"])+pd.Timedelta(days=2)).date().isoformat()
    f=_augment(_download(start,end))
    base,_=_daily(rows,tq,f,"baseline");ov,_=_daily(rows,tq,f,MODE)
    blocks={}
    for block in BLOCKS:
        rng=random.Random(SEED+2000+block);vals=[]
        for _ in range(BOOTSTRAPS):
            idx=_block_indices(len(base),block,rng);vals.append(_sample_stats(base,ov,idx))
        improved=[x for x in vals if x["dd_improvement"]>0]
        harmed=[x for x in vals if x["dd_improvement"]<0]
        flat=[x for x in vals if x["dd_improvement"]==0]
        wealth_harmed=[x for x in vals if x["wealth_ratio"]<1]
        blocks[str(block)]={"all":_group(vals),"dd_improved":_group(improved),"dd_harmed":_group(harmed),"dd_flat":_group(flat),
          "wealth_harmed":_group(wealth_harmed),
          "rates":{"dd_improved":len(improved)/len(vals),"dd_harmed":len(harmed)/len(vals),"dd_flat":len(flat)/len(vals),
                   "wealth_harmed":len(wealth_harmed)/len(vals)}}
    result={"schema_version":1,"kind":"PULSE_VOL_FAILURE_FORENSICS_RESEARCH_ONLY","mode":MODE,
      "frozen_model":"StockLens 8.0","frozen_model_mutated":False,"promotion_allowed":False,
      "paired_blocks":blocks,
      "diagnostic_contract":"No threshold changes. Classifies identical-index bootstrap paths by realized overlay outcome and counts sacrificed positive vs cushioned negative intervention sessions.",
      "claim_boundary":"Mechanism diagnosis only. Group differences are descriptive and cannot be used as a new trading rule without separately predeclared validation."}
    Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))
