from __future__ import annotations
import json,random
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import _path_metrics,_block_indices,_quantiles,BOOTSTRAPS,SEED
OUT=Path("research/accel_vcap_independent_redteam.json")
def build(out=OUT):
 rows,tq,_,_=_aligned();dates=pd.to_datetime([x["date"] for x in rows]);q=pd.Series([float(x["close"]) for x in rows],index=dates);r=q.pct_change(fill_method=None)
 rv10=r.rolling(10,10).std()*(252**.5);rv20=r.rolling(20,20).std()*(252**.5);rv60=r.rolling(60,40).std()*(252**.5)
 accel=rv10>1.15*rv60;cap=(.60/rv20.replace(0,float("nan"))).clip(1,3)
 def run(candidate=True,lag=0,cost=5.):
  ret=[];lev=[];prev=None
  for i in range(1,len(rows)):
   frozen=float(rows[i-1]["leverage"]);j=i-1-lag;e=frozen
   if candidate and j>=0 and bool(accel.iloc[j]) and pd.notna(cap.iloc[j]):e=min(e,float(cap.iloc[j]))
   qw,tw=weights_for_leverage(e) if e>0 else (0.,0.);qr=float(rows[i]["close"])/float(rows[i-1]["close"])-1;tr=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1
   fee=0 if prev is None else cost/10000*abs(e-prev);prev=e;ret.append(TARGET_INVESTED_FRACTION*(qw*qr+tw*tr)-fee);lev.append(e)
  return ret,lev
 base,_=run(False);cand,_=run(True);bm=_path_metrics(base);cm=_path_metrics(cand)
 stresses={}
 for lag in (0,1,2,3,5):
  for cost in (0.,5.,10.,20.):
   b,_=run(False,lag,cost);c,_=run(True,lag,cost);x=_path_metrics(c);y=_path_metrics(b);stresses[f"lag{lag}_cost{cost:g}"]={"wealth_ratio":x["end_equity"]/y["end_equity"],"dd_improvement":x["max_drawdown"]-y["max_drawdown"]}
 windows=[]
 for start in range(dates[1].year,dates[-1].year-1,3):
  ix=[i for i,d in enumerate(dates[1:]) if start<=d.year<=start+2]
  if len(ix)<500:continue
  x=_path_metrics([cand[i] for i in ix]);y=_path_metrics([base[i] for i in ix]);windows.append({"period":f"{start}-{start+2}","wealth_ratio":x["end_equity"]/y["end_equity"],"dd_improvement":x["max_drawdown"]-y["max_drawdown"]})
 leave_year=[]
 for year in sorted(set(d.year for d in dates[1:])):
  ix=[i for i,d in enumerate(dates[1:]) if d.year!=year]
  x=_path_metrics([cand[i] for i in ix]);y=_path_metrics([base[i] for i in ix]);leave_year.append({"omitted_year":year,"wealth_ratio":x["end_equity"]/y["end_equity"],"dd_improvement":x["max_drawdown"]-y["max_drawdown"]})
 boot={}
 for block in (21,63,126):
  rng=random.Random(SEED+block+77001);wr=[];di=[]
  for _ in range(BOOTSTRAPS):
   ix=_block_indices(len(base),block,rng);x=_path_metrics([cand[i] for i in ix]);y=_path_metrics([base[i] for i in ix]);wr.append(x["end_equity"]/y["end_equity"]);di.append(x["max_drawdown"]-y["max_drawdown"])
  boot[str(block)]={"wealth":_quantiles(wr),"dd":_quantiles(di),"p_dd_improve":sum(v>0 for v in di)/len(di),"p_wealth_ge_90":sum(v>=.90 for v in wr)/len(wr)}
 checks={"historical_wealth_ge_95":cm["end_equity"]/bm["end_equity"]>=.95,"historical_dd_improve_ge_2pp":cm["max_drawdown"]-bm["max_drawdown"]>=.02,"lag1_cost5_wealth_ge_90":stresses["lag1_cost5"]["wealth_ratio"]>=.90,"lag1_cost5_dd_ge_1pp":stresses["lag1_cost5"]["dd_improvement"]>=.01,"bad_3y_windows_le_2":sum(x["wealth_ratio"]<.97 and x["dd_improvement"]<.01 for x in windows)<=2,"min_bootstrap_dd_prob_ge_75":min(x["p_dd_improve"] for x in boot.values())>=.75}
 result={"kind":"ACCEL_VCAP_INDEPENDENT_REDTEAM_RESEARCH_ONLY","candidate_contract":{"accel":"rv10 > 1.15 * rv60","vol_cap":"clip(0.60 / rv20, 1, 3)","retuned":False},"frozen_model_mutated":False,"promotion_allowed":False,"historical":{"wealth_ratio":cm["end_equity"]/bm["end_equity"],"dd_improvement":cm["max_drawdown"]-bm["max_drawdown"]},"execution_stress":stresses,"nonoverlap_3y":windows,"leave_one_year_out":leave_year,"paired_bootstrap":boot,"checks":checks,"verdict":"PASS_INDEPENDENT_REDTEAM" if all(checks.values()) else "FAIL_INDEPENDENT_REDTEAM","claim_boundary":"Independent retrospective falsification only; no promotion or live capital decision."}
 Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))
