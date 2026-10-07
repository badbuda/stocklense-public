from __future__ import annotations
import json, random
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from risk_overlay_multifactor import _download
from risk_overlay_deep_dive import _augment
from orthogonal_tail_validation import BLOCKS, BOOTSTRAPS, SEED, _block_indices, _path_metrics, _quantiles
OUT=Path("research/pulse_vol_reentry_validation.json")
MODES=("baseline","pulse_vol","pulse_vol_fast_release","pulse_vol_step_release","pulse_vol_recovery_release")
def _raw_cap(f,dt):
    if dt not in f.index:return 3.0
    rv=float(f.at[dt,"rv20"]) if pd.notna(f.at[dt,"rv20"]) else 0.0
    pulse=bool(f.at[dt,"term_severe_pulse5"])
    return min(2.0 if pulse else 3.0,max(1.0,min(3.0,.60/max(rv,.01))))
def _caps(f,dates,mode):
    raw=[_raw_cap(f,dt) for dt in dates]
    if mode=="baseline":return [3.0]*len(raw)
    if mode=="pulse_vol":return raw
    out=[];prev=3.0
    for dt,r in zip(dates,raw):
        if r<prev:cap=r
        elif r>=3.0:
            if mode=="pulse_vol_fast_release":cap=3.0
            elif mode=="pulse_vol_step_release":cap=min(3.0,prev+0.5)
            elif mode=="pulse_vol_recovery_release":
                rec=bool(f.at[dt,"term_severe_recovery3"]) if dt in f.index else False
                cap=min(3.0,prev+0.5) if rec else 3.0
            else:cap=r
        else:cap=r
        out.append(cap);prev=cap
    return out
def _daily(rows,tq,f,mode):
    dates=[pd.Timestamp(rows[i-1]["date"]) for i in range(1,len(rows))];caps=_caps(f,dates,mode);out=[];hits=0
    for i,cap in enumerate(caps,1):
        frozen=float(rows[i-1]["leverage"]);exp=min(frozen,cap);hits+=int(exp<frozen-1e-12)
        q0,t0=weights_for_leverage(exp) if exp>0 else (0.,0.);q=q0*TARGET_INVESTED_FRACTION;t=t0*TARGET_INVESTED_FRACTION
        qr=float(rows[i]["close"])/float(rows[i-1]["close"])-1.;tr=tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1.;out.append(q*qr+t*tr)
    return out,hits
def _paired(series):
    n=len(series["baseline"]);out={}
    for block in BLOCKS:
        rng=random.Random(SEED+3000+block);samples={m:[] for m in MODES}
        for _ in range(BOOTSTRAPS):
            idx=_block_indices(n,block,rng)
            for m in MODES:samples[m].append(_path_metrics([series[m][i] for i in idx]))
        base=samples["baseline"];pv=samples["pulse_vol"];bo={}
        for m in MODES:
            vals=samples[m];dd=[v["max_drawdown"]-b["max_drawdown"] for v,b in zip(vals,base)];wr=[v["end_equity"]/b["end_equity"] for v,b in zip(vals,base)]
            pdd=[v["max_drawdown"]-p["max_drawdown"] for v,p in zip(vals,pv)];pwr=[v["end_equity"]/p["end_equity"] for v,p in zip(vals,pv)]
            bo[m]={"max_drawdown_quantiles":_quantiles([v["max_drawdown"] for v in vals]),"paired_maxdd_improvement_vs_baseline":_quantiles(dd),
             "paired_wealth_ratio_vs_baseline":_quantiles(wr),"paired_maxdd_change_vs_pulse_vol":_quantiles(pdd),"paired_wealth_ratio_vs_pulse_vol":_quantiles(pwr),
             "probability_dd_improvement_vs_baseline":sum(x>0 for x in dd)/len(dd),"probability_wealth_improvement_vs_pulse_vol":sum(x>1 for x in pwr)/len(pwr),
             "probability_preserve_90pct_baseline_wealth":sum(x>=.90 for x in wr)/len(wr),"probability_drawdown_below_60pct":sum(v["max_drawdown"]<=-.60 for v in vals)/len(vals)}
        out[str(block)]=bo
    return out
def build(out=OUT):
    rows,tq,_,_=_aligned();start=rows[0]["date"];end=(pd.Timestamp(rows[-1]["date"])+pd.Timedelta(days=2)).date().isoformat();f=_augment(_download(start,end));series={};hits={}
    for m in MODES:series[m],hits[m]=_daily(rows,tq,f,m)
    result={"schema_version":1,"kind":"PULSE_VOL_REENTRY_PAIRED_VALIDATION_RESEARCH_ONLY","frozen_model":"StockLens 8.0","frozen_model_mutated":False,"promotion_allowed":False,
     "modes":list(MODES),"intervention_sessions":hits,"historical_path":{m:_path_metrics(series[m]) for m in MODES},"paired_cluster_bootstrap":_paired(series),
     "anti_overfit_contract":["Three coarse re-entry mechanisms fixed before outcome evaluation","No entry-threshold changes","Identical sampled indices across variants","No automatic winner selection or promotion"],
     "claim_boundary":"Mechanism falsification only; diagnostic challengers are not prospectively validated rules."}
    Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))
