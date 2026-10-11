"""SL9-019 two fixed nonduplicative inverse-variance/downside-risk candidates.

All outcomes from observed real QQQ/TQQQ daily open/close and frozen 8.0
prior-session levels. Reused historical sample, not pristine OOS or alpha.
No synthetic leveraged ETF, order placement, margin or automatic promotion.
"""
from __future__ import annotations
from pathlib import Path
from statistics import stdev
import json
import math

from observed_etf_two_question_audit import load, _metrics, _prices, START_CAPITAL, SPLITS
from observed_etf_four_challengers_batch import simulate as frozen_reference
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from tradable_tqqq_execution_comparison import _mark, _rebalance

MODES=("frozen","inverse_variance20","downside_semivariance20")
LAGS=(0,1)
SLIPS=(10.,20.)
FEE_BPS=2.
TARGET_ANNUAL_QQQ_VOL=.60
MIN_EXPOSURE=1.
MAX_EXPOSURE=3.
WEIGHT_BAND=.005
SOURCE_SHA="bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129"
OUT=Path("research/results/inverse_variance_downside_drag_observed_etfs.json")
REPORT=Path("research/reports/inverse_variance_downside_drag_observed_etfs.md")


def finished_features(rows):
    """At index t, feature uses only completed QQQ closes <= t."""
    q=[float(row["qc"]) for row in rows]
    for x in q:
        if not math.isfinite(x) or x <= 0:
            raise ValueError("DRAG_INVALID_REAL_QQQ_BAR")
    rv=[None]*len(q)
    negative=[None]*len(q)
    for t in range(20,len(q)):
        ret=[math.log(q[j]/q[j-1]) for j in range(t-19,t+1)]
        rv[t]=stdev(ret)*math.sqrt(252.)
        negative[t]=math.sqrt(2.*252.*sum(min(v,0.)**2 for v in ret)/20.)
    return rv,negative


def cap(mode,sigma,downside):
    if mode not in MODES:
        raise ValueError("DRAG_UNREGISTERED_MODE")
    if mode=="frozen" or sigma is None:
        return MAX_EXPOSURE
    if not math.isfinite(sigma) or sigma<0:
        raise ValueError("DRAG_INVALID_SIGMA")
    if mode=="downside_semivariance20":
        if downside is None or not math.isfinite(downside) or downside<0:
            raise ValueError("DRAG_INVALID_DOWNSIDE_SIGMA")
        used=downside
        cap_raw=TARGET_ANNUAL_QQQ_VOL/max(used,1e-8)
    else:
        cap_raw=(TARGET_ANNUAL_QQQ_VOL/max(sigma,1e-8))**2
    return min(MAX_EXPOSURE,max(MIN_EXPOSURE,cap_raw))


def simulate(rows,*,mode="frozen",lag=0,slip=10.):
    if mode not in MODES or lag not in LAGS or slip not in SLIPS:
        raise ValueError("DRAG_UNREGISTERED_EXPERIMENT_OR_STRESS")
    if len(rows)<3 or [r["date"] for r in rows] != sorted(set(r["date"] for r in rows)):
        raise ValueError("DRAG_DATE_ORDER_INVALID")
    rv,sem=finished_features(rows)
    p={"cash":START_CAPITAL,"shares":{"QQQ":0,"TQQQ":0},
       "fees":0.,"slippage":0.,"trades":0,"turnover_notional":0.}
    navs,dates=[],[]
    target_prev=None
    interventions=0
    skipped=0
    for i,row in enumerate(rows):
        if row.get("l") not in (0,1.25,2,3) or row.get("signal","") >= row["date"]:
            raise ValueError("DRAG_FUTURE_OR_INVALID_FROZEN_DECISION")
        if not all(type(row.get(k)) in (float,int) and math.isfinite(row[k]) and row[k]>0
                   for k in ("qo","qc","to","tc")):
            raise ValueError("DRAG_INVALID_OBSERVED_OPEN_OR_CLOSE")
        # lag is extra delay after previous completed day's end, not a
        # retroactive change to the frozen 8.0 decision already as-of.
        past=i-1-lag
        allowed=cap(mode,rv[past],sem[past]) if past>=0 else MAX_EXPOSURE
        level=min(float(row["l"]),allowed)
        if level<float(row["l"])-1e-9:
            interventions+=1
        q,t=weights_for_leverage(level) if level else (0.,0.)
        weights={"QQQ":q*TARGET_INVESTED_FRACTION,"TQQQ":t*TARGET_INVESTED_FRACTION}
        prices=_prices(row)
        rebalance=target_prev is None or abs(level-target_prev)>1e-9
        if rebalance and target_prev is not None and mode!="frozen":
            equity=_mark(p,prices,"open")
            if equity<=0:raise ValueError("DRAG_INVALID_PRETRADE_NAV")
            mismatch=max(abs(p["shares"][s]*prices[s]["open"]/equity-weights[s])
                         for s in ("QQQ","TQQQ"))
            if mismatch<=WEIGHT_BAND:
                rebalance=False
                skipped+=1
        if rebalance:
            _rebalance(p,prices,weights,FEE_BPS,slip)
        nav=_mark(p,prices,"close")
        if not math.isfinite(nav) or nav<=0 or p["cash"]<-1e-5:
            raise ValueError("DRAG_INVALID_ACCOUNT")
        navs.append(nav)
        dates.append(row["date"])
        target_prev=level
    return {"navs":navs,"dates":dates,"stats":_metrics(navs,dates),
            "trades":p["trades"],"intervention_sessions":interventions,
            "skipped_rebalances_50bps":skipped}


def era(path,start,end):
    ix=[i for i,d in enumerate(path["dates"]) if start<=d<=end]
    if not ix:raise ValueError("DRAG_MISSING_SPLIT")
    a,b=ix[0],ix[-1]
    initial=START_CAPITAL if a==0 else path["navs"][a-1]
    return _metrics(path["navs"][a:b+1],path["dates"][a:b+1],first=initial)


def evaluate(raw):
    if raw.get("snapshot_sha256")!=SOURCE_SHA:
        raise ValueError("DRAG_UNVERIFIED_QQQ_TQQQ_SOURCE")
    rows=raw["daily"]
    runs={(mode,lag,slip):simulate(rows,mode=mode,lag=lag,slip=slip)
          for mode in MODES for lag in LAGS for slip in SLIPS}
    for lag in LAGS:
        for slip in SLIPS:
            a=runs[("frozen",lag,slip)]["navs"]
            b=frozen_reference(rows,mode="frozen",lag=0,slippage_bps=slip)["navs"]
            if len(a)!=len(b) or any(abs(x-y)>1e-5 for x,y in zip(a,b)):
                raise ValueError("DRAG_FROZEN_DAILY_NAV_PARITY_FAILED")
    baseline=runs[("frozen",0,10.)]["stats"]
    challengers={}
    for mode in MODES[1:]:
        cases=[]
        for lag in LAGS:
            for slip in SLIPS:
                x=runs[(mode,lag,slip)]["stats"]
                b=runs[("frozen",lag,slip)]["stats"]
                dd=100*(x["max_drawdown"]-b["max_drawdown"])
                cg=100*(x["cagr"]-b["cagr"])
                cases.append({"lag":lag,"slip_bps":slip,"cagr_delta_pp":cg,
                              "maxdd_gain_pp":dd,"passes":dd>=3 and cg>=-1.5})
        one=runs[(mode,0,10.)]
        challengers[mode]={"cagr":one["stats"]["cagr"],
             "maxdd":one["stats"]["max_drawdown"],
             "cagr_delta_pp":100*(one["stats"]["cagr"]-baseline["cagr"]),
             "maxdd_gain_pp":100*(one["stats"]["max_drawdown"]-baseline["max_drawdown"]),
             "trades":one["trades"],"intervention_sessions":one["intervention_sessions"],
             "skipped_rebalances_50bps":one["skipped_rebalances_50bps"],
             "lag_cost_cases":cases,"passes":sum(q["passes"] for q in cases),
             "required":4,
             "era_changes":{name:{"cagr_delta_pp":100*(era(one,a,b)["cagr"]-era(runs[("frozen",0,10.)],a,b)["cagr"]),
                            "maxdd_gain_pp":100*(era(one,a,b)["max_drawdown"]-era(runs[("frozen",0,10.)],a,b)["max_drawdown"])}
                            for name,(a,b) in SPLITS.items()}}
    return {"schema_version":1,"kind":"SL9_019_ACTUAL_QQQ_TQQQ_INVERSE_VARIANCE_DOWNSIDE",
            "sessions":len(rows),"source_sha256":SOURCE_SHA,
            "baseline":baseline,"challengers":challengers,
            "frozen_day_by_day_parity":True,
            "reused_history_not_independent_oos":True,
            "no_synthetic_TQQQ_returns":True,
            "qqq_sigma_completed_prior_sessions_only":True,
            "market_open_proxy_not_observed_broker_fills":True,
            "selection_corrected_alpha_proven":False,
            "live_broker_orders_authorized":False,
            "frozen_stocklens_8_changed":False,"automatic_promotion":False}


def build():
    result=evaluate(load())
    OUT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    base=result["baseline"]
    lines=["# SL9-019 inverse-variance and downside-only volatility scaling",
    "", "Fixed two candidates on historically reused real observed QQQ/TQQQ.",
    "Modelled physical shares at Yahoo daily OPEN, 2bps fees/side, 10/20bps",
    "slippage; exact 0/1 extra volatility feature lag. NOT broker NBBO.",
    "","| Model | CAGR | MaxDD | CAGR delta pp | MaxDD gain pp | Trades | 4-case gate |",
    "|---|---:|---:|---:|---:|---:|---|",
    f'| frozen 8.0 | {base["cagr"]:.3%} | {base["max_drawdown"]:.3%} | 0 | 0 | - | Reference |']
    for name,v in result["challengers"].items():
        lines.append(f'| {name} | {v["cagr"]:.3%} | {v["maxdd"]:.3%} | '+ 
                     f'{v["cagr_delta_pp"]:+.3f} | {v["maxdd_gain_pp"]:+.3f} | '+
                     f'{v["trades"]} | {v["passes"]}/4 |')
    lines+=["","No frozen 8.0 modification, no synthetic TQQQ, no selection-corrected",
            "alpha or new untouched OOS, no broker execution authorization."]
    REPORT.write_text("\n".join(lines)+"\n")
    print("STOCKLENS_INVERSE_VARIANCE_RESULTS="+json.dumps({
        "base":{k:base[k] for k in ("cagr","max_drawdown")},
        "candidates":{k:{x:v[x] for x in ("cagr","maxdd","cagr_delta_pp",
                                "maxdd_gain_pp","passes","trades")}
                      for k,v in result["challengers"].items()},
        "promotion":False},sort_keys=True))
    return result


if __name__=="__main__":
    build()
