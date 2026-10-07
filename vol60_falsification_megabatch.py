from __future__ import annotations
import json, math, random
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import _path_metrics

OUT=Path("research/vol60_falsification_megabatch.json")
LAGS=(0,1,2,5)
RELEASES=(1,3,5)

def _base(rows,tq):
    d=pd.to_datetime([r["date"] for r in rows])
    q=pd.Series([float(r["close"]) for r in rows],index=d)
    qr=q.pct_change(fill_method=None)
    rv20=qr.rolling(20,min_periods=20).std()*(252**0.5)
    cap=(0.60/rv20.replace(0,float("nan"))).clip(lower=1,upper=3)
    return d,cap

def _returns(rows,tq,caps,lag=0,release=1,static=None):
    out=[]; exp=[]; hits=0; held=3.0; age=release
    for i in range(1,len(rows)):
        frozen=float(rows[i-1]["leverage"])
        j=i-1-lag
        raw=3.0 if j<0 or pd.isna(caps.iloc[j]) else float(caps.iloc[j])
        if static is not None: raw=float(static)
        if release>1 and static is None:
            if raw<held: held=raw; age=0
            elif age<release: age+=1
            else: held=raw
            cap=held
        else: cap=raw
        e=min(frozen,cap); exp.append(e); hits+=int(e<frozen-1e-12)
        q0,t0=weights_for_leverage(e) if e>0 else (0.,0.)
        qr=float(rows[i]["close"])/float(rows[i-1]["close"])-1
        tr=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1
        out.append(TARGET_INVESTED_FRACTION*(q0*qr+t0*tr))
    return out,exp,hits

def _slice_metrics(rets,dates,start=None,end=None):
    ix=[i for i,d in enumerate(dates[1:]) if (start is None or d>=pd.Timestamp(start)) and (end is None or d<=pd.Timestamp(end))]
    return _path_metrics([rets[i] for i in ix]) if ix else None

def build(out=OUT):
    rows,tq,_,_=_aligned(); dates,caps=_base(rows,tq)
    base,be,_=_returns(rows,tq,caps,static=3.0)
    variants={}
    for lag in LAGS:
        for rel in RELEASES:
            k=f"lag{lag}_release{rel}"
            r,e,h=_returns(rows,tq,caps,lag=lag,release=rel)
            variants[k]={"returns":r,"mean_leverage":sum(e)/len(e),"interventions":h}
    periods={"pre2020":(None,"2019-12-31"),"post2020":("2020-01-01",None),
             "gfc":("2007-10-01","2009-06-30"),"covid":("2020-02-01","2020-06-30"),
             "inflation2022":("2022-01-01","2022-12-31")}
    full_base=_path_metrics(base); report={}
    for k,v in variants.items():
        x=_path_metrics(v["returns"]); static,_e,_h=_returns(rows,tq,caps,static=v["mean_leverage"]); sx=_path_metrics(static)
        sub={}
        for p,(a,b) in periods.items():
            bm=_slice_metrics(base,dates,a,b); vm=_slice_metrics(v["returns"],dates,a,b)
            if bm and vm: sub[p]={"wealth_ratio":vm["end_equity"]/bm["end_equity"],"dd_improvement":vm["max_drawdown"]-bm["max_drawdown"]}
        report[k]={"full":x,"wealth_ratio_vs_baseline":x["end_equity"]/full_base["end_equity"],
          "dd_improvement_vs_baseline":x["max_drawdown"]-full_base["max_drawdown"],
          "matched_static":{"wealth_ratio":x["end_equity"]/sx["end_equity"],"dd_improvement":x["max_drawdown"]-sx["max_drawdown"]},
          "mean_leverage":v["mean_leverage"],"interventions":v["interventions"],"subperiods":sub}
    # leave-one-crisis-out: remove each crisis interval entirely, preserving paired dates
    loco={}
    crises={"gfc":("2007-10-01","2009-06-30"),"covid":("2020-02-01","2020-06-30"),"inflation2022":("2022-01-01","2022-12-31")}
    champion=variants["lag0_release1"]["returns"]
    for name,(a,b) in crises.items():
        keep=[i for i,d in enumerate(dates[1:]) if not(pd.Timestamp(a)<=d<=pd.Timestamp(b))]
        bm=_path_metrics([base[i] for i in keep]); vm=_path_metrics([champion[i] for i in keep])
        loco[name]={"wealth_ratio":vm["end_equity"]/bm["end_equity"],"dd_improvement":vm["max_drawdown"]-bm["max_drawdown"]}
    result={"schema_version":1,"kind":"VOL60_FALSIFICATION_MEGABATCH_RESEARCH_ONLY","frozen_model_mutated":False,
      "selection_contract":"vol60 fixed by prior batch; no target retuning here","lags":list(LAGS),"release_days":list(RELEASES),
      "baseline":full_base,"variants":report,"leave_one_crisis_out":loco,
      "pass_rule":"No promotion. A robust continuation requires lag stability, no single-crisis dependence, and dynamic advantage over matched static exposure.",
      "claim_boundary":"Historical falsification only; no automatic promotion."}
    Path(out).write_text(json.dumps(result,indent=2)+"\n"); return result
if __name__=="__main__": print(json.dumps(build(),indent=2))
