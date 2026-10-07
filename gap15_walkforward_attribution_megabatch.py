from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import _path_metrics
OUT=Path("research/gap15_walkforward_attribution_megabatch.json")
def build(out=OUT):
 rows,tq,_,_=_aligned();dates=pd.to_datetime([r["date"] for r in rows]);q=pd.Series([float(r["close"]) for r in rows],index=dates);qr=q.pct_change(fill_method=None)
 rv10=qr.rolling(10,10).std()*(252**.5);rv20=qr.rolling(20,20).std()*(252**.5);rv60=qr.rolling(60,40).std()*(252**.5);vcap=(.60/rv20.replace(0,float("nan"))).clip(1,3);acc=rv10>1.15*rv60;gap=qr.rolling(5,5).min()<-.05;tail=acc&gap
 base=[];cand=[];events=[]
 for i in range(1,len(rows)):
  frozen=float(rows[i-1]["leverage"]);j=i-1;cap=float(vcap.iloc[j]) if bool(acc.iloc[j]) and pd.notna(vcap.iloc[j]) else 3.;cap2=min(cap,1.5) if bool(tail.iloc[j]) else cap;e1=frozen;e2=min(frozen,cap2)
  rq=float(rows[i]["close"])/float(rows[i-1]["close"])-1;rt=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1
  def rr(e):
   q0,t0=weights_for_leverage(e) if e>0 else (0.,0.);return TARGET_INVESTED_FRACTION*(q0*rq+t0*rt)
  a,b=rr(e1),rr(e2);base.append(a);cand.append(b)
  if e2<e1-1e-12:events.append({"date":str(dates[i].date()),"baseline_leverage":e1,"candidate_leverage":e2,"baseline_return":a,"candidate_return":b,"delta_return":b-a})
 windows=[]
 years=sorted(set(x.year for x in dates[1:]))
 for start in range(min(years),max(years)-1,2):
  end=start+1;ix=[i for i,x in enumerate(dates[1:]) if start<=x.year<=end]
  if len(ix)<200:continue
  x=_path_metrics([cand[i] for i in ix]);y=_path_metrics([base[i] for i in ix]);windows.append({"period":f"{start}-{end}","sessions":len(ix),"wealth_ratio":x["end_equity"]/y["end_equity"],"dd_improvement":x["max_drawdown"]-y["max_drawdown"],"events":sum(1 for e in events if start<=pd.Timestamp(e["date"]).year<=end)})
 deltas=sorted(events,key=lambda x:abs(x["delta_return"]),reverse=True);total=sum(e["delta_return"] for e in events);top5=sum(e["delta_return"] for e in deltas[:5]);top10=sum(e["delta_return"] for e in deltas[:10])
 positive=sum(e["delta_return"]>0 for e in events);negative=sum(e["delta_return"]<0 for e in events)
 # remove largest absolute event days to test concentration
 date_to_i={str(x.date()):i for i,x in enumerate(dates[1:])};trim={}
 for n in (1,3,5,10):
  remove={date_to_i[e["date"]] for e in deltas[:n]};ix=[i for i in range(len(base)) if i not in remove];x=_path_metrics([cand[i] for i in ix]);y=_path_metrics([base[i] for i in ix]);trim[str(n)]={"wealth_ratio":x["end_equity"]/y["end_equity"],"dd_improvement":x["max_drawdown"]-y["max_drawdown"]}
 res={"kind":"GAP15_WALKFORWARD_ATTRIBUTION_MEGABATCH_RESEARCH_ONLY","frozen_model_mutated":False,"two_year_nonoverlap_windows":windows,"event_attribution":{"event_count":len(events),"positive_events":positive,"negative_events":negative,"sum_delta_return":total,"top5_delta_share":None if total==0 else top5/total,"top10_delta_share":None if total==0 else top10/total,"largest_events":deltas[:20]},"trim_largest_event_days":trim,"falsification_rule":{"concern_if_majority_windows_wealth_below_0_97_and_dd_below_0_01":True,"concern_if_trim5_eliminates_dd_edge":True},"claim_boundary":"Predeclared candidate only; no threshold tuning or automatic promotion."}
 Path(out).write_text(json.dumps(res,indent=2)+"\n");return res
if __name__=="__main__":print(json.dumps(build(),indent=2))
