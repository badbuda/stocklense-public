from __future__ import annotations
import json, math, random
from pathlib import Path
import pandas as pd
from tqqq_reality_check import _aligned
from risk_overlay_multifactor import _download
from risk_overlay_deep_dive import _augment
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from sparse_tail_confirmation_validation import cap
from orthogonal_tail_validation import _path_metrics

OUT=Path("research/sparse_tail_redteam_megabatch.json")
SEED=20261002
LAGS=(0,1,2,3,5)
SHIFTS=(-63,-20,-10,-5,-2,-1,0,1,2,5,10,20,63)
PLACEBO_DRAWS=2000
EPISODE_GAP=5

def _inputs():
    rows,tq,_,_=_aligned()
    f=_augment(_download(rows[0]["date"],(pd.Timestamp(rows[-1]["date"])+pd.Timedelta(days=2)).date().isoformat()))
    dates=[pd.Timestamp(r["date"]) for r in rows[:-1]]
    base=[float(r["leverage"]) for r in rows[:-1]]
    caps=[min(base[i],cap(f,dates[i],"pulse125_slow2_ensemble125")) for i in range(len(dates))]
    px=pd.Series([float(r["close"]) for r in rows],index=pd.to_datetime([r["date"] for r in rows]))
    rv=(px.pct_change().rolling(20).std()*math.sqrt(252)).reindex(dates)
    return rows,tq,f,dates,base,caps,rv

def _returns(rows,tq,exposure,cost_bps=0.0,annual_financing=0.0):
    rr=[]; prev=None
    for i,ex in enumerate(exposure,1):
        q0,t0=weights_for_leverage(ex) if ex>0 else (0.,0.)
        q=q0*TARGET_INVESTED_FRACTION;t=t0*TARGET_INVESTED_FRACTION
        r=q*(float(rows[i]["close"])/float(rows[i-1]["close"])-1)+t*(tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1)
        if annual_financing>0:r-=max(0.,ex-1.)*annual_financing/252.
        if prev is not None and cost_bps>0:r-=abs(ex-prev)*cost_bps/10000.
        rr.append(r);prev=ex
    return rr

def _stats(rows,tq,base,caps,cost_bps=0.,fin=0.):
    br=_returns(rows,tq,base,cost_bps,fin);cr=_returns(rows,tq,caps,cost_bps,fin)
    b=_path_metrics(br);c=_path_metrics(cr)
    dl=[math.log1p(y)-math.log1p(x) for x,y in zip(br,cr)]
    return {"wealth_ratio":c["end_equity"]/b["end_equity"],"delta_log_wealth":sum(dl),
      "max_drawdown":c["max_drawdown"],"dd_improvement":c["max_drawdown"]-b["max_drawdown"],
      "intervention_sessions":sum(y<x-1e-12 for x,y in zip(base,caps))},dl,br,cr

def _shift(v,n,fill):
    if n==0:return list(v)
    if n>0:return [fill]*n+list(v[:-n])
    k=-n;return list(v[k:])+[fill]*k

def _episodes(base,caps):
    hit=[i for i,(b,c) in enumerate(zip(base,caps)) if c<b-1e-12]
    if not hit:return []
    groups=[[hit[0]]]
    for i in hit[1:]:
        if i-groups[-1][-1]<=EPISODE_GAP:groups[-1].append(i)
        else:groups.append([i])
    return [(g[0],g[-1]) for g in groups]

def _concentration(dl,eps,dates):
    by=[]
    for a,b in eps:
        v=sum(dl[a:b+1]);by.append({"start":str(dates[a].date()),"end":str(dates[b].date()),"span_sessions":b-a+1,"delta_log_wealth":v})
    by.sort(key=lambda x:x["delta_log_wealth"],reverse=True)
    pos=sum(max(0.,x) for x in dl) or 1.
    topdays=sorted(dl,reverse=True)
    return {"episode_count":len(eps),"episodes":by,
      "top_day_positive_share":max(0.,topdays[0])/pos if topdays else 0.,
      "top3_day_positive_share":sum(max(0.,x) for x in topdays[:3])/pos,
      "top5_day_positive_share":sum(max(0.,x) for x in topdays[:5])/pos,
      "top_episode_positive_share":max(0.,by[0]["delta_log_wealth"])/sum(max(0.,x["delta_log_wealth"]) for x in by) if by and sum(max(0.,x["delta_log_wealth"]) for x in by)>0 else 0.}

def _attribution(rows,base,caps):
    ar=drag=0.
    neg=pos=0.
    for i,(b,c) in enumerate(zip(base,caps),1):
        r=float(rows[i]["close"])/float(rows[i-1]["close"])-1
        a=(c-b)*r;d=-.5*(c*c-b*b)*r*r
        ar+=a;drag+=d
        if r<0:neg+=a
        else:pos+=a
    return {"arithmetic_first_order":ar,"reduced_drag_second_order":drag,
      "arithmetic_on_negative_days":neg,"arithmetic_on_positive_days":pos,
      "note":"Diagnostic Taylor attribution on QQQ close returns; exact portfolio log delta is reported separately."}

def _placebos(rows,tq,dates,base,caps,rv,observed):
    rng=random.Random(SEED);n=len(base);hit=[i for i,(b,c) in enumerate(zip(base,caps)) if c<b-1e-12]
    capvals=[caps[i] for i in hit];obs=observed["delta_log_wealth"]
    random_vals=[];matched_vals=[]
    valid=[i for i in range(n) if pd.notna(rv.iloc[i])]
    bins=pd.qcut(rv,10,labels=False,duplicates="drop")
    bybin={}
    for i in valid:bybin.setdefault(int(bins.iloc[i]),[]).append(i)
    hitbins=[int(bins.iloc[i]) for i in hit if pd.notna(bins.iloc[i])]
    for _ in range(PLACEBO_DRAWS):
        idx=rng.sample(range(n),len(hit));pc=list(base)
        for j,v in zip(idx,capvals):pc[j]=min(pc[j],v)
        s,_,_,_=_stats(rows,tq,base,pc);random_vals.append(s["delta_log_wealth"])
        chosen=[];used=set()
        for bb in hitbins:
            pool=[x for x in bybin.get(bb,[]) if x not in used]
            if not pool:continue
            x=rng.choice(pool);chosen.append(x);used.add(x)
        pm=list(base)
        for j,v in zip(chosen,capvals[:len(chosen)]):pm[j]=min(pm[j],v)
        s,_,_,_=_stats(rows,tq,base,pm);matched_vals.append(s["delta_log_wealth"])
    def summ(v):
        z=sorted(v);return {"draws":len(z),"p_one_sided":(1+sum(x>=obs for x in z))/(1+len(z)),
          "q50":z[len(z)//2],"q90":z[int(.9*(len(z)-1))],"q95":z[int(.95*(len(z)-1))]}
    return {"same_count_random":summ(random_vals),"rv_decile_matched":summ(matched_vals)}

def build(out=OUT):
    rows,tq,f,dates,base,caps,rv=_inputs()
    timing={}
    for lag in LAGS:
        lc=_shift(caps,lag,3.)
        lc=[min(b,c) for b,c in zip(base,lc)]
        timing[str(lag)]=_stats(rows,tq,base,lc)[0]
    shifts={}
    for sh in SHIFTS:
        sc=_shift(caps,sh,3.);sc=[min(b,c) for b,c in zip(base,sc)]
        shifts[str(sh)]=_stats(rows,tq,base,sc)[0]
    observed,dl,br,cr=_stats(rows,tq,base,caps)
    eps=_episodes(base,caps)
    costs={}
    for bps,fin in ((0,0.),(5,0.),(10,0.),(5,.05),(15,.075)):
        costs[f"cost{bps}bps_fin{fin:.3f}"]=_stats(rows,tq,base,caps,bps,fin)[0]
    result={"schema_version":1,"kind":"SPARSE_TAIL_REDTEAM_MEGABATCH_RESEARCH_ONLY",
      "promotion_allowed":False,"frozen_model_mutated":False,
      "timing_contract":{"lag_0":"Feature/state at completed close t controls exposure over t->t+1. This is the existing next-session causal convention, NOT same-bar protection.","lag_1":"One additional completed-session delay beyond the normal causal convention.","warning":"Claude's statement that lag-1 is necessarily the deployable version is not assumed; executability still requires verifying data publication timestamps and fill convention."},
      "observed":observed,"lag_ladder":timing,"mask_shift_profile":shifts,
      "attribution":_attribution(rows,base,caps),"concentration":_concentration(dl,eps,dates),
      "placebos":_placebos(rows,tq,dates,base,caps,rv,observed),"cost_financing_ladder":costs,
      "predeclared_falsification":{"lag1_negative":"delta_log_wealth at lag1 < 0","top3_days_gt_half":"top3 positive-day share > 0.50","top_episode_gt_half":"top episode positive share > 0.50","rv_matched_p_gt_0_20":"rv-decile matched placebo p > 0.20"},
      "claim_boundary":"Adversarial historical falsification only. No optimization or promotion. This batch prioritizes timing, concentration, placebo and cost diagnostics. GARCH/SPA, cross-market transfer and true LOCO re-selection remain separate expensive evidence layers."}
    Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))
