from __future__ import annotations
import json,math,random
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import _path_metrics,_block_indices,_quantiles,BOOTSTRAPS,SEED
OUT=Path("research/accel10_tail_layer_megabatch.json");BLOCKS=(5,21,63,126)
MODES=("baseline","accel10","tail_gap","tail_ddvel","tail_severity","tail_breadth_proxy","tail_combo")
def build(out=OUT):
 rows,tq,_,_=_aligned();d=pd.to_datetime([r["date"] for r in rows]);q=pd.Series([float(r["close"]) for r in rows],index=d);qr=q.pct_change(fill_method=None)
 rv10=qr.rolling(10,10).std()*(252**.5);rv20=qr.rolling(20,20).std()*(252**.5);rv60=qr.rolling(60,40).std()*(252**.5);cap=(.60/rv20.replace(0,float("nan"))).clip(1,3);acc=rv10>1.15*rv60
 gap5=qr.rolling(5,5).min();peak=q.cummax();dd=q/peak-1;ddvel=dd-dd.shift(5);severity=(rv10/rv60.replace(0,float("nan")))
 sma20=q.rolling(20,20).mean();sma50=q.rolling(50,50).mean();breadth_proxy=(q<sma20)&(sma20<sma50)
 flags={"tail_gap":acc&(gap5<-.05),"tail_ddvel":acc&(ddvel<-.06),"tail_severity":acc&(severity>1.5),"tail_breadth_proxy":acc&breadth_proxy,"tail_combo":acc&((gap5<-.05)|(ddvel<-.06)|(severity>1.5))}
 def run(mode,lag=0,cost=0.):
  ret=[];ex=[];hit=0;tailhit=0;prev=None
  for i in range(1,len(rows)):
   frozen=float(rows[i-1]["leverage"]);j=i-1-lag;c=3.
   if j>=0 and mode!="baseline" and bool(acc.iloc[j]) and pd.notna(cap.iloc[j]):c=float(cap.iloc[j])
   if j>=0 and mode not in ("baseline","accel10") and bool(flags[mode].iloc[j]):c=min(c,1.0);tailhit+=1
   e=min(frozen,c);hit+=int(e<frozen-1e-12);q0,t0=weights_for_leverage(e) if e>0 else (0.,0.)
   rq=float(rows[i]["close"])/float(rows[i-1]["close"])-1;rt=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1
   fee=0 if prev is None else cost/10000.*abs(e-prev);prev=e;ex.append(e);ret.append(TARGET_INVESTED_FRACTION*(q0*rq+t0*rt)-fee)
  return ret,ex,hit,tailhit
 data={};series={}
 for m in MODES:
  r,e,h,th=run(m);series[m]=r;x=_path_metrics(r);data[m]={**x,"mean_leverage":sum(e)/len(e),"interventions":h,"tail_events":th,"wealth_ratio":None,"dd_improvement":None}
 b=data["baseline"]
 for m in MODES[1:]:data[m]["wealth_ratio"]=data[m]["end_equity"]/b["end_equity"];data[m]["dd_improvement"]=data[m]["max_drawdown"]-b["max_drawdown"]
 # lag falsification
 lag={}
 for m in MODES[1:]:
  lag[m]={}
  for L in (1,2):
   r,e,h,th=run(m,L);x=_path_metrics(r);lag[m][str(L)]={"wealth_ratio":x["end_equity"]/b["end_equity"],"dd_improvement":x["max_drawdown"]-b["max_drawdown"],"mean_leverage":sum(e)/len(e)}
 # economic decomposition: intervention-day next-session returns vs baseline
 decomp={}
 base=series["baseline"]
 for m in MODES[1:]:
  rr=series[m];delta=[rr[i]-base[i] for i in range(len(base))];pos=sum(x for x in delta if x>0);neg=sum(x for x in delta if x<0)
  decomp[m]={"sessions_helped":sum(x>0 for x in delta),"sessions_hurt":sum(x<0 for x in delta),"sum_help":pos,"sum_hurt":neg,"net_daily_return_delta_sum":sum(delta)}
 # exact growth / mu sigma audit on strategy daily returns
 audit={}
 for m in ("baseline","accel10","tail_combo"):
  r=series[m];mu=sum(r)/len(r);var=sum((x-mu)**2 for x in r)/len(r);exact=sum(math.log1p(x) for x in r)/len(r);second=mu-.5*var
  audit[m]={"mean_daily":mu,"variance_daily":var,"half_variance_drag":.5*var,"second_order_log_growth":second,"exact_mean_log_growth":exact,"mu_over_variance":mu/var if var else None,"mu_over_half_variance":mu/(.5*var) if var else None}
 # cost sensitivity for survivors/probes
 costs={}
 for m in MODES[1:]:
  costs[m]={}
  for cst in (2.5,5.,10.):
   r,e,_,_=run(m,0,cst);x=_path_metrics(r);costs[m][str(cst)]={"wealth_ratio":x["end_equity"]/b["end_equity"],"dd_improvement":x["max_drawdown"]-b["max_drawdown"]}
 # paired bootstrap accel10 and tail modes
 boot={}
 for m in MODES[1:]:
  boot[m]={}
  for block in BLOCKS:
   rng=random.Random(SEED+block+sum(map(ord,m)));wr=[];di=[]
   for _ in range(BOOTSTRAPS):
    ix=_block_indices(len(base),block,rng);x=_path_metrics([series[m][i] for i in ix]);y=_path_metrics([base[i] for i in ix]);wr.append(x["end_equity"]/y["end_equity"]);di.append(x["max_drawdown"]-y["max_drawdown"])
   boot[m][str(block)]={"wealth":_quantiles(wr),"dd":_quantiles(di),"p_preserve_85":sum(x>=.85 for x in wr)/len(wr),"p_dd_improve":sum(x>0 for x in di)/len(di)}
 result={"kind":"ACCEL10_TAIL_LAYER_MEGABATCH_RESEARCH_ONLY","frozen_model_mutated":False,"rules":{"accel10":"RV10>1.15*RV60 then existing 60% cap","tail_cap":"1.0x only while accel10 AND predeclared severe condition","gap":"worst 5d daily QQQ<-5%","ddvel":"5d QQQ drawdown velocity<-6pp","severity":"RV10/RV60>1.5","breadth_proxy":"QQQ<SMA20<SMA50","combo":"gap OR ddvel OR severity"},"historical":data,"lag_falsification":lag,"intervention_economics":decomp,"growth_mu_sigma_audit":audit,"cost_sensitivity":costs,"paired_cluster_bootstrap":boot,"claim_boundary":"Exploratory tail mechanisms; no threshold selection or promotion."}
 Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))
