from __future__ import annotations
import json,math
from pathlib import Path
from stocklens.data import load_qqq_history
from stocklens.core import replay_levels,compute_features,next_level,defense_active,LEVEL_LEVERAGE
from backtest_engine import run_backtest
from backtest_contract import FrozenExposureReplayAdapter,stocklens_8_request

OUT=Path("research/yahoo_long_history.json")

def _rows(df=None,audit=None):
    if df is None:
        df,audit=load_qqq_history()
    dates=df["Date"].dt.date.astype(str).tolist()
    closes=df["Close"].astype(float).tolist()
    decisions=replay_levels(closes,dates)
    by_date={d.asof_date:d for d in decisions}
    rows=[];prev=None
    for dt,close in zip(dates,closes):
        d=by_date.get(dt)
        if d is None: continue
        event=prev is not None and d.target_leverage!=prev.target_leverage
        rows.append({"date":dt,"close":close,"leverage":float(d.target_leverage),"level":int(d.level),"defense":bool(d.defense_active),"event":bool(event),"vol20":float(d.features.vol20),"sma50":float(d.features.sma50),"sma200":float(d.features.sma200),"mom12":float(d.features.mom12)})
        prev=d
    return rows,audit




def _retroactive_rows(df=None,audit=None):
    """Research-only extension before frozen 2009 trading start; never baseline evidence."""
    if df is None:
        df,audit=load_qqq_history()
    dates=df["Date"].dt.date.astype(str).tolist();closes=df["Close"].astype(float).tolist()
    rows=[];level=None;prev_lev=None
    for i in range(252,len(closes)):
        ft=compute_features(closes[:i+1]);level=next_level(ft,level);defense=defense_active(ft)
        lev=0.0 if defense else float(LEVEL_LEVERAGE[level])
        rows.append({"date":dates[i],"close":closes[i],"leverage":lev,"level":int(level),"defense":bool(defense),"event":prev_lev is not None and lev!=prev_lev})
        prev_lev=lev
    return rows,audit

def _drawdown_profile(ledger):
    worst=min(ledger,key=lambda x:float(x.get("drawdown",0.0)))
    trough_i=ledger.index(worst);recovery=None
    pre_peak=max(float(x["net_nav"]) for x in ledger[:trough_i+1])
    for x in ledger[trough_i+1:]:
        if float(x["net_nav"])>=pre_peak:
            recovery=x["date"];break
    return {"max_drawdown":float(worst["drawdown"]),"trough_date":worst["date"],"recovery_date":recovery,
      "recovered":recovery is not None,"underwater_sessions_after_trough":(next((i for i,x in enumerate(ledger[trough_i+1:],1) if float(x["net_nav"])>=pre_peak),len(ledger)-trough_i-1))}

def _period_metrics(rows,adapter,start,end):
    selected=[r for r in rows if start<=r["date"]<=end]
    if len(selected)<2:return None
    s=run_backtest(selected,stocklens_8_request(initial=100000,monthly=0,cost_bps=5),adapter)
    qrows=[dict(x,leverage=1.0,event=False) for x in selected]
    q=run_backtest(qrows,stocklens_8_request(initial=100000,monthly=0,cost_bps=0),adapter)
    return {"start":s["start"],"end":s["end"],"sessions":s["sessions"],
      "strategy_cagr":s["analytics"]["cagr_without_contribution_distortion"],"strategy_max_drawdown":s["max_drawdown"],
      "qqq_cagr":q["analytics"]["cagr_without_contribution_distortion"],"qqq_max_drawdown":q["max_drawdown"],
      "excess_cagr":s["analytics"]["cagr_without_contribution_distortion"]-q["analytics"]["cagr_without_contribution_distortion"]}




def _downside_windows(ledger):
    nav=[float(x["net_nav"]) for x in ledger]; dates=[x["date"] for x in ledger]; out={}
    for label,n in (("1m",21),("3m",63),("6m",126),("12m",252)):
        vals=[]
        for i in range(n,len(nav)):
            vals.append((nav[i]/nav[i-n]-1.0,i))
        if vals:
            worst,i=min(vals,key=lambda x:x[0])
            out[label]={"return":float(worst),"start":dates[i-n],"end":dates[i],"sessions":n}
    return out

def _underwater_stats(ledger):
    peak=-float("inf"); underwater=0; max_run=0; current=0
    for x in ledger:
        nav=float(x["net_nav"])
        if nav>=peak:
            peak=nav;current=0
        else:
            underwater+=1;current+=1;max_run=max(max_run,current)
    return {"underwater_sessions":underwater,"underwater_fraction":underwater/len(ledger) if ledger else None,"longest_underwater_run_sessions":max_run}

def _exposure_attribution(rows):
    buckets={str(x):{"sessions":0,"compounded_market_return":1.0} for x in (0.0,1.25,2.0,3.0)}
    for i in range(1,len(rows)):
        lev=float(rows[i-1]["leverage"]); key=str(lev)
        r=float(rows[i]["close"])/float(rows[i-1]["close"])-1.0
        b=buckets.setdefault(key,{"sessions":0,"compounded_market_return":1.0})
        b["sessions"]+=1;b["compounded_market_return"]*=1.0+r*lev
    for b in buckets.values():b["compounded_market_return"]-=1.0
    return buckets

def _cost_stress(rows,adapter):
    out=[]
    for bps in (0,5,10,25,50):
        x=run_backtest(rows,stocklens_8_request(initial=100000,monthly=0,cost_bps=bps),adapter)
        out.append({"cost_bps":bps,"end_equity":x["end_equity"],"cagr":x["analytics"]["cagr_without_contribution_distortion"],"max_drawdown":x["max_drawdown"],"estimated_cost":x["total_estimated_transaction_cost"]})
    return out


def _rolling_windows(rows,adapter):
    out={}
    for years in (1,3,5):
        span=years*252; samples=[]
        for i in range(0,max(0,len(rows)-span),21):
            chunk=rows[i:i+span+1]
            if len(chunk)<span:continue
            s=run_backtest(chunk,stocklens_8_request(initial=100000,monthly=0,cost_bps=5),adapter)
            q=run_backtest([dict(x,leverage=1.0,event=False) for x in chunk],stocklens_8_request(initial=100000,monthly=0,cost_bps=0),adapter)
            sc=s["analytics"]["cagr_without_contribution_distortion"];qc=q["analytics"]["cagr_without_contribution_distortion"]
            samples.append({"start":chunk[0]["date"],"end":chunk[-1]["date"],"strategy_cagr":sc,"qqq_cagr":qc,"excess_cagr":sc-qc})
        out[str(years)+"y"]={"samples":len(samples),"strategy_above_qqq":sum(x["excess_cagr"]>0 for x in samples),
          "worst_excess_cagr":min((x["excess_cagr"] for x in samples),default=None),
          "best_excess_cagr":max((x["excess_cagr"] for x in samples),default=None)}
    return out

def _calendar_years(rows,adapter):
    years=sorted({r["date"][:4] for r in rows})
    out=[]
    for y in years:
        m=_period_metrics(rows,adapter,y+"-01-01",y+"-12-31")
        if m:
            full_year=(m["start"]<=y+"-01-07" and m["end"]>=y+"-12-20")
            out.append({"year":int(y),"full_year":full_year,**m})
    return out

def _exposure_mix(rows):
    n=len(rows) or 1
    counts={}
    for r in rows:
        k=str(float(r["leverage"]))
        counts[k]=counts.get(k,0)+1
    return {"sessions":len(rows),"counts":counts,"fractions":{k:v/n for k,v in counts.items()}}


def _verdict(result):
    rw=result["rolling_windows"]; cost=result["cost_stress"]; ann=result["annual_summary"]
    checks={
      "sanity":result["sanity"]["status"]=="PASS",
      "lean_claim_boundary_preserved":result["execution_parity"] is False,
      "cost_50bps_finite":bool(cost) and math.isfinite(float(cost[-1]["cagr"])),
      "rolling_5y_available":rw.get("5y",{}).get("samples",0)>0,
      "annual_comparison_available":ann.get("years_compared",0)>0,
      "retroactive_isolated":result["retroactive_extension"]["baseline_mutated"] is False
    }
    return {"status":"PASS" if all(checks.values()) else "ATTENTION","checks":checks,
      "interpretation_policy":"DESCRIPTIVE_RESEARCH_ONLY_NO_AUTOMATIC_PROMOTION",
      "promotion_allowed":False,
      "status_meaning":"PACKAGE_INTEGRITY_ONLY_NOT_STRATEGY_VALIDATION",
      "canonical_claim":"Yahoo independently reconstructs frozen StockLens rules from the canonical 2009 start; it does not prove original LEAN execution parity.",
      "retroactive_claim":"Pre-2009 results are a separate retroactive research extension and are never baseline evidence."}

def build(out=OUT):
    df,audit=load_qqq_history()
    rows,_=_rows(df,audit)
    adapter=FrozenExposureReplayAdapter()
    pure=run_backtest(rows,stocklens_8_request(initial=100000,monthly=0,cost_bps=5),adapter)
    contributed=run_backtest(rows,stocklens_8_request(initial=100000,monthly=3500,cost_bps=5),adapter)
    qqq_rows=[dict(x,leverage=1.0,event=False) for x in rows]
    qqq=run_backtest(qqq_rows,stocklens_8_request(initial=100000,monthly=0,cost_bps=0),adapter)
    qqq_contributed=run_backtest(qqq_rows,stocklens_8_request(initial=100000,monthly=3500,cost_bps=5),adapter)
    retro_rows,_=_retroactive_rows(df,audit)
    retro=run_backtest(retro_rows,stocklens_8_request(initial=100000,monthly=0,cost_bps=5),adapter)
    retro_qqq=run_backtest([dict(x,leverage=1.0,event=False) for x in retro_rows],stocklens_8_request(initial=100000,monthly=0,cost_bps=0),adapter)
    annual=_calendar_years(rows,adapter)
    comparable=[x for x in annual if x.get("strategy_cagr") is not None and x.get("qqq_cagr") is not None]
    comparable_full=[x for x in comparable if x.get("full_year")]
    annual_summary={
      "years_compared":len(comparable),
      "strategy_above_qqq_years":sum(x["strategy_cagr"]>x["qqq_cagr"] for x in comparable),
      "strategy_below_qqq_years":sum(x["strategy_cagr"]<x["qqq_cagr"] for x in comparable),
      "strategy_equal_qqq_years":sum(x["strategy_cagr"]==x["qqq_cagr"] for x in comparable),
      "full_years_compared":len(comparable_full),
      "best_strategy_year":max(comparable_full,key=lambda x:x["strategy_cagr"]) if comparable_full else None,
      "worst_strategy_year":min(comparable_full,key=lambda x:x["strategy_cagr"]) if comparable_full else None,
      "best_worst_excludes_partial_years":True
    }
    sanity={
      "sessions_ge_3000":len(rows)>=3000,
      "history_ge_10_years":int(rows[-1]["date"][:4])-int(rows[0]["date"][:4])>=10,
      "transitions_nonzero":sum(bool(x["event"]) for x in rows)>0,
      "allowed_exposures_only":all(float(x["leverage"]) in (0.0,1.25,2.0,3.0) for x in rows),
      "finite_core_metrics":all(math.isfinite(float(x)) for x in (pure["end_equity"],pure["max_drawdown"],qqq["end_equity"],qqq["max_drawdown"],contributed["end_equity"])),
      "matched_contribution_capital":abs(float(contributed["paid_capital"])-float(qqq_contributed["paid_capital"]))<1e-9
    }
    sanity["status"]="PASS" if all(sanity.values()) else "FAIL"
    result={
      "schema_version":1,
      "status":"PASS" if sanity["status"]=="PASS" else "FAIL",
      "sanity":sanity,
      "kind":"YAHOO_INDEPENDENT_LONG_HISTORY_RECONSTRUCTION",
      "frozen_model":"StockLens 8.0",
      "source":"YFINANCE_QQQ_AUTO_ADJUSTED",
      "execution_parity":False,
      "claim_boundary":"Independent Yahoo reconstruction; not original LEAN execution evidence.",
      "instrument_semantics":{"model":"DAILY_QQQ_RETURN_TIMES_PRIOR_SESSION_TARGET_LEVERAGE","actual_tqqq_history":False,"synthetic_before_tqqq_inception":True,"limitations":["No actual leveraged-ETF fee series","No financing spread","No tracking error","No intraday rebalance mechanics","Daily compounding is modeled from QQQ returns rather than observed TQQQ prices"]},
      "retroactive_extension":{"evidence_class":"RETROACTIVE_RESEARCH_EXTENSION_NOT_FROZEN_BASELINE","baseline_mutated":False,"start":retro_rows[0]["date"],"end":retro_rows[-1]["date"],"sessions":len(retro_rows),"strategy_cagr":retro["analytics"]["cagr_without_contribution_distortion"],"strategy_max_drawdown":retro["max_drawdown"],"qqq_cagr":retro_qqq["analytics"]["cagr_without_contribution_distortion"],"qqq_max_drawdown":retro_qqq["max_drawdown"],"warning":"Applies frozen decision rules before their canonical 2009 trading start. Research only; not LEAN parity or original StockLens 8.0 evidence."},
      "retroactive_subperiods":[x for x in [_period_metrics(retro_rows,adapter,"2000-01-01","2002-12-31"),_period_metrics(retro_rows,adapter,"2003-01-01","2008-12-31")] if x is not None],
      "retroactive_coverage":{"requested_start":"2000-01-01","actual_start":retro_rows[0]["date"],"partial_initial_period":retro_rows[0]["date"]>"2000-01-01"},
      "sessions":len(rows),"start":rows[0]["date"],"end":rows[-1]["date"],
      "strategy_no_contributions":{
        "end_equity":pure["end_equity"],"cagr":pure["analytics"]["cagr_without_contribution_distortion"],
        "max_drawdown":pure["max_drawdown"],"estimated_cost":pure["total_estimated_transaction_cost"]},
      "qqq_buy_hold_no_contributions":{
        "end_equity":qqq["end_equity"],"cagr":qqq["analytics"]["cagr_without_contribution_distortion"],
        "max_drawdown":qqq["max_drawdown"]},
      "qqq_with_monthly_3500":{"end_equity":qqq_contributed["end_equity"],"paid_capital":qqq_contributed["paid_capital"],"profit_loss":qqq_contributed["replay_profit_loss"],"max_drawdown":qqq_contributed["max_drawdown"],"cagr":None,"cagr_reason":"Monthly external contributions make endpoint CAGR misleading; intentionally omitted."},
      "contribution_comparison":{"strategy_cost_bps":5,"qqq_cost_bps":5,"matched_cost_assumption":True,"strategy_minus_qqq_end_equity":contributed["end_equity"]-qqq_contributed["end_equity"],"strategy_to_qqq_end_equity_ratio":contributed["end_equity"]/qqq_contributed["end_equity"] if qqq_contributed["end_equity"] else None},
      "strategy_with_monthly_3500":{
        "end_equity":contributed["end_equity"],"paid_capital":contributed["paid_capital"],
        "profit_loss":contributed["replay_profit_loss"],"max_drawdown":contributed["max_drawdown"],
        "cagr":None,"cagr_reason":"Monthly external contributions make endpoint CAGR misleading; intentionally omitted."},
      "source_audit":audit,
      "provenance":{"adapter":adapter.strategy_id,"evidence_class":adapter.evidence_class,
        "pure_ledger_sha256":pure["ledger_sha256"],"contributed_ledger_sha256":contributed["ledger_sha256"],
        "qqq_ledger_sha256":qqq["ledger_sha256"]},
      "comparison":{"strategy_minus_qqq_cagr":pure["analytics"]["cagr_without_contribution_distortion"]-qqq["analytics"]["cagr_without_contribution_distortion"],"strategy_minus_qqq_max_drawdown":pure["max_drawdown"]-qqq["max_drawdown"],"strategy_to_qqq_ending_equity_ratio":pure["end_equity"]/qqq["end_equity"] if qqq["end_equity"] else None},
      "transition_count":sum(bool(x["event"]) for x in rows),
      "drawdown_profile":{"strategy":_drawdown_profile(pure["ledger"]),"qqq":_drawdown_profile(qqq["ledger"])},
      "downside_windows":{"strategy":_downside_windows(pure["ledger"]),"qqq":_downside_windows(qqq["ledger"])},
      "underwater":{"strategy":_underwater_stats(pure["ledger"]),"qqq":_underwater_stats(qqq["ledger"])},
      "subperiods":[x for x in [_period_metrics(rows,adapter,"2009-09-01","2014-12-31"),_period_metrics(rows,adapter,"2015-01-01","2019-12-31"),_period_metrics(rows,adapter,"2020-01-01","2024-12-31"),_period_metrics(rows,adapter,"2025-01-01","2099-12-31")] if x is not None],
      "calendar_years":annual,
      "annual_summary":annual_summary,
      "exposure_mix":_exposure_mix(rows),
      "exposure_attribution":_exposure_attribution(rows),
      "cost_stress":_cost_stress(rows,adapter),
      "rolling_windows":_rolling_windows(rows,adapter)
    }
    result["research_verdict"]=_verdict(result)
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,default=str)+chr(10))
    return result

if __name__=="__main__": print(json.dumps(build(),indent=2,default=str))
