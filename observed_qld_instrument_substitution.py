"""SL9-015: preregistered QLD physical-share substitution, 8.0 unchanged.

Only observed Yahoo adjusted historical QQQ/QLD/TQQQ OPEN/CLOSE, never
synthetic 2x/3x series. Historic intraday fills, fund tracking/costs and
broker eligibility are *not* proven. No orders or automatic promotion.
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
import hashlib
import json
import math

from observed_etf_two_question_audit import load, _metrics, SPLITS, START_CAPITAL
from observed_etf_four_challengers_batch import simulate as reference
from stocklens.core import TARGET_INVESTED_FRACTION, weights_for_leverage

SYMS=("QQQ","QLD","TQQQ")
SOURCE=Path("research/private/observed_qld_2010_2026.json")
OUT=Path("research/results/qld_instrument_substitution.json")
REPORT=Path("research/reports/qld_instrument_substitution.md")
SCOPE_SHA="bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129"
MODES=("frozen","qld_only_at_2x","qld_at_1_25x_and_2x")
LAGS=(0,1)
SLIPPAGES=(10.,20.)
FEES_BPS=2.


def normalize_price_frame(frame, expected_dates):
    import pandas as pd
    if frame is None or frame.empty:
        raise ValueError("QLD_NO_OBSERVED_BARS")
    if isinstance(frame.columns,pd.MultiIndex):
        try:
            oo,cc=frame["Open"]["QLD"],frame["Close"]["QLD"]
        except KeyError as exc:
            raise ValueError("QLD_MISSING_OBSERVED_OPEN_CLOSE") from exc
    else:
        try:
            oo,cc=frame["Open"],frame["Close"]
        except KeyError as exc:
            raise ValueError("QLD_MISSING_OBSERVED_OPEN_CLOSE") from exc
    days=[pd.Timestamp(x).date().isoformat() for x in frame.index]
    if days!=sorted(set(days)):
        raise ValueError("QLD_DUPLICATE_OR_NONMONOTONE_BARS")
    records={}
    for i,day in enumerate(days):
        a,b=float(oo.iloc[i]),float(cc.iloc[i])
        if not all(math.isfinite(v) and v>0 for v in (a,b)):
            raise ValueError("QLD_NONFINITE_OR_ZERO_BAR")
        records[day]={"date":day,"open":a,"close":b}
    missing=[d for d in expected_dates if d not in records]
    if missing:
        raise ValueError("QLD_MISSING_OBSERVED_TRADING_DAYS:"+str(len(missing)))
    return [records[d] for d in expected_dates]


def download_qld(rows):
    import yfinance as yf
    dates=[r["date"] for r in rows]
    end=(date.fromisoformat(dates[-1])+timedelta(days=1)).isoformat()
    f=yf.download("QLD",start=dates[0],end=end,interval="1d",
                  auto_adjust=True,actions=False,progress=False,threads=False)
    return normalize_price_frame(f,dates)


def freeze_source(rows, bars):
    ds=[r["date"] for r in rows]
    if len(bars)!=len(rows) or [b["date"] for b in bars]!=ds:
        raise ValueError("QLD_SOURCE_CALENDAR_MISMATCH")
    return {"schema_version":1,"instrument":"QLD",
            "source_url":"https://finance.yahoo.com/quote/QLD/history/",
            "observed_adjusted_daily_open_close":True,
            "baseline_sha256":SCOPE_SHA,
            "first_seen_proven":False,
            "third_party_price_adjustments_audited":False,
            "bars":bars}


def fingerprint_bars(source):
    if (source.get("schema_version")!=1 or source.get("instrument")!="QLD"
        or source.get("observed_adjusted_daily_open_close") is not True
        or source.get("baseline_sha256")!=SCOPE_SHA
        or source.get("first_seen_proven") is not False
        or source.get("third_party_price_adjustments_audited") is not False):
        raise ValueError("QLD_UNVERIFIED_SOURCE_CONTRACT")
    bars=source.get("bars")
    if not isinstance(bars,list) or not bars:
        raise ValueError("QLD_EMPTY_SOURCE")
    ds=[x.get("date") for x in bars]
    if ds!=sorted(set(ds)):
        raise ValueError("QLD_SOURCE_NONMONOTONE")
    for r in bars:
        if not all(type(r.get(k)) in (int,float) and math.isfinite(r[k]) and r[k]>0
                   for k in ("open","close")):
            raise ValueError("QLD_INVALID_SOURCE_PRICES")
    return hashlib.sha256(json.dumps(bars,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def target_weights(lev,mode):
    if mode not in MODES or lev not in (0,1.25,2,3):
        raise ValueError("QLD_NONREGISTERED_MODEL")
    if lev==0:
        return {"QQQ":0.,"QLD":0.,"TQQQ":0.}
    if mode!="frozen" and lev==2:
        return {"QQQ":0.,"QLD":TARGET_INVESTED_FRACTION,"TQQQ":0.}
    if mode=="qld_at_1_25x_and_2x" and lev==1.25:
        return {"QQQ":.75*TARGET_INVESTED_FRACTION,
                "QLD":.25*TARGET_INVESTED_FRACTION,"TQQQ":0.}
    q,t=weights_for_leverage(lev)
    return {"QQQ":q*TARGET_INVESTED_FRACTION,"QLD":0.,
            "TQQQ":t*TARGET_INVESTED_FRACTION}


def execute(p, prices, weights, fee_bps, slip_bps):
    if set(weights)!=set(SYMS) or sum(weights.values())>1.00000000001:
        raise ValueError("QLD_INVALID_TARGET")
    equity=p["cash"]+sum(p["shares"][s]*prices[s]["open"] for s in SYMS)
    if equity<=0: raise ValueError("QLD_INVALID_NAV")
    targets={s:math.floor(equity*weights[s]/prices[s]["open"]) for s in SYMS}
    for s in SYMS:
        q=p["shares"][s]-targets[s]
        if q>0:
            price=prices[s]["open"]*(1-slip_bps/1e4)
            p["cash"]+=q*price*(1-fee_bps/1e4)
            p["shares"][s]-=q
            p["trades"]+=1
    for s in SYMS:
        missing=targets[s]-p["shares"][s]
        if missing>0:
            unit=prices[s]["open"]*(1+slip_bps/1e4)*(1+fee_bps/1e4)
            q=min(missing,math.floor(max(0.,p["cash"])/unit))
            if q>0:
                p["cash"]-=q*unit
                p["shares"][s]+=q
                p["trades"]+=1
    if p["cash"]<-1e-5: raise ValueError("QLD_NEGATIVE_CASH")


def simulate(rows,source,mode="frozen",lag=0,slip_bps=10.):
    if mode not in MODES or lag not in LAGS or slip_bps not in SLIPPAGES:
        raise ValueError("QLD_HYPOTHESIS_NOT_REGISTERED")
    fingerprint_bars(source)
    bars=source["bars"]
    if len(bars)!=len(rows) or [b["date"] for b in bars]!=[r["date"] for r in rows]:
        raise ValueError("QLD_DATE_MISMATCH")
    p={"cash":START_CAPITAL,"shares":{s:0 for s in SYMS},"trades":0}
    old=None
    navs=[]
    times={}
    for i,r in enumerate(rows):
        if r.get("signal","")>=r["date"] or r.get("l") not in (0,1.25,2,3):
            raise ValueError("QLD_INVALID_FROZEN_PRIOR_SIGNAL")
        j=i-lag
        level=rows[j]["l"] if j>=0 else 0
        times[level]=times.get(level,0)+1
        weights=target_weights(level,mode)
        prices={"QQQ":{"open":r["qo"],"close":r["qc"]},
                "QLD":{"open":bars[i]["open"],"close":bars[i]["close"]},
                "TQQQ":{"open":r["to"],"close":r["tc"]}}
        if old is None or old!=level:
            execute(p,prices,weights,FEES_BPS,slip_bps)
        nav=p["cash"]+sum(p["shares"][s]*prices[s]["close"] for s in SYMS)
        if not math.isfinite(nav) or nav<=0 or p["cash"]<-1e-5:
            raise ValueError("QLD_BAD_LEDGER_NAV")
        navs.append(nav)
        old=level
    return {"navs":navs,"dates":[r["date"] for r in rows],
            "stats":_metrics(navs,[r["date"] for r in rows]),
            "trades":p["trades"],"exposure_days":times}


def era(path,a,b):
    indices=[i for i,d in enumerate(path["dates"]) if a<=d<=b]
    if not indices: raise ValueError("QLD_MISSING_ERA")
    first,last=indices[0],indices[-1]
    initial=START_CAPITAL if first==0 else path["navs"][first-1]
    return _metrics(path["navs"][first:last+1],path["dates"][first:last+1],first=initial)


def evaluate(raw,source):
    rows=raw["daily"]
    if raw.get("snapshot_sha256")!=SCOPE_SHA:raise ValueError("QLD_BASELINE_SOURCE_CHANGED")
    sha=fingerprint_bars(source)
    allruns={(m,l,s):simulate(rows,source,m,l,s)
             for m in MODES for l in LAGS for s in SLIPPAGES}
    for l in LAGS:
        for s in SLIPPAGES:
            x=allruns[("frozen",l,s)]["navs"]
            ref=reference(rows,mode="frozen",lag=l,slippage_bps=s)["navs"]
            if len(x)!=len(ref) or any(abs(a-b)>1e-5 for a,b in zip(x,ref)):
                raise ValueError("QLD_FROZEN_DAILY_LEDGER_PARITY_BROKEN")
    main=allruns[("frozen",0,10.)]
    cases={}
    for mode in MODES[1:]:
        test=allruns[(mode,0,10.)]
        stress=[]
        for lag in LAGS:
            for slip in SLIPPAGES:
                a=allruns[(mode,lag,slip)]["stats"]
                b=allruns[("frozen",lag,slip)]["stats"]
                gain=100*(a["cagr"]-b["cagr"])
                dd=100*(a["max_drawdown"]-b["max_drawdown"])
                stress.append({"lag":lag,"slippage_bps":slip,
                               "cagr_gain_pp":gain,"maxdd_gain_pp":dd,
                               "research_continue_only":gain>=.5 and dd>=-1.})
        cases[mode]={"cagr":test["stats"]["cagr"],
          "maxdd":test["stats"]["max_drawdown"],
          "cagr_gain_pp":100*(test["stats"]["cagr"]-main["stats"]["cagr"]),
          "maxdd_gain_pp":100*(test["stats"]["max_drawdown"]-main["stats"]["max_drawdown"]),
          "trades":test["trades"],
          "stress":stress,"continuation_passes":sum(x["research_continue_only"] for x in stress),
          "requires_4_passes":True,
          "eras":{name:{"cagr_gain_pp":100*(era(test,a,b)["cagr"]-era(main,a,b)["cagr"]),
                        "maxdd_gain_pp":100*(era(test,a,b)["max_drawdown"]-era(main,a,b)["max_drawdown"])}
                  for name,(a,b) in SPLITS.items()}}
    return {"schema_version":1,"research_family":"QLD_REAL_INSTRUMENT_SUBSTITUTION",
      "source_sha256":sha,"baseline_market_sha256":raw["snapshot_sha256"],
      "period":raw["period"],"actual_observed_qld_sessions":len(source["bars"]),
      "baseline":main["stats"],"baseline_trades":main["trades"],
      "exposure_sessions_by_frozen_level":main["exposure_days"],
      "two_fixed_modes":cases,
      "parity_all_four_fee_lag_cases":True,
      "source_price_adjustment_independently_audited":False,
      "vendor_historical_first_seen_proven":False,
      "observed_real_qqq_qld_tqqq":True,"synthetic_tqqq_returns_used":False,
      "reused_historical_sample_not_pristine_oos":True,
      "actual_broker_0931_fills":False,"frozen_8_0_changed":False,
      "capital_deployment_authorized":False,"automatic_promotion":False}


def build():
    raw=load()
    bars=download_qld(raw["daily"])
    source=freeze_source(raw["daily"],bars)
    SOURCE.parent.mkdir(parents=True,exist_ok=True)
    SOURCE.write_text(json.dumps(source,sort_keys=True,separators=(",",":"))+"\n")
    result=evaluate(raw,source)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    lines=["# SL9-015 — observed physical QLD instrument substitution",
        "", "Two fixed research families, preregistered. Frozen decisions do not change.",
        "Observed QQQ/QLD/TQQQ Yahoo-adjusted daily open proxy, not broker executions.",
        "All 0/1 lag and 10/20bps modeled slippage NAVs match frozen baseline.",
        "Full 2010–2026 is reused historical research, NOT untouched OOS.",
        "","| Variant | CAGR | MaxDD | CAGR delta pp | MaxDD delta pp | Gate |",
        "|---|---:|---:|---:|---:|---:|"]
    a=result["baseline"]
    lines.append(f'| frozen | {a["cagr"]:.3%} | {a["max_drawdown"]:.3%} | 0 | 0 | baseline |')
    for k,v in result["two_fixed_modes"].items():
        lines.append(f'| {k} | {v["cagr"]:.3%} | {v["maxdd"]:.3%} | {v["cagr_gain_pp"]:+.3f} | {v["maxdd_gain_pp"]:+.3f} | {v["continuation_passes"]}/4 |')
    lines += ["","Continuation threshold in every stress case: >=0.5 percentage-point",
       "CAGR gain and no more than 1pp MaxDD deterioration; NOT permission to deploy.",
       "No source provider adjustment cross-audit or actual market depth/venue fills.",
       "No synthetic QLD or TQQQ, no optimized weights, no signal changes."]
    REPORT.write_text("\n".join(lines)+"\n")
    summary={"period":result["period"],"qld_sessions":result["actual_observed_qld_sessions"],
      "qld_source_sha256":result["source_sha256"],
      "base":{k:a[k] for k in ("cagr","max_drawdown")},
      "challengers":{k:{q:v[q] for q in ("cagr","maxdd","cagr_gain_pp",
                        "maxdd_gain_pp","continuation_passes")}
                     for k,v in result["two_fixed_modes"].items()},
      "no_promotion":True}
    print("STOCKLENS_QLD_RESULT="+json.dumps(summary,sort_keys=True))
    return result


if __name__=="__main__":
    build()
