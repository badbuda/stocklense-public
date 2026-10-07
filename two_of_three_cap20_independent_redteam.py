from __future__ import annotations
import json,random
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import _path_metrics,_block_indices,_quantiles,BOOTSTRAPS,SEED
OUT=Path("research/two_of_three_cap20_independent_redteam.json")
BLOCKS=(5,21,63,126)
def build(out=OUT):
 rows,tq,_,_=_aligned(); dates=pd.to_datetime([r["date"] for r in rows]); q=pd.Series([float(r["close"]) for r in rows],index=dates); qr=q.pct_change(fill_method=None)
 rv10=qr.rolling(10,10).std()*(252**.5); rv20=qr.rolling(20,20).std()*(252**.5); rv60=qr.rolling(60,40).std()*(252**.5); vcap=(.60/rv20.replace(0,float("nan"))).clip(1,3); acc=rv10>1.15*rv60
 gap=qr.rolling(5,5).min()<-.05; dd=q/q.cummax()-1; ddv=(dd-dd.shift(5))<-.06; sev=(rv10/rv60.replace(0,float("nan")))>1.5
 tail=acc&((gap.astype(int)+ddv.astype(int)+sev.astype(int))>=2)
 def run(mode="candidate",lag=0,release=1,cost=0.,mask=None):
  ret=[]; lev=[]; flags=[]; prev=None; cooldown=0
  for i in range(1,len(rows)):
   frozen=float(rows[i-1]["leverage"]); j=i-1-lag; c=3.; active=False
   if mode!="baseline" and j>=0 and bool(acc.iloc[j]) and pd.notna(vcap.iloc[j]): c=float(vcap.iloc[j])
   if mode=="candidate" and j>=0 and bool(tail.iloc[j]): cooldown=max(cooldown,release); active=True
   if mode=="candidate" and cooldown>0: c=min(c,2.0); cooldown-=1
   e=min(frozen,c); rq=float(rows[i]["close"])/float(rows[i-1]["close"])-1; rt=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1
   fee=0 if prev is None else cost/10000.*abs(e-prev); prev=e; q0,t0=weights_for_leverage(e) if e>0 else (0.,0.)
   r=TARGET_INVESTED_FRACTION*(q0*rq+t0*rt)-fee
   if mask is None or mask[i-1]: ret.append(r); lev.append(e); flags.append(active)
  return ret,lev,flags
 base,_,_=run("baseline"); accel,_,_=run("accel10"); cand,lev,fl=run(); bm=_path_metrics(base); am=_path_metrics(accel); cm=_path_metrics(cand)
 def rel(x): return {"wealth_vs_baseline":x["end_equity"]/bm["end_equity"],"dd_improvement_vs_baseline":x["max_drawdown"]-bm["max_drawdown"]}
 lag_release={}
 for L in (1,2,5):
  for R in (1,2,3,5):
   x=_path_metrics(run("candidate",L,R)[0]); lag_release[f"lag{L}_release{R}"]={**x,**rel(x)}
 costs={}
 for cst in (2.5,5.,10.,20.):
  x=_path_metrics(run("candidate",0,1,cst)[0]); costs[str(cst)]={**x,**rel(x)}
 # Fixed temporal falsification; no threshold tuning.
 periods={"pre2018":dates[1:]<pd.Timestamp("2018-01-01"),"2018plus":dates[1:]>=pd.Timestamp("2018-01-01"),"pre2020":dates[1:]<pd.Timestamp("2020-01-01"),"post2020":dates[1:]>=pd.Timestamp("2020-01-01"),"covid":(dates[1:]>=pd.Timestamp("2020-02-01"))&(dates[1:]<=pd.Timestamp("2020-06-30")),"y2022":(dates[1:]>=pd.Timestamp("2022-01-01"))&(dates[1:]<=pd.Timestamp("2022-12-31"))}
 sub={}
 for k,m in periods.items():
  xb=_path_metrics(run("baseline",mask=m)[0]); xc=_path_metrics(run("candidate",mask=m)[0]); sub[k]={"wealth_ratio":xc["end_equity"]/xb["end_equity"],"dd_improvement":xc["max_drawdown"]-xb["max_drawdown"]}
 leave={}
 for k,m in {"exclude_covid":~periods["covid"],"exclude_2022":~periods["y2022"]}.items():
  xb=_path_metrics(run("baseline",mask=m)[0]); xc=_path_metrics(run("candidate",mask=m)[0]); leave[k]={"wealth_ratio":xc["end_equity"]/xb["end_equity"],"dd_improvement":xc["max_drawdown"]-xb["max_drawdown"]}
 # Rolling 3y/5y fixed windows, evaluated versus accel10 and baseline.
 rolling={}
 for yrs in (3,5):
  n=252*yrs; arr=[]
  for end in range(n,len(base)+1,21):
   bb=_path_metrics(base[end-n:end]); aa=_path_metrics(accel[end-n:end]); cc=_path_metrics(cand[end-n:end])
   arr.append({"end":str(dates[end].date()),"wealth_vs_baseline":cc["end_equity"]/bb["end_equity"],"wealth_vs_accel10":cc["end_equity"]/aa["end_equity"],"dd_vs_baseline":cc["max_drawdown"]-bb["max_drawdown"],"dd_vs_accel10":cc["max_drawdown"]-aa["max_drawdown"]})
  rolling[str(yrs)]={"windows":len(arr),"p_wealth_ge_accel10":sum(x["wealth_vs_accel10"]>=1 for x in arr)/len(arr),"p_dd_better_accel10":sum(x["dd_vs_accel10"]>0 for x in arr)/len(arr),"p_joint_preserve95_and_dd1pp":sum(x["wealth_vs_accel10"]>=.95 and x["dd_vs_accel10"]>=.01 for x in arr)/len(arr),"median_wealth_vs_accel10":sorted(x["wealth_vs_accel10"] for x in arr)[len(arr)//2],"median_dd_vs_accel10":sorted(x["dd_vs_accel10"] for x in arr)[len(arr)//2]}
 # Worst drawdown attribution.
 def worst(r):
  eq=[];v=1.;peak=1.;pi=0;worstv=0.;out=(0,0)
  for i,x in enumerate(r): v*=1+x; eq.append(v); 
  for i,v in enumerate(eq):
   if v>peak: peak=v;pi=i
   z=v/peak-1
   if z<worstv: worstv=z;out=(pi,i)
  p,t=out; return {"max_drawdown":worstv,"peak_date":str(dates[p+1].date()),"trough_date":str(dates[t+1].date()),"tail_flags_in_drawdown":int(sum(fl[p:t+1]))}
 attribution={"baseline":worst(base),"accel10":worst(accel),"candidate":worst(cand)}
 boot={}
 for block in BLOCKS:
  rng=random.Random(SEED+20261004+block); wr=[]; di=[]; wa=[]
  for _ in range(BOOTSTRAPS):
   ix=_block_indices(len(base),block,rng); b=_path_metrics([base[i] for i in ix]); a=_path_metrics([accel[i] for i in ix]); c=_path_metrics([cand[i] for i in ix])
   wr.append(c["end_equity"]/b["end_equity"]); wa.append(c["end_equity"]/a["end_equity"]); di.append(c["max_drawdown"]-b["max_drawdown"])
  boot[str(block)]={"wealth_vs_baseline":_quantiles(wr),"wealth_vs_accel10":_quantiles(wa),"dd":_quantiles(di),"p_preserve85_baseline":sum(x>=.85 for x in wr)/len(wr),"p_beat_accel10":sum(x>=1 for x in wa)/len(wa),"p_dd_improve":sum(x>0 for x in di)/len(di)}
 res={"kind":"TWO_OF_THREE_CAP20_INDEPENDENT_REDTEAM_RESEARCH_ONLY","frozen_model_mutated":False,"candidate_precommitted":"accel10 + at least two of gap/dd-velocity/severity => 2.0x cap","historical":{"baseline":bm,"accel10":{**am,**rel(am)},"candidate":{**cm,**rel(cm),"wealth_vs_accel10":cm["end_equity"]/am["end_equity"],"dd_vs_accel10":cm["max_drawdown"]-am["max_drawdown"],"mean_leverage":sum(lev)/len(lev)}},"lag_release":lag_release,"cost_sensitivity":costs,"subperiods":sub,"leave_crisis_out":leave,"rolling_windows":rolling,"worst_drawdown_attribution":attribution,"paired_cluster_bootstrap":boot,"claim_boundary":"Independent falsification only; no promotion and no frozen mutation."}
 Path(out).write_text(json.dumps(res,indent=2)+"\n"); return res
if __name__=="__main__": print(json.dumps(build(),indent=2))
