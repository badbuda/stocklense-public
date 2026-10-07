from __future__ import annotations
import json,random
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from risk_overlay_multifactor import _download
from risk_overlay_deep_dive import _augment
from orthogonal_tail_validation import BLOCKS,BOOTSTRAPS,SEED,_block_indices,_path_metrics,_quantiles
OUT=Path("research/pulse_vol_component_attribution.json"); MODES=("baseline","pulse_only","vol_only","pulse_vol")
def cap(f,dt,m):
 if m=="baseline" or dt not in f.index:return 3.
 rv=float(f.at[dt,"rv20"]) if pd.notna(f.at[dt,"rv20"]) else 0.; pulse=bool(f.at[dt,"term_severe_pulse5"]); pc=2. if pulse else 3.; vc=max(1.,min(3.,.60/max(rv,.01)))
 return pc if m=="pulse_only" else vc if m=="vol_only" else min(pc,vc)
def daily(rows,tq,f,m):
 out=[];hits=0
 for i in range(1,len(rows)):
  frozen=float(rows[i-1]["leverage"]); exp=min(frozen,cap(f,pd.Timestamp(rows[i-1]["date"]),m)); hits+=exp<frozen-1e-12
  q0,t0=weights_for_leverage(exp) if exp>0 else (0.,0.); q=q0*TARGET_INVESTED_FRACTION;t=t0*TARGET_INVESTED_FRACTION
  out.append(q*(float(rows[i]["close"])/float(rows[i-1]["close"])-1.)+t*(tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1.))
 return out,int(hits)
def paired(s):
 n=len(s["baseline"]);out={}
 for block in BLOCKS:
  rng=random.Random(SEED+5000+block);z={m:[] for m in MODES}
  for _ in range(BOOTSTRAPS):
   idx=_block_indices(n,block,rng)
   for m in MODES:z[m].append(_path_metrics([s[m][i] for i in idx]))
  b=z["baseline"];c=z["pulse_vol"];bo={}
  for m in MODES:
   v=z[m];dd=[x["max_drawdown"]-y["max_drawdown"] for x,y in zip(v,b)];wr=[x["end_equity"]/y["end_equity"] for x,y in zip(v,b)]
   bo[m]={"max_drawdown_quantiles":_quantiles([x["max_drawdown"] for x in v]),"wealth_ratio_vs_baseline":_quantiles(wr),"dd_improvement_vs_baseline":_quantiles(dd),
    "wealth_ratio_vs_combo":_quantiles([x["end_equity"]/y["end_equity"] for x,y in zip(v,c)]),"dd_change_vs_combo":_quantiles([x["max_drawdown"]-y["max_drawdown"] for x,y in zip(v,c)]),
    "p_dd_improve_vs_baseline":sum(x>0 for x in dd)/len(dd),"p_preserve_90pct_baseline_wealth":sum(x>=.9 for x in wr)/len(wr),"p_dd_ge_60pct":sum(x["max_drawdown"]<=-.6 for x in v)/len(v)}
  out[str(block)]=bo
 return out
def build(out=OUT):
 rows,tq,_,_=_aligned();f=_augment(_download(rows[0]["date"],(pd.Timestamp(rows[-1]["date"])+pd.Timedelta(days=2)).date().isoformat()));s={};hits={}
 for m in MODES:s[m],hits[m]=daily(rows,tq,f,m)
 def st(a):return {"sum_return_delta":sum(a),"positive_fraction":sum(x>0 for x in a)/len(a),"negative_fraction":sum(x<0 for x in a)/len(a)}
 r={"schema_version":1,"kind":"PULSE_VOL_COMPONENT_ATTRIBUTION_RESEARCH_ONLY","frozen_model":"StockLens 8.0","frozen_model_mutated":False,"promotion_allowed":False,"modes":list(MODES),"intervention_sessions":hits,
 "historical_path":{m:_path_metrics(s[m]) for m in MODES},"session_attribution":{"vol_increment_over_pulse_only":st([x-y for x,y in zip(s["pulse_vol"],s["pulse_only"])]),"pulse_increment_over_vol_only":st([x-y for x,y in zip(s["pulse_vol"],s["vol_only"])])},
 "paired_cluster_bootstrap":paired(s),"anti_overfit_contract":["Component ablation only","No new thresholds","Identical paired block paths","No promotion"],"claim_boundary":"Attribution/falsification only; bootstrap is not a forecast."}
 Path(out).write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build(),indent=2))
