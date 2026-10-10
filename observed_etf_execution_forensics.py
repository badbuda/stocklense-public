"""Auditable StockLens 8.0 daily execution forensics, NOT broker fills.

Yahoo-adjusted REAL QQQ/TQQQ Open/Close inputs; whole-share trades and costs
are MODELED. No synthetic TQQQ, no future signal and no model promotion.
"""
from __future__ import annotations
import json
import math
from datetime import date
from pathlib import Path
from statistics import mean

from observed_etf_two_question_audit import load, _run, _metrics, _prices, START_CAPITAL
from observed_etf_vol60_reentry_audit import simulate as overlay_sim
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from tradable_tqqq_execution_comparison import _mark, _rebalance

OUT = Path("research/results/observed_execution_crisis_forensics.json")
REPORT = Path("research/reports/observed_execution_crisis_forensics.md")
SYMBOLS = ("QQQ","TQQQ")
DELAYS = (0,1,2)
SLIPPAGES = (10.,20.,30.)
GAP_PENALTIES = (0.,30.,60.)
CRISES = {
  "2015_16":("2015-08-01","2016-03-31"),
  "2018_Q4":("2018-09-04","2019-01-31"),
  "2020_COVID":("2020-02-01","2020-05-31"),
  "2022_RATES":("2022-01-03","2022-12-30"),
}


def _target(level):
    if level not in (0.,1.25,2.,3.):
        raise ValueError("INVALID_FROZEN_EXPOSURE")
    if level==0:
        return {"QQQ":0.,"TQQQ":0.}
    q,t=weights_for_leverage(level)
    return {"QQQ":q*TARGET_INVESTED_FRACTION,
            "TQQQ":t*TARGET_INVESTED_FRACTION}


def replay(rows, *, delay=0, slip=10., extra_gap_slip=0.):
    """Break each NAV change into overnight, open execution and intraday.

    Gap liquidity surcharge is HYPOTHETICAL on days with observed<-3% gap
    in either ETF AND an actual frozen rebalance; never invent an ETF price.
    """
    if delay not in DELAYS or slip not in SLIPPAGES or extra_gap_slip not in GAP_PENALTIES:
        raise ValueError("UNREGISTERED_STRESS_VARIANT")
    if len(rows)<3:raise ValueError("INSUFFICIENT_PATH")
    p={"cash":START_CAPITAL,"shares":{"QQQ":0,"TQQQ":0},
       "fees":0.,"slippage":0.,"trades":0,"turnover_notional":0.}
    obs=[]
    prev_day=""
    prev_close=None
    prev_level=None
    prev_nav=START_CAPITAL
    penalty_events=0
    for i,row in enumerate(rows):
        if row["date"]<=prev_day or row.get("signal","")>=row["date"]:
            raise ValueError("BAD_DATE_OR_FUTURE_SIGNAL")
        for k in ("qo","qc","to","tc"):
            if not isinstance(row.get(k),(float,int)) or not math.isfinite(row[k]) or row[k]<=0:
                raise ValueError("BAD_OBSERVED_PRICE:"+k)
        # Historical frozen target as observed by the original prior-session
        # replay. A delayed target uses only earlier already-available rows.
        earlier=rows[max(0,i-delay)]
        level=float(earlier["l"])
        weights=_target(level)
        px=_prices(row)
        if prev_close is None:
            open_gap={s:None for s in SYMBOLS}
            pnl_gap=0.
            open_pre=START_CAPITAL
        else:
            open_gap={s:px[s]["open"]/prev_close[s]-1 for s in SYMBOLS}
            pnl_gap=sum(p["shares"][s]*(px[s]["open"]-prev_close[s]) for s in SYMBOLS)
            open_pre=_mark(p,px,"open")
            if not math.isclose(open_pre,prev_nav+pnl_gap,rel_tol=1e-10,abs_tol=.001):
                raise ValueError("NIGHT_ACCOUNTING_BROKEN")
        if open_pre<=0:raise ValueError("BANKRUPT_AT_OPEN")
        fee_before,slip_before,orders_before=p["fees"],p["slippage"],p["trades"]
        trade=prev_level is None or prev_level!=level
        event_penalty=extra_gap_slip if trade and any(
            g is not None and g<=-.03 for g in open_gap.values()) else 0.
        penalty_events+=int(event_penalty>0)
        if trade:
            _rebalance(p,px,weights,2.,slip+event_penalty)
        open_post=_mark(p,px,"open")
        modeled_fee=p["fees"]-fee_before
        modeled_slip=p["slippage"]-slip_before
        if not math.isclose(open_pre-open_post,modeled_fee+modeled_slip,
                            abs_tol=.001,rel_tol=1e-10):
            raise ValueError("COST_ACCOUNTING_BROKEN")
        session_pnl=sum(p["shares"][s]*(px[s]["close"]-px[s]["open"]) for s in SYMBOLS)
        close=_mark(p,px,"close")
        if not math.isclose(close,prev_nav+pnl_gap+session_pnl-modeled_fee-modeled_slip,
                            abs_tol=.001,rel_tol=1e-10):
            raise ValueError("FULL_DAY_ACCOUNTING_BROKEN")
        if close<=0 or p["cash"]<-.00001:
            raise ValueError("INSOLVENT_MODELED_PORTFOLIO")
        contributions={
          "overnight":math.log(open_pre/prev_nav),
          "execution":math.log(open_post/open_pre),
          "intraday":math.log(close/open_post)}
        if not math.isclose(sum(contributions.values()),math.log(close/prev_nav),abs_tol=1e-11):
            raise ValueError("LOG_RETURN_ACCOUNTING_BROKEN")
        obs.append({
          "date":row["date"],"signal":earlier["signal"],
          "prior_frozen_level":level,"rebalance":trade,
          "model_orders":p["trades"]-orders_before,
          "nav":close,"prior_nav":prev_nav,"daily_return":close/prev_nav-1.,
          "overnight_dollar_pnl":pnl_gap,"intraday_dollar_pnl":session_pnl,
          "model_fees":modeled_fee,"model_slippage":modeled_slip,
          "overnight_gap_by_etf":open_gap,
          "log_components":contributions,"gap_liquidity_penalty_bps":event_penalty})
        prev_day=row["date"]
        prev_nav=close
        prev_level=level
        prev_close={s:px[s]["close"] for s in SYMBOLS}
    return {"rows":obs,
            "metrics":_metrics([r["nav"] for r in obs],[r["date"] for r in obs]),
            "model_orders":p["trades"],"modeled_fees":p["fees"],
            "modeled_slippage":p["slippage"],
            "penalized_rebalance_sessions":penalty_events}


def distinct_drawdowns(rows, n=10):
    """Peak/trough/recovery episodes, with virtual inception peak and censoring."""
    peak=START_CAPITAL
    high_i=-1
    current=None
    closed=[]
    for i,row in enumerate(rows):
        val=row["nav"]
        if val>=peak:
            if current is not None:
                current["recovery_i"]=i
                closed.append(current)
                current=None
            peak=val
            high_i=i
        else:
            if current is None:
                current={"peak_i":high_i,"trough_i":i,"peak_nav":peak,
                         "trough_nav":val,"recovery_i":None}
            elif val<current["trough_nav"]:
                current.update(trough_i=i,trough_nav=val)
    if current is not None:
        closed.append(current)
    out=[]
    for e in sorted(closed,key=lambda e:e["trough_nav"]/e["peak_nav"])[:n]:
        a,b=e["peak_i"],e["trough_i"]
        window=rows[a+1:b+1]
        parts={k:sum(r["log_components"][k] for r in window)
               for k in ("overnight","intraday","execution")}
        total=math.log(e["trough_nav"]/e["peak_nav"])
        if not math.isclose(total,sum(parts.values()),abs_tol=1e-9):
            raise ValueError("EPISODE_PNL_NOT_EXACT")
        first_delev=next((r["date"] for r in window if r["prior_frozen_level"]<3.),None)
        negatives=[(r["date"],-math.log1p(r["daily_return"]))
                   for r in window if r["daily_return"]<0]
        biggest=sorted(negatives,key=lambda x:x[1],reverse=True)[:5]
        out.append({
         "peak_date":rows[a]["date"] if a>=0 else "INCEPTION",
         "trough_date":rows[b]["date"],
         "recovery_date":rows[e["recovery_i"]]["date"] if e["recovery_i"] is not None else None,
         "recovery_right_censored":e["recovery_i"] is None,
         "peak_to_trough_sessions":b-a,
         "peak_to_recovery_sessions":e["recovery_i"]-a if e["recovery_i"] is not None else None,
         "peak_to_trough_return":e["trough_nav"]/e["peak_nav"]-1.,
         "exact_log_attribution":parts,
         "gross_negative_log_by_exposure":{
          str(l):sum(-math.log1p(r["daily_return"])
                     for r in window if r["daily_return"]<0 and r["prior_frozen_level"]==l)
          for l in (0.,1.25,2.,3.)},
         "first_day_under_3x":first_delev,
         "top5_negative_days":biggest,
         "top5_fraction_of_all_negative_logs":sum(x[1] for x in biggest)/sum(x[1] for x in negatives) if negatives else 0,
         "diagnostic_only_no_prospective_selection":True,
        })
    return out


def named_windows(rows):
    result={}
    for name,(begin,end) in CRISES.items():
        w=[r for r in rows if begin<=r["date"]<=end]
        if len(w)<40:raise ValueError("MISSING_CRISIS_COHORT:"+name)
        comp={k:sum(r["log_components"][k] for r in w)
              for k in ("overnight","intraday","execution")}
        pnl=math.log(w[-1]["nav"]/w[0]["prior_nav"])
        if not math.isclose(sum(comp.values()),pnl,abs_tol=1e-9):
            raise ValueError("CRISIS_LOG_RECONCILIATION_BROKEN:"+name)
        peak=w[0]["prior_nav"]
        dd=0.
        for row in w:
            peak=max(peak,row["nav"])
            dd=min(dd,row["nav"]/peak-1.)
        result[name]={
         "begin":w[0]["date"],"end":w[-1]["date"],"sessions":len(w),
         "total_window_return":w[-1]["nav"]/w[0]["prior_nav"]-1.,
         "window_max_drawdown":dd,
         "exact_log_components":comp,
         "model_orders":sum(r["model_orders"] for r in w),
         "cost_currency":sum(r["model_fees"]+r["model_slippage"] for r in w),
         "negative_overnight_pnl_days":sum(r["overnight_dollar_pnl"]<0 for r in w),
        }
    return result


def tails(rows):
    sorted_rets=sorted(r["daily_return"] for r in rows)
    def es(frac):
        n=max(1,math.ceil(len(sorted_rets)*frac))
        return mean(sorted_rets[:n])
    # Rolling 21 / 63 session returns includes the pre-window close.
    nav=[START_CAPITAL]+[r["nav"] for r in rows]
    roll={}
    for h in (21,63,252):
        roll[str(h)]=min(nav[i+h]/nav[i]-1. for i in range(len(nav)-h))
    high=START_CAPITAL
    streak=max_streak=0
    for r in rows:
        high=max(high,r["nav"])
        streak=streak+1 if r["nav"]<high else 0
        max_streak=max(max_streak,streak)
    gap_rows=[r for r in rows if any(
      gap is not None and gap<=-.03 for gap in r["overnight_gap_by_etf"].values())]
    overnight_worst=sorted(rows[1:],key=lambda r:r["overnight_dollar_pnl"]/r["prior_nav"])[:10]
    return {
      "empirical_daily_ES_1pct":es(.01),"empirical_daily_ES_5pct":es(.05),
      "worst_daily_return":min(sorted_rets),
      "worst_rolling_simple_returns":roll,
      "longest_sessions_underwater":max_streak,
      "remaining_underwater_at_last_day":streak>0,
      "observed_gap_below_minus3pct_any_etf_sessions":len(gap_rows),
      "severe_gap_sessions_with_model_orders":sum(bool(r["model_orders"]) for r in gap_rows),
      "worst_overnight_account_losses":[{
       "day":r["date"],"overnight_pnl_frac":r["overnight_dollar_pnl"]/r["prior_nav"],
       "QQQ_gap":r["overnight_gap_by_etf"]["QQQ"],
       "TQQQ_gap":r["overnight_gap_by_etf"]["TQQQ"],
       "model_orders":r["model_orders"]} for r in overnight_worst],
      "worst_daily_returns":[{
       "day":r["date"],"daily_return":r["daily_return"],
       "level":r["prior_frozen_level"],"parts":r["log_components"]}
       for r in sorted(rows,key=lambda z:z["daily_return"])[:10]],
    }


def evaluate(source):
    if source.get("evidence")!="REAL_QQQ_TQQQ_ADJUSTED_DAILY_OPEN_EXECUTION_PROXY" or source.get("live_trading_authorized") is not False or source.get("full_lean_broker_parity") is not False:
        raise ValueError("UNVERIFIED_OR_LIVE_SOURCE")
    raw=source["daily"]
    if len(raw)<3000:raise ValueError("HISTORICAL_COHORT_TOO_SHORT")
    previous=_run(raw,variant="frozen")
    x=replay(raw)
    if len(previous["navs"])!=len(x["rows"]):
        raise ValueError("DIFFERENT_DAY_COUNT")
    largest=0.
    for observed,ref in zip(x["rows"],previous["navs"]):
        e=abs(observed["nav"]-ref)/ref
        largest=max(largest,e)
        if e>2e-10:raise ValueError("FROZEN_NAV_PARITY_BROKEN:"+observed["date"])
    episodes=distinct_drawdowns(x["rows"])
    comparative={}
    # Overlay episodes share the EXACT frozen peak/trough boundaries.
    index={r["date"]:i for i,r in enumerate(raw)}
    for name in ("vol60_instant","vol60_hold10_ramp10"):
        z=overlay_sim(raw,mode=name)
        comparative[name]=[]
        for e in episodes:
            start=index[e["peak_date"]] if e["peak_date"]!="INCEPTION" else -1
            end=index[e["trough_date"]]
            a=START_CAPITAL if start==-1 else z["navs"][start]
            ret=z["navs"][end]/a-1.
            comparative[name].append({
              "peak_date":e["peak_date"],"trough_date":e["trough_date"],
              "frozen_return":e["peak_to_trough_return"],
              "overlay_same_dates_return":ret,
              "delta_return_pp":100*(ret-e["peak_to_trough_return"])})
    stress=[]
    for lag in DELAYS:
        for slip in SLIPPAGES:
            for penalty in GAP_PENALTIES:
                v=replay(raw,delay=lag,slip=slip,extra_gap_slip=penalty)
                s=v["metrics"]
                stress.append({
                 "extra_frozen_signal_delay_sessions":lag,
                 "ordinary_slippage_bps_per_side":slip,
                 "extra_slippage_only_on_severe_gap_rebalance_bps":penalty,
                 "cagr":s["cagr"],"max_drawdown":s["max_drawdown"],
                 "ending_equity":s["ending_equity"],
                 "model_orders":v["model_orders"],
                 "gap_penalized_sessions":v["penalized_rebalance_sessions"],
                 "delta_cagr_pp_vs_frozen":100*(s["cagr"]-x["metrics"]["cagr"]),
                 "delta_maxdd_pp_vs_frozen":100*(s["max_drawdown"]-x["metrics"]["max_drawdown"])})
    assert len(stress)==27
    return {
      "schema_version":1,
      "kind":"REAL_QQQ_TQQQ_OPEN_EXECUTION_CRISIS_FORENSICS",
      "status":"DIAGNOSTIC_ONLY_NOT_TRADE_READY",
      "source_snapshot_sha256":source["snapshot_sha256"],
      "period":source["period"],
      "daily_frozen_nav_exactly_replayed":True,
      "largest_relative_daily_nav_residual":largest,
      "frozen":{**x["metrics"],"model_orders":x["model_orders"],
                "model_fees":x["modeled_fees"],"model_slippage":x["modeled_slippage"]},
      "ten_distinct_drawdown_episodes":episodes,
      "four_crisis_window_log_attribution":named_windows(x["rows"]),
      "observed_gap_risk_and_recovery":tails(x["rows"]),
      "overlay_same_frozen_episode_counterfactuals":comparative,
      "delay_slippage_gap_penalty_stress":stress,
      "predeclared_stress_counts":{"delay":len(DELAYS),
          "base_slippage":len(SLIPPAGES),"hypothetical_gap_penalty":len(GAP_PENALTIES)},
      "not_nasdaq_original_broker_lean":True,
      "real_etf_prices_not_synthetic_3x":True,
      "model_promotion_allowed":False,
      "broker_orders_authorized":False,
      "forward_independent_validation_proven":False,
      "limitations":[
        "Whole-share buys/sells simulated against Yahoo-adjusted daily OPEN; actual 09:31/09:32 NBBO and broker fills unavailable.",
        "Log overnight/intraday/cost is an exact accounting identity under MODEL fills, not attribution of predictive causality.",
        "Extra opening-gap liquidity slippage is a hypothetical sensitivity on real observed gaps, not a synthetic market observation.",
        "Frozen signal delay is an extra historical row lag, using the earliest known pre-session signal for initial warmup.",
        "Worst drawdown and the four named windows were retrospectively inspected and cannot be called an untouched holdout.",
        "Frozen model unchanged; no capital deployment or promotion."
      ]}
      

def report_md(r):
    fmt=lambda x:f"{100*x:.2f}%"
    lines=["# StockLens 8.0 — crisis attribution, overnight gaps and execution robustness",
      "",
      f'Observed QQQ/TQQQ adjusted daily OHLC {r["period"]["start"]}—{r["period"]["end"]} ({r["period"]["sessions"]} sessions); simulated next-daily-OPEN orders.',
      f'Exact daily NAV parity residual: {r["largest_relative_daily_nav_residual"]:.2g}. FROZEN model immutable.',
      "",
      "## The most severe distinct drawdowns (no nested overlapping episodes)",
      "| Peak | Trough | DD | Nights (log) | Intraday (log) | Cost (log) | Deleverage before trough | Recovery |",
      "|---|---|---:|---:|---:|---:|---|---|"]
    for e in r["ten_distinct_drawdown_episodes"]:
        c=e["exact_log_attribution"]
        lines.append(f'| {e["peak_date"]} | {e["trough_date"]} | {fmt(e["peak_to_trough_return"])} | '
           f'{c["overnight"]:+.4f} | {c["intraday"]:+.4f} | {c["execution"]:+.4f} | '
           f'{e["first_day_under_3x"] or "No"} | {e["recovery_date"] or "UNRECOVERED"} |')
    lines+=["", "## Four predeclared historical crisis windows",
        "| Period | Simple return | MaxDD within window | Log overnight | Log intraday | Log costs | Simulated orders |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for name,w in r["four_crisis_window_log_attribution"].items():
        c=w["exact_log_components"]
        lines.append(f'| {name} | {fmt(w["total_window_return"])} | {fmt(w["window_max_drawdown"])} | '
                     f'{c["overnight"]:+.4f} | {c["intraday"]:+.4f} | {c["execution"]:+.4f} | {w["model_orders"]} |')
    t=r["observed_gap_risk_and_recovery"]
    lines+=["","## Historical tails (descriptive, no extrapolation)", "",
      f'- Worst single modeled session {fmt(t["worst_daily_return"])}; empirical 1% expected shortfall {fmt(t["empirical_daily_ES_1pct"])}.',
      f'- Longest period under a prior closing peak: {t["longest_sessions_underwater"]} sessions.',
      f'- Observed overnight negative gap ≥3% in QQQ or TQQQ: {t["observed_gap_below_minus3pct_any_etf_sessions"]} dates; {t["severe_gap_sessions_with_model_orders"]} coincided with model orders.',
      "","## 27 hypothetical price-execution stresses (observed historical gaps only)","",
      "| Added frozen-signal lag | Base slip | Extra slippage on actual ≥3% negative gap rebalance | CAGR | MaxDD |",
      "|---:|---:|---:|---:|---:|"]
    for row in r["delay_slippage_gap_penalty_stress"]:
        if row["ordinary_slippage_bps_per_side"] not in (10.,30.) or row["extra_slippage_only_on_severe_gap_rebalance_bps"] not in (0.,60.):
            continue
        lines.append(f'| {row["extra_frozen_signal_delay_sessions"]} | {row["ordinary_slippage_bps_per_side"]}bps | '
              f'{row["extra_slippage_only_on_severe_gap_rebalance_bps"]}bps | {fmt(row["cagr"])} | {fmt(row["max_drawdown"])} |')
    lines+=["","## Claim boundaries","",
     "- Costs/slippage are **modeled**. No original QuantConnect LEAN same-input parity, no NBBO or broker fill records.",
     "- Overnight gap losses cannot be undone at the same opening price. The overnight/daytime split is descriptive and not a standalone trading rule.",
     "- The selected crises are already known; this is not independent forward testing or a significance claim.",
     "- No synthetic TQQQ, no frozen-8.0 modification, no automatic model promotion or live capital authorization.",
     ""]
    return "\n".join(lines)


def build(out=OUT,report=REPORT):
    result=evaluate(load())
    out=Path(out);report=Path(report)
    out.parent.mkdir(parents=True,exist_ok=True)
    report.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    report.write_text(report_md(result))
    compact={
      "status":result["status"],"frozen":result["frozen"],
      "worst_episodes":[{
        "peak":e["peak_date"],"trough":e["trough_date"],"drawdown":e["peak_to_trough_return"],
        "first_delev":e["first_day_under_3x"],"log_components":e["exact_log_attribution"]}
        for e in result["ten_distinct_drawdown_episodes"][:4]],
      "crises":result["four_crisis_window_log_attribution"],
      "tails":{k:v for k,v in result["observed_gap_risk_and_recovery"].items() if not isinstance(v,list)},
      "stress_extremes":{
        "worst_maxdd":min(z["max_drawdown"] for z in result["delay_slippage_gap_penalty_stress"]),
        "lowest_cagr":min(z["cagr"] for z in result["delay_slippage_gap_penalty_stress"]),
        "best_maxdd":max(z["max_drawdown"] for z in result["delay_slippage_gap_penalty_stress"])},
      "exact_parity":result["daily_frozen_nav_exactly_replayed"]}
    print("STOCKLENS_EPISODE_CRISIS_FORENSICS="+json.dumps(compact,sort_keys=True))
    print("FILES="+str(out)+";"+str(report))
    return result


if __name__=="__main__":
    build()
