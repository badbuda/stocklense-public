from __future__ import annotations
import json, random
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from risk_overlay_multifactor import _download
from risk_overlay_deep_dive import _augment
from orthogonal_tail_validation import BLOCKS, BOOTSTRAPS, SEED, _block_indices, _path_metrics, _quantiles

OUT=Path("research/dynamic_overlay_tail_validation.json")
# Fixed subset of already-declared mechanisms. No new thresholds and no outcome-driven selection.
MODES=("baseline","term_severe_pulse5_cap2","realized_vol30_cap2","dd_budget","pulse_vol")

def _cap(mode, frozen, f, dt):
    if mode=="baseline" or dt not in f.index:return frozen
    rv=float(f.at[dt,"rv20"]) if pd.notna(f.at[dt,"rv20"]) else 0.0
    qdd=float(f.at[dt,"qdd252"]) if pd.notna(f.at[dt,"qdd252"]) else 0.0
    pulse=bool(f.at[dt,"term_severe_pulse5"])
    cap=3.0
    if mode=="term_severe_pulse5_cap2": cap=2.0 if pulse else 3.0
    elif mode=="realized_vol30_cap2": cap=2.0 if rv>=0.30 else 3.0
    elif mode=="dd_budget": cap=1.25 if qdd<=-.15 else (2.0 if qdd<=-.10 else (2.5 if qdd<=-.05 else 3.0))
    elif mode=="pulse_vol":
        volcap=max(1.0,min(3.0,.60/max(rv,.01)))
        cap=min(2.0 if pulse else 3.0,volcap)
    return min(frozen,cap)

def _daily(rows,tq,f,mode):
    out=[];hits=0
    for i in range(1,len(rows)):
        src=rows[i-1];dt=pd.Timestamp(src["date"]);frozen=float(src["leverage"]);exp=_cap(mode,frozen,f,dt)
        hits+=int(exp<frozen-1e-12)
        q0,t0=weights_for_leverage(exp) if exp>0 else (0.,0.);q=q0*TARGET_INVESTED_FRACTION;t=t0*TARGET_INVESTED_FRACTION
        qr=float(rows[i]["close"])/float(rows[i-1]["close"])-1.;tr=tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1.
        out.append(q*qr+t*tr)
    return out,hits

def _paired(series):
    n=len(series["baseline"]);out={}
    for block in BLOCKS:
        rng=random.Random(SEED+1000+block);samples={m:[] for m in MODES}
        for _ in range(BOOTSTRAPS):
            idx=_block_indices(n,block,rng)
            for m in MODES:samples[m].append(_path_metrics([series[m][i] for i in idx]))
        base=samples["baseline"];bo={}
        for m in MODES:
            vals=samples[m];dd=[v["max_drawdown"]-b["max_drawdown"] for v,b in zip(vals,base)]
            wr=[v["end_equity"]/b["end_equity"] for v,b in zip(vals,base)]
            bo[m]={"samples":BOOTSTRAPS,
              "max_drawdown_quantiles":_quantiles([v["max_drawdown"] for v in vals]),
              "end_equity_quantiles":_quantiles([v["end_equity"] for v in vals]),
              "paired_maxdd_improvement_quantiles":_quantiles(dd),
              "paired_terminal_wealth_ratio_quantiles":_quantiles(wr),
              "probability_drawdown_below_50pct":sum(v["max_drawdown"]<=-.50 for v in vals)/len(vals),
              "probability_drawdown_below_60pct":sum(v["max_drawdown"]<=-.60 for v in vals)/len(vals),
              "probability_paired_dd_improvement":sum(x>0 for x in dd)/len(dd),
              "probability_preserve_at_least_80pct_terminal_wealth":sum(x>=.80 for x in wr)/len(wr)}
        out[str(block)]=bo
    return out

def build(out=OUT):
    rows,tq,_,_=_aligned();start=rows[0]["date"];end=(pd.Timestamp(rows[-1]["date"])+pd.Timedelta(days=2)).date().isoformat()
    f=_augment(_download(start,end));series={};hits={}
    for m in MODES:series[m],hits[m]=_daily(rows,tq,f,m)
    result={"schema_version":1,"kind":"DYNAMIC_OVERLAY_PAIRED_TAIL_VALIDATION_RESEARCH_ONLY",
      "frozen_model":"StockLens 8.0","frozen_model_mutated":False,"promotion_allowed":False,
      "modes":list(MODES),"intervention_sessions":hits,
      "historical_path":{m:_path_metrics(series[m]) for m in MODES},
      "paired_cluster_bootstrap":_paired(series),
      "anti_overfit_contract":["No new thresholds","Four pre-existing mechanism families only","Identical sampled block indices across modes","No automatic winner selection or promotion","Prior completed-session features only"],
      "claim_boundary":"Paired path-risk comparison of previously declared overlays. Bootstrap is not a market forecast and historical protection does not establish future protection or investability."}
    Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))
