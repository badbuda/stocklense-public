from __future__ import annotations
from pathlib import Path
import pandas as pd

def build(src,out="research/data/SL9-007-UPSHIFT-CONFIRMATION.csv",up_confirm=2):
 df=pd.read_csv(src);q=df.qqq_return.astype(float);base=df.baseline_leverage.astype(float)
 executed=[];current=float(base.iloc[0]);pending=None;count=0
 for target in base.astype(float):
  if target<current:
   current=target;pending=None;count=0
  elif target>current:
   if pending==target: count+=1
   else: pending=target;count=1
   if count>=up_confirm:
    current=target;pending=None;count=0
  else:
   pending=None;count=0
  executed.append(current)
 candidate=pd.Series(executed,index=df.index,dtype=float)
 x=pd.DataFrame({"date":df.date.astype(str),"strategy_return":q*candidate,"benchmark_return":df.baseline_return.astype(float),
  "underlying_return":q,"strategy_exposure":candidate,"baseline_exposure":base})
 p=Path(out);p.parent.mkdir(parents=True,exist_ok=True);x.to_csv(p,index=False)
 return {"name":"asymmetric_upshift_confirmation","up_confirm":up_confirm,"down_confirm":1,
  "timing":"baseline target already lagged to execution session; challenger confirms consecutive upshift targets","rows":len(x),
  "changed_sessions":int((candidate!=base).sum()),"changed_fraction":float((candidate!=base).mean())}
