from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import _path_metrics
OUT=Path("research/two_of_three_timing_attribution_megabatch.json")
def build(out=OUT):
 rows,tq,_,_=_aligned(); d=pd.to_datetime([r["date"] for r in rows]); q=pd.Series([float(r["close"]) for r in rows],index=d); qr=q.pct_change(fill_method=None)
 rv10=qr.rolling(10,10).std()*(252**.5);rv20=qr.rolling(20,20).std()*(252**.5);rv60=qr.rolling(60,40).std()*(252**.5);vcap=(.60/rv20.replace(0,float("nan"))).clip(1,3);acc=rv10>1.15*rv60
 gap=qr.rolling(5,5).min()<-.05;dd=q/q.cummax()-1;ddv=(dd-dd.shift(5))<-.06;sev=(rv10/rv60.replace(0,float("nan")))>1.5;tail=acc&((gap.astype(int)+ddv.astype(int)+sev.astype(int))>=2)
 def run(kind="candidate",delay=0,confirm=1):
  rr=[]; meta=[];prev_tail=False
  for i in range(1,len(rows)):
   frozen=float(rows[i-1]["leverage"]);j=i-1-delay;c=3.;is_tail=False
   if kind!="baseline" and j>=0 and bool(acc.iloc[j]) and pd.notna(vcap.iloc[j]):c=float(vcap.iloc[j])
   if kind=="candidate" and j>=0:
    raw=bool(tail.iloc[j]); is_tail=raw and (confirm==1 or (j>0 and bool(tail.iloc[j-1])))
    if is_tail:c=min(c,2.)
   e=min(frozen,c);q0,t0=weights_for_leverage(e) if e>0 else (0.,0.);rq=float(rows[i]["close"])/float(rows[i-1]["close"])-1;rt=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1;r=TARGET_INVESTED_FRACTION*(q0*rq+t0*rt)
   rr.append(r);meta.append({"date":str(d[i].date()),"r":r,"tail":is_tail,"gap":bool(gap.iloc[j]) if j>=0 else False,"ddv":bool(ddv.iloc[j]) if j>=0 else False,"sev":bool(sev.iloc[j]) if j>=0 else False,"lev":e})
  return rr,meta
 b,bm=run("baseline");a,am=run("accel10");c,cm=run();B=_path_metrics(b);A=_path_metrics(a);C=_path_metrics(c)
 # Event contribution: candidate minus accel10 by tail event date, sorted without tuning.
 events=[]
 for i,m in enumerate(cm):
  if m["tail"]:
   delta=c[i]-a[i];events.append({**m,"delta_vs_accel10":delta,"accel10_return":a[i],"candidate_return":c[i]})
 events=sorted(events,key=lambda x:x["delta_vs_accel10"])
 neg=sum(x["delta_vs_accel10"] for x in events if x["delta_vs_accel10"]<0);pos=sum(x["delta_vs_accel10"] for x in events if x["delta_vs_accel10"]>0)
 years={}
 for y in sorted(set(d[1:].year)):
  ix=[i for i,x in enumerate(d[1:]) if x.year==y]
  if not ix:continue
  bb=_path_metrics([b[i] for i in ix]);aa=_path_metrics([a[i] for i in ix]);cc=_path_metrics([c[i] for i in ix])
  years[str(y)]={"wealth_vs_accel10":cc["end_equity"]/aa["end_equity"],"dd_vs_accel10":cc["max_drawdown"]-aa["max_drawdown"],"tail_days":sum(cm[i]["tail"] for i in ix)}
 timing={}
 for delay in (0,1,2,3,5):
  for conf in (1,2):
   x,_=run("candidate",delay,conf);X=_path_metrics(x);timing[f"delay{delay}_confirm{conf}"]={"wealth_vs_baseline":X["end_equity"]/B["end_equity"],"wealth_vs_accel10":X["end_equity"]/A["end_equity"],"dd_vs_baseline":X["max_drawdown"]-B["max_drawdown"],"dd_vs_accel10":X["max_drawdown"]-A["max_drawdown"]}
 # Exact drawdown episodes top 10 for candidate and accel10.
 def episodes(r):
  eq=[];v=1.;peak=1.;pi=0;eps=[];in_dd=False;start=0
  for i,x in enumerate(r):
   v*=1+x;eq.append(v)
   if v>=peak:
    if in_dd: eps.append((worst,start,i-1,pi))
    peak=v;pi=i;in_dd=False;worst=0.
   else:
    z=v/peak-1
    if not in_dd:start=i;worst=z;in_dd=True
    worst=min(worst,z)
  if in_dd:eps.append((worst,start,len(r)-1,pi))
  return [{"drawdown":x[0],"peak_date":str(d[x[3]+1].date()),"trough_region_start":str(d[x[1]+1].date()),"episode_end":str(d[x[2]+1].date())} for x in sorted(eps)[:10]]
 # Predeclared execution-robustness diagnostics: no parameter selection.
 # Compare confirmation as a stability diagnostic and quantify COVID concentration.
 covid_ix=[i for i,x in enumerate(d[1:]) if x.year==2020]
 noncov_ix=[i for i,x in enumerate(d[1:]) if x.year!=2020]
 def slice_rel(ix,confirm):
  x,_=run("candidate",0,confirm); aa=_path_metrics([a[i] for i in ix]); xx=_path_metrics([x[i] for i in ix])
  return {"wealth_vs_accel10":xx["end_equity"]/aa["end_equity"],"dd_vs_accel10":xx["max_drawdown"]-aa["max_drawdown"]}
 concentration={"confirm1_2020":slice_rel(covid_ix,1),"confirm1_non2020":slice_rel(noncov_ix,1),"confirm2_2020":slice_rel(covid_ix,2),"confirm2_non2020":slice_rel(noncov_ix,2)}
 res={"kind":"TWO_OF_THREE_TIMING_ATTRIBUTION_MEGABATCH_RESEARCH_ONLY","frozen_model_mutated":False,"historical":{"baseline":B,"accel10":A,"candidate":C},"event_attribution":{"tail_event_count":len(events),"sum_positive_delta":pos,"sum_negative_delta":neg,"worst_15_events":events[:15],"best_15_events":events[-15:]},"year_attribution":years,"timing_robustness":timing,"covid_concentration_diagnostic":concentration,"top_drawdown_episodes":{"accel10":episodes(a),"candidate":episodes(c)},"claim_boundary":"Mechanism/timing diagnosis only. Confirm2 is falsification, not a selected replacement."}
 Path(out).write_text(json.dumps(res,indent=2)+"\n");return res
if __name__=="__main__":print(json.dumps(build(),indent=2))
