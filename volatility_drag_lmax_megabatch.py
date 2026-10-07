from __future__ import annotations
import json, math, random
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import BLOCKS, BOOTSTRAPS, SEED, _block_indices, _path_metrics, _quantiles

OUT=Path("research/volatility_drag_lmax_megabatch.json")
MODES=("baseline","kelly_half","kelly_quarter","gap15","gap20","gap25","vol60","hybrid_kelly_gap20","hybrid_vol_gap20")

def _features(rows,tq):
    dates=pd.to_datetime([r["date"] for r in rows])
    q=pd.Series([float(r["close"]) for r in rows],index=dates)
    t=pd.Series([float(tq[r["date"]]) for r in rows],index=dates)
    qr=q.pct_change(fill_method=None); tr=t.pct_change(fill_method=None)
    mu=qr.rolling(126,min_periods=63).mean()
    var=qr.rolling(126,min_periods=63).var()
    kelly=(mu/var.replace(0,float("nan"))).clip(lower=0,upper=3)
    rv20=qr.rolling(20,min_periods=20).std()*(252**0.5)
    worst63=tr.rolling(63,min_periods=21).min().abs()
    return pd.DataFrame({"kelly":kelly,"rv20":rv20,"worst63":worst63},index=dates)

def _cap(f,dt,mode):
    if mode=="baseline" or dt not in f.index:return 3.0
    k=float(f.at[dt,"kelly"]) if pd.notna(f.at[dt,"kelly"]) else 3.0
    rv=float(f.at[dt,"rv20"]) if pd.notna(f.at[dt,"rv20"]) else 0.0
    worst=float(f.at[dt,"worst63"]) if pd.notna(f.at[dt,"worst63"]) else 0.0
    kh=max(1.0,min(3.0,0.5*k)); kq=max(1.0,min(3.0,0.25*k))
    g15=max(1.0,min(3.0,0.15/max(worst,0.01)))
    g20=max(1.0,min(3.0,0.20/max(worst,0.01)))
    g25=max(1.0,min(3.0,0.25/max(worst,0.01)))
    vol=max(1.0,min(3.0,0.60/max(rv,0.01)))
    return {"kelly_half":kh,"kelly_quarter":kq,"gap15":g15,"gap20":g20,"gap25":g25,
            "vol60":vol,"hybrid_kelly_gap20":min(kh,g20),"hybrid_vol_gap20":min(vol,g20)}[mode]

def _daily(rows,tq,f,mode,static_cap=None):
    out=[];exps=[];hits=0
    for i in range(1,len(rows)):
        frozen=float(rows[i-1]["leverage"])
        cap=static_cap if static_cap is not None else _cap(f,pd.Timestamp(rows[i-1]["date"]),mode)
        exp=min(frozen,float(cap));exps.append(exp);hits+=int(exp<frozen-1e-12)
        q0,t0=weights_for_leverage(exp) if exp>0 else (0.,0.)
        q=q0*TARGET_INVESTED_FRACTION;t=t0*TARGET_INVESTED_FRACTION
        qr=float(rows[i]["close"])/float(rows[i-1]["close"])-1.
        tr=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1.
        out.append(q*qr+t*tr)
    return out,exps,hits

def _decomp(rets):
    s=pd.Series(rets,dtype=float); mu=float(s.mean()); var=float(s.var(ddof=0))
    exact=float((1+s).map(math.log).mean()) if (s>-1).all() else None
    approx=mu-0.5*var
    return {"mean_daily":mu,"variance_daily":var,"second_order_log_growth":approx,
            "exact_mean_log_growth":exact,"volatility_drag_half_variance":0.5*var}

def _paired(series):
    n=len(series["baseline"]);out={}
    for block in BLOCKS:
        rng=random.Random(SEED+12000+block);samples={m:[] for m in MODES}
        for _ in range(BOOTSTRAPS):
            idx=_block_indices(n,block,rng)
            for m in MODES:samples[m].append(_path_metrics([series[m][i] for i in idx]))
        b=samples["baseline"];bo={}
        for m in MODES:
            v=samples[m];dd=[x["max_drawdown"]-y["max_drawdown"] for x,y in zip(v,b)]
            wr=[x["end_equity"]/y["end_equity"] for x,y in zip(v,b)]
            bo[m]={"dd_improvement":_quantiles(dd),"wealth_ratio":_quantiles(wr),
                   "p_dd_improve":sum(x>0 for x in dd)/len(dd),
                   "p_preserve_85pct_wealth":sum(x>=.85 for x in wr)/len(wr)}
        out[str(block)]=bo
    return out

def build(out=OUT):
    rows,tq,_,_=_aligned();f=_features(rows,tq);series={};hist={};matched={}
    for m in MODES:
        rets,exps,hits=_daily(rows,tq,f,m);series[m]=rets;x=_path_metrics(rets)
        hist[m]={**x,"mean_effective_leverage":sum(exps)/len(exps),"intervention_sessions":hits,"growth_decomposition":_decomp(rets)}
        if m!="baseline":
            static_cap=sum(exps)/len(exps);sr,sexp,_=_daily(rows,tq,f,m,static_cap=static_cap);sx=_path_metrics(sr)
            matched[m]={"static_cap":static_cap,"dynamic_wealth_ratio_vs_static_matched":x["end_equity"]/sx["end_equity"],
                        "dynamic_maxdd_improvement_vs_static_matched":x["max_drawdown"]-sx["max_drawdown"],
                        "static_matched":sx}
    b=hist["baseline"]
    gates={}
    for m in MODES[1:]:
        x=hist[m];gates[m]={"wealth_ratio_vs_baseline":x["end_equity"]/b["end_equity"],
                            "maxdd_improvement_vs_baseline":x["max_drawdown"]-b["max_drawdown"],
                            "continue_gate":(x["end_equity"]/b["end_equity"]>=.85 and x["max_drawdown"]-b["max_drawdown"]>=.03)}
    result={"schema_version":1,"kind":"VOLATILITY_DRAG_GAP_RISK_LMAX_MEGABATCH_RESEARCH_ONLY",
      "frozen_model":"StockLens 8.0","frozen_model_mutated":False,"promotion_allowed":False,
      "modes":list(MODES),"historical_path":hist,"static_matched_exposure":matched,"continuation_gates":gates,
      "paired_cluster_bootstrap":_paired(series),
      "mechanism_contract":{"kelly":"126-session prior-completed QQQ mean/variance; half and quarter Kelly bounded 1x..3x",
       "gap":"prior 63-session worst observed TQQQ daily loss; fixed 15/20/25% one-day loss budgets; bounded 1x..3x",
       "vol":"60% annualized volatility target from prior 20 completed QQQ sessions; bounded 1x..3x",
       "hybrids":"minimum of independently specified caps; no fitted weights"},
      "anti_overfit_contract":["All schedules fixed before outcome evaluation","No threshold optimizer","Static matched-exposure benchmark for every dynamic rule","Paired block bootstrap uses identical sampled paths","Frozen 8.0 can only be de-risked, never levered above its decision","No automatic winner selection or promotion"],
      "continuation_rule":"Continue a family only if historical wealth >=85% of baseline AND MaxDD improves >=3 percentage points; bootstrap is supporting falsification evidence, not a promotion rule.",
      "claim_boundary":"Research-only mechanism falsification. Rolling estimates and historical tail observations do not forecast future returns or guarantee drawdown control."}
    Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))
