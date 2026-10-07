from __future__ import annotations
import json, random
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import _path_metrics,_block_indices,_quantiles,BOOTSTRAPS,SEED
OUT=Path("research/gap15_final_falsification_megabatch.json")
LAGS=(0,1,2,3,5); COSTS=(0.,2.5,5.,10.,20.); BLOCKS=(5,21,63,126)
def build(out=OUT):
 rows,tq,_,_=_aligned(); dates=pd.to_datetime([r["date"] for r in rows]); q=pd.Series([float(r["close"]) for r in rows],index=dates); qr=q.pct_change(fill_method=None)
 rv10=qr.rolling(10,10).std()*(252**.5); rv20=qr.rolling(20,20).std()*(252**.5); rv60=qr.rolling(60,40).std()*(252**.5)
 vcap=(.60/rv20.replace(0,float("nan"))).clip(1,3); accel=rv10>1.15*rv60; gap=qr.rolling(5,5).min()<-.05; tail=accel&gap
 def run(mode="baseline",lag=0,cost=0.,persist=1):
  ret=[]; lev=[]; flags=[]; prev=None
  for i in range(1,len(rows)):
   frozen=float(rows[i-1]["leverage"]); j=i-1-lag; cap=3.; hit=False
   if mode!="baseline" and j>=0 and bool(accel.iloc[j]) and pd.notna(vcap.iloc[j]): cap=float(vcap.iloc[j])
   if mode=="gap15" and j>=0:
    lo=max(0,j-persist+1); hit=any(bool(tail.iloc[k]) for k in range(lo,j+1))
    if hit: cap=min(cap,1.5)
   e=min(frozen,cap); q0,t0=weights_for_leverage(e) if e>0 else (0.,0.); rq=float(rows[i]["close"])/float(rows[i-1]["close"])-1; rt=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1
   fee=0. if prev is None else cost/10000.*abs(e-prev); prev=e
   ret.append(TARGET_INVESTED_FRACTION*(q0*rq+t0*rt)-fee); lev.append(e); flags.append(hit and e<frozen-1e-12)
  return ret,lev,flags
 base,_,_=run(); cand,clev,hits=run("gap15"); bm=_path_metrics(base); cm=_path_metrics(cand)
 # Rolling non-overlapping and rolling 3y OOS windows
 windows=[]
 for start in range(dates[1].year,dates[-1].year-1):
  a=pd.Timestamp(f"{start}-01-01"); b=a+pd.DateOffset(years=3)-pd.Timedelta(days=1); ix=[i for i,d in enumerate(dates[1:]) if a<=d<=b]
  if len(ix)<500: continue
  x=_path_metrics([cand[i] for i in ix]); y=_path_metrics([base[i] for i in ix]); windows.append({"start":str(a.date()),"end":str(b.date()),"sessions":len(ix),"wealth_ratio":x["end_equity"]/y["end_equity"],"dd_improvement":x["max_drawdown"]-y["max_drawdown"],"interventions":sum(hits[i] for i in ix)})
 # latency x cost full interaction
 grid={}
 for lag in LAGS:
  for cost in COSTS:
   r,_,_=run("gap15",lag,cost); x=_path_metrics(r); grid[f"lag{lag}_cost{cost:g}"]={"wealth_ratio":x["end_equity"]/bm["end_equity"],"dd_improvement":x["max_drawdown"]-bm["max_drawdown"]}
 # persistence is falsification only, not candidate search
 persistence={}
 for p in (1,2,3,5):
  r,l,h=run("gap15",0,5.,p); x=_path_metrics(r); changes=sum(abs(l[i]-l[i-1])>1e-12 for i in range(1,len(l))); persistence[str(p)]={"wealth_ratio":x["end_equity"]/bm["end_equity"],"dd_improvement":x["max_drawdown"]-bm["max_drawdown"],"interventions":sum(h),"leverage_changes":changes}
 # event rebound/false-positive attribution
 ev=[]
 for i,h in enumerate(hits):
  if not h: continue
  rec={"date":str(dates[i+1].date()),"delta_day":cand[i]-base[i]}
  for horizon in (1,3,5,10):
   end=min(len(base),i+1+horizon); rec[f"future_{horizon}d_baseline"]=sum(base[i+1:end]); rec[f"future_{horizon}d_candidate"]=sum(cand[i+1:end])
  ev.append(rec)
 falsepos={str(h):sum(e[f"future_{h}d_baseline"]>0 for e in ev)/len(ev) if ev else None for h in (1,3,5,10)}
 # leave each calendar year out
 leave={}
 for yr in sorted(set(d.year for d in dates[1:])):
  ix=[i for i,d in enumerate(dates[1:]) if d.year!=yr]
  x=_path_metrics([cand[i] for i in ix]); y=_path_metrics([base[i] for i in ix]); leave[str(yr)]={"wealth_ratio":x["end_equity"]/y["end_equity"],"dd_improvement":x["max_drawdown"]-y["max_drawdown"]}
 # paired cluster bootstrap
 boot={}
 for block in BLOCKS:
  rng=random.Random(SEED+88000+block); wr=[]; di=[]
  for _ in range(BOOTSTRAPS):
   ix=_block_indices(len(base),block,rng); x=_path_metrics([cand[i] for i in ix]); y=_path_metrics([base[i] for i in ix]); wr.append(x["end_equity"]/y["end_equity"]); di.append(x["max_drawdown"]-y["max_drawdown"])
  boot[str(block)]={"wealth":_quantiles(wr),"dd":_quantiles(di),"p_wealth_90":sum(v>=.90 for v in wr)/len(wr),"p_dd_improve":sum(v>0 for v in di)/len(di)}
 # explicit fixed gate; no tuning from this output
 primary=grid["lag1_cost5"]
 bad_windows=sum(w["wealth_ratio"]<.97 and w["dd_improvement"]<.01 for w in windows)
 bad_leave=sum(v["wealth_ratio"]<.97 and v["dd_improvement"]<.01 for v in leave.values())
 min_boot=min(v["p_dd_improve"] for v in boot.values())
 checks={"historical_wealth_ge_0_95":cm["end_equity"]/bm["end_equity"]>=.95,"historical_dd_improve_ge_0_02":cm["max_drawdown"]-bm["max_drawdown"]>=.02,"lag1_cost5_wealth_ge_0_90":primary["wealth_ratio"]>=.90,"lag1_cost5_dd_ge_0_01":primary["dd_improvement"]>=.01,"rolling_bad_windows_le_2":bad_windows<=2,"leave_year_bad_le_2":bad_leave<=2,"bootstrap_min_p_dd_ge_0_75":min_boot>=.75}
 verdict="PASS_RESEARCH_GATE" if all(checks.values()) else "FAIL_RESEARCH_GATE"
 res={"kind":"GAP15_FINAL_FALSIFICATION_MEGABATCH_RESEARCH_ONLY","frozen_model_mutated":False,"promotion_allowed":False,"candidate_contract":{"rv10_over_rv60":1.15,"gap_5d_min_return":-.05,"tail_cap":1.5,"no_threshold_retuning":True},"historical":{"wealth_ratio":cm["end_equity"]/bm["end_equity"],"dd_improvement":cm["max_drawdown"]-bm["max_drawdown"],"interventions":sum(hits)},"rolling_3y_oos":windows,"latency_cost_grid":grid,"persistence_falsification":persistence,"rebound_false_positive_rate":falsepos,"leave_each_year_out":leave,"paired_cluster_bootstrap":boot,"decision":{"checks":checks,"bad_rolling_windows":bad_windows,"bad_leave_years":bad_leave,"min_bootstrap_p_dd_improve":min_boot,"verdict":verdict,"meaning":"Research gate only. PASS does not authorize promotion or live capital; prospective evidence remains required."}}
 Path(out).write_text(json.dumps(res,indent=2)+"\n"); return res
if __name__=="__main__": print(json.dumps(build(),indent=2))
