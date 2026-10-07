from __future__ import annotations
import json, random
from pathlib import Path
from statistics import median
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
OUT=Path("research/orthogonal_tail_validation.json")
SEED=8009
BLOCKS=(5,21,63)
BOOTSTRAPS=300
GAPS=(-0.05,-0.10,-0.15,-0.20)
GAP_OFFSETS=(0,1,3,5)
CONTRIBUTIONS=(0.0,3500.0)
# Fixed before outcome evaluation. These are intentionally coarse lower-risk reference
# frontiers, not candidate selection. They answer whether tail risk is primarily a
# consequence of the highest frozen exposure states.
EXPOSURE_CAPS=(3.0,2.75,2.5,2.25,2.0,1.75,1.5,1.25,1.0,0.75,0.5)

def _daily(rows,tq,cap=3.0):
    out=[]
    for i in range(1,len(rows)):
        frozen=float(rows[i-1]["leverage"]);exp=min(frozen,cap)
        q0,t0=weights_for_leverage(exp) if exp>0 else (0.0,0.0)
        q=q0*TARGET_INVESTED_FRACTION;t=t0*TARGET_INVESTED_FRACTION
        qr=float(rows[i]["close"])/float(rows[i-1]["close"])-1.0;tr=tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1.0
        out.append({"date":rows[i]["date"],"ret":q*qr+t*tr,"leverage":exp,"frozen_leverage":frozen})
    return out

def _path_metrics(rets,start=100000.0,monthly=0.0):
    nav=peak=start;dd=0.0;months=0
    for i,r in enumerate(rets):
        nav*=1.0+r
        if monthly and i and i%21==0:nav+=monthly;months+=1
        peak=max(peak,nav);dd=min(dd,nav/peak-1.0)
    contributed=start+months*monthly
    return {"end_equity":nav,"max_drawdown":dd,"total_contributed":contributed,"wealth_multiple_on_contributed":nav/contributed if contributed else None}

def _block_indices(n,block,rng):
    out=[]
    while len(out)<n:
        start=rng.randrange(0,max(1,n-block+1));out.extend(range(start,min(n,start+block)))
    return out[:n]

def _block_sample(rets,block,n,rng):
    if not rets:return []
    out=[]
    while len(out)<n:
        start=rng.randrange(0,max(1,len(rets)-block+1))
        out.extend(rets[start:start+block])
    return out[:n]

def _quantiles(xs):
    ys=sorted(xs)
    def q(p):
        if not ys:return None
        return ys[min(len(ys)-1,max(0,int(round((len(ys)-1)*p))))]
    return {"p01":q(.01),"p05":q(.05),"p50":q(.50),"p95":q(.95),"p99":q(.99)}

def _cluster_bootstrap(rets):
    rng=random.Random(SEED);out={}
    for block in BLOCKS:
        dds=[];ends=[]
        for _ in range(BOOTSTRAPS):
            m=_path_metrics(_block_sample(rets,block,len(rets),rng));dds.append(m["max_drawdown"]);ends.append(m["end_equity"])
        out[str(block)]={"samples":BOOTSTRAPS,"max_drawdown_quantiles":_quantiles(dds),"end_equity_quantiles":_quantiles(ends),
          "probability_drawdown_below_50pct":sum(x<=-.50 for x in dds)/len(dds),"probability_drawdown_below_60pct":sum(x<=-.60 for x in dds)/len(dds)}
    return out

def _historical_cap_frontier(daily_by_cap):
    base=_path_metrics([x["ret"] for x in daily_by_cap[3.0]])
    out={}
    for cap,xs in daily_by_cap.items():
        m=_path_metrics([x["ret"] for x in xs])
        avg=sum(x["leverage"] for x in xs)/len(xs)
        out[str(cap)]={**m,"average_realized_leverage":avg,
          "terminal_wealth_ratio_vs_3x":m["end_equity"]/base["end_equity"],
          "maxdd_improvement_vs_3x":m["max_drawdown"]-base["max_drawdown"],
          "passes_predeclared_85pct_wealth_and_3pp_dd":m["end_equity"]>=.85*base["end_equity"] and m["max_drawdown"]-base["max_drawdown"]>=.03}
    return out

def _paired_cap_frontier(series_by_cap):
    """Use identical sampled block indices for every cap so comparisons are paired, not Monte-Carlo noise."""
    n=len(next(iter(series_by_cap.values())));out={}
    for block in BLOCKS:
        rng=random.Random(SEED+block);samples={str(c):[] for c in EXPOSURE_CAPS}
        for _ in range(BOOTSTRAPS):
            idx=_block_indices(n,block,rng)
            for cap in EXPOSURE_CAPS:
                m=_path_metrics([series_by_cap[cap][i] for i in idx])
                samples[str(cap)].append(m)
        base=samples["3.0"]
        block_out={}
        for cap in EXPOSURE_CAPS:
            vals=samples[str(cap)]
            dd_delta=[v["max_drawdown"]-b["max_drawdown"] for v,b in zip(vals,base)]
            wealth_ratio=[v["end_equity"]/b["end_equity"] if b["end_equity"] else None for v,b in zip(vals,base)]
            block_out[str(cap)]={
              "samples":BOOTSTRAPS,
              "max_drawdown_quantiles":_quantiles([v["max_drawdown"] for v in vals]),
              "end_equity_quantiles":_quantiles([v["end_equity"] for v in vals]),
              "paired_maxdd_improvement_quantiles":_quantiles(dd_delta),
              "paired_terminal_wealth_ratio_quantiles":_quantiles([x for x in wealth_ratio if x is not None]),
              "probability_drawdown_below_50pct":sum(v["max_drawdown"]<=-.50 for v in vals)/len(vals),
              "probability_drawdown_below_60pct":sum(v["max_drawdown"]<=-.60 for v in vals)/len(vals),
              "probability_paired_dd_improvement":sum(x>0 for x in dd_delta)/len(dd_delta),
              "probability_preserve_at_least_80pct_terminal_wealth":sum(x>=.80 for x in wealth_ratio if x is not None)/len(wealth_ratio)}
        out[str(block)]=block_out
    return out

def _gap_injection(daily):
    rets=[x["ret"] for x in daily];ranked=sorted(range(len(daily)),key=lambda i:daily[i]["leverage"],reverse=True);anchors=[]
    for i in ranked:
        if all(abs(i-j)>21 for j in anchors):anchors.append(i)
        if len(anchors)>=8:break
    out=[]
    for gap in GAPS:
        for off in GAP_OFFSETS:
            vals=[]
            for a in anchors:
                j=min(len(rets)-1,a+off);x=list(rets);x[j]=(1+x[j])*(1+gap)-1;vals.append(_path_metrics(x)["max_drawdown"])
            out.append({"synthetic_gap":gap,"offset_sessions":off,"anchors":len(vals),"median_max_drawdown":median(vals) if vals else None,"worst_max_drawdown":min(vals) if vals else None})
    return out

def _sequence_contribution_stress(rets):
    step=max(1,len(rets)//24);offsets=tuple(range(0,len(rets),step));out=[]
    for monthly in CONTRIBUTIONS:
        vals=[]
        for k in offsets:vals.append(_path_metrics(rets[k:]+rets[:k],monthly=monthly))
        out.append({"monthly_contribution":monthly,"rotations":len(vals),"end_equity_quantiles":_quantiles([v["end_equity"] for v in vals]),
          "max_drawdown_quantiles":_quantiles([v["max_drawdown"] for v in vals]),"wealth_multiple_quantiles":_quantiles([v["wealth_multiple_on_contributed"] for v in vals])})
    return out

def build(out=OUT):
    rows,tq,_,_=_aligned()
    daily_by_cap={cap:_daily(rows,tq,cap) for cap in EXPOSURE_CAPS}
    daily=daily_by_cap[3.0];rets=[x["ret"] for x in daily]
    series_by_cap={cap:[x["ret"] for x in xs] for cap,xs in daily_by_cap.items()}
    result={"schema_version":2,"kind":"ORTHOGONAL_TAIL_VALIDATION_RESEARCH_ONLY","frozen_model":"StockLens 8.0","frozen_model_mutated":False,
      "promotion_allowed":False,
      "selection_policy":"No parameter selection or challenger promotion. Fixed coarse stresses and fixed 3.0/2.5/2.0 exposure-cap reference frontier only.",
      "baseline":_path_metrics(rets),
      "historical_exposure_cap_frontier":_historical_cap_frontier(daily_by_cap),
      "predeclared_simple_cap_rule":"Continue only if a lower cap preserves >=85% terminal wealth and improves MaxDD by >=3 percentage points; bootstrap evidence is paired and diagnostic.",
      "cluster_preserving_block_bootstrap":_cluster_bootstrap(rets),
      "paired_exposure_cap_tail_frontier":_paired_cap_frontier(series_by_cap),
      "synthetic_gap_injection":_gap_injection(daily),
      "sequence_and_contribution_timing":_sequence_contribution_stress(rets),
      "claim_boundary":"Falsification and path-risk evidence only. Bootstrap is not a market forecast; synthetic gaps are counterfactual shocks; rotations test sequence sensitivity. Exposure caps are coarse diagnostic reference frontiers, not tuned challengers or promotion candidates."}
    Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))
