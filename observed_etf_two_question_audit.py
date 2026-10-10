"""Two-question StockLens 8.0 falsification audit using observed QQQ/TQQQ bars.

One externally checkable snapshot: docs/portal-history.json, derived Yahoo
observed (not synthetic) adjusted daily Open/Close with immutable frozen 8.0
prior-session exposure. Never a clean holdout, LEAN exact-input comparison,
observed intraday fill, or authorization for capital deployment.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
import json
import math
from pathlib import Path
import random
from statistics import mean, stdev

from stocklens.core import TARGET_INVESTED_FRACTION, weights_for_leverage
from tradable_tqqq_execution_comparison import _mark, _rebalance

SOURCE = Path("docs/portal-history.json")
OUT = Path("research/results/two_questions_risk_matched.json")
REPORT = Path("research/reports/two_questions_risk_matched.md")
SPLITS = {
    "development": ("2010-02-11", "2017-12-29"),
    "validation_reused": ("2018-01-02", "2022-12-30"),
    "later_observational_reused": ("2023-01-03", "2026-10-09"),
}
VARIANTS = ("frozen", "vol_tiers", "five_day_shock", "combined")
MIN_N = 3000
START_CAPITAL = 100000.
FEE_BPS, SLIP_BPS = 2., 10.


def load(source=SOURCE):
    raw = json.loads(Path(source).read_text(encoding="utf-8"))
    if (raw.get("evidence") != "REAL_QQQ_TQQQ_ADJUSTED_DAILY_OPEN_EXECUTION_PROXY"
        or raw.get("instruments") != ["QQQ", "TQQQ"]
        or raw.get("observed_ohlc_available") is not True
        or raw.get("full_lean_broker_parity") is not False
        or raw.get("live_trading_authorized") is not False):
        raise ValueError("SOURCE_NOT_OBSERVED_PROXY")
    rows = raw.get("daily", [])
    period = raw.get("period", {})
    if len(rows) < MIN_N or len(rows) != period.get("sessions"):
        raise ValueError("INCOMPLETE_OBSERVED_ETF_COHORT")
    days = [r.get("date") for r in rows]
    if (days != sorted(set(days)) or days[0] != period.get("start")
        or days[-1] != period.get("end") or days[-1] != raw.get("updated_session")):
        raise ValueError("NONMONOTONE_OR_STALE_COHORT")
    for row in rows:
        if (row.get("signal", "") >= row["date"]
            or row.get("l") not in (0, 1.25, 2, 3)
            or float(row.get("contribution", -1)) != 0):
            raise ValueError("FUTURE_SIGNAL_OR_CONTRIBUTION_CONTAMINATION")
        if not all(isinstance(row.get(key), (int, float)) and
                   math.isfinite(row[key]) and row[key] > 0
                   for key in ("qo", "qc", "to", "tc", "s", "q")):
            raise ValueError("UNOBSERVED_OR_INVALID_ETF_PRICE")
    recorded = raw["without_contributions"]
    if (abs(rows[-1]["s"] - recorded["strategy"]["ending_equity"]) > .06
        or abs(rows[-1]["q"] - recorded["qqq"]["ending_equity"]) > .06):
        raise ValueError("FROZEN_NAV_SOURCE_ENDPOINT_MISMATCH")
    return raw


def _std(values):
    return stdev(values) if len(values) >= 2 else float("nan")


def _daily_returns(values, initial=None):
    prev = [initial] + values[:-1] if initial is not None else values[:-1]
    out = [(a / b - 1) for a, b in zip(values if initial is not None else values[1:], prev)]
    if any(not math.isfinite(x) or x <= -1 for x in out):
        raise ValueError("INVALID_DAILY_RETURNS")
    return out


def _beta(y, x):
    dx = mean(x)
    dy = mean(y)
    den = sum((a - dx) ** 2 for a in x)
    if den <= 1e-14:
        raise ValueError("NO_BENCHMARK_VARIATION")
    return sum((a - dx) * (b - dy) for a, b in zip(x, y)) / den


def _hac_alpha(y, x, lag=21):
    """OLS intercept and Newey-West sandwich SE (not selection-corrected)."""
    n = len(y)
    if n < 100 or len(x) != n:
        raise ValueError("INSUFFICIENT_REGRESSION_SAMPLE")
    mx, my = mean(x), mean(y)
    v = sum((z-mx)**2 for z in x)
    beta = sum((a-mx)*(b-my) for a,b in zip(x,y))/v
    alpha = my-beta*mx
    residuals = [b-alpha-beta*a for a,b in zip(x,y)]
    # Residual scores with raw X=(1,x); sandwich sums have no n scaling.
    s00=s01=s11=0.
    for k in range(min(lag,n-1)+1):
        w=1. if k==0 else 1.-k/(min(lag,n-1)+1.)
        for t in range(k,n):
            u=residuals[t]*residuals[t-k]
            z0=1.
            z1=x[t]
            a0=1.
            a1=x[t-k]
            factor=w*(1 if k==0 else 1)
            s00+=factor*u*z0*a0
            s01+=factor*u*z0*a1
            s11+=factor*u*z1*a1
            if k:
                s01+=factor*u*z1*a0
                s11+=factor*u*z1*a1
                s00+=factor*u*z0*a0
    det=n*sum(t*t for t in x)-sum(x)**2
    inverse00=sum(t*t for t in x)/det
    inverse01=-sum(x)/det
    # symmetrized meat off-diagonal. The preceding loop collects cross terms.
    variance = inverse00**2*s00+2*inverse00*inverse01*s01+inverse01**2*s11
    se=math.sqrt(max(variance,0.))
    return {"beta_to_qqq":beta,"daily_arithmetic_alpha":alpha,
            "annualized_arithmetic_alpha":252*alpha,
            "hac_lags":lag,"annualized_alpha_se":252*se,
            "annualized_alpha_95pct_ci":[252*(alpha-1.96*se),252*(alpha+1.96*se)],
            "alpha_t_statistic_not_selection_corrected":alpha/se if se else None,
            "not_clean_inference":True}


def _metrics(navs, dates, first=START_CAPITAL):
    if len(navs)<2:raise ValueError("INSUFFICIENT_NAV_PATH")
    ret=_daily_returns(navs,first)
    peak=first
    dd=0.
    for nav in navs:
        peak=max(peak,nav)
        dd=min(dd,nav/peak-1)
    years=(date.fromisoformat(dates[-1])-date.fromisoformat(dates[0])).days/365.2425
    mu=mean(ret)
    downside=math.sqrt(mean([min(0,v)**2 for v in ret]))
    return {"sessions":len(navs),"start":dates[0],"end":dates[-1],
            "ending_equity":round(navs[-1],2),
            "cagr":(navs[-1]/first)**(1/years)-1,
            "max_drawdown":dd,
            "annualized_volatility":_std(ret)*math.sqrt(252),
            "annualized_mean_arithmetic":mu*252,
            "sharpe_zero_rf":mu/_std(ret)*math.sqrt(252) if _std(ret)>0 else None,
            "sortino_zero_rf":mu/downside*math.sqrt(252) if downside>0 else None}


def _prices(row):
    return {"QQQ":{"open":float(row["qo"]),"close":float(row["qc"])},
            "TQQQ":{"open":float(row["to"]),"close":float(row["tc"])}}


def _run(rows, *, variant="frozen", tqqq_weight=None, lag=0,
         fee_bps=FEE_BPS, slip_bps=SLIP_BPS):
    """Tradable ETF whole-share modeled next-open orders, not daily-return scaling."""
    if variant not in VARIANTS+("static_mix",) or lag not in (0,1,2):
        raise ValueError("UNKNOWN_PREDECLARED_VARIANT_OR_LAG")
    if tqqq_weight is not None and not (0<=tqqq_weight<=TARGET_INVESTED_FRACTION):
        raise ValueError("INVALID_STATIC_MIX_WEIGHT")
    p={"cash":START_CAPITAL,"shares":{"QQQ":0,"TQQQ":0},
       "fees":0.,"slippage":0.,"trades":0,"turnover_notional":0.}
    navs=[]
    previous=None
    prior_month=None
    hits=0
    target_levels=[]
    qclose=[float(r["qc"]) for r in rows]
    dates=[r["date"] for r in rows]
    for i,row in enumerate(rows):
        prices=_prices(row)
        if variant=="static_mix":
            weights={"QQQ":TARGET_INVESTED_FRACTION-tqqq_weight,
                     "TQQQ":tqqq_weight}
            target=("static",tqqq_weight)
        else:
            frozen=float(row["l"])
            cap=_cap(qclose,i-1-lag,variant)
            lev=min(frozen,cap)
            if lev < frozen:hits+=1
            x,y=weights_for_leverage(lev) if lev else (0.,0.)
            weights={"QQQ":x*TARGET_INVESTED_FRACTION,
                     "TQQQ":y*TARGET_INVESTED_FRACTION}
            target=lev
            target_levels.append(lev)
        rebalance=(previous is None or target!=previous or
                   variant=="static_mix" and prior_month!=row["date"][:7])
        if rebalance:
            _rebalance(p,prices,weights,fee_bps,slip_bps)
        mark=_mark(p,prices,"close")
        if not math.isfinite(mark) or mark<=0 or p["cash"]<-1e-5:
            raise ValueError("INVALID_PORTFOLIO_ACCOUNT")
        navs.append(mark)
        previous=target
        prior_month=row["date"][:7]
    return {"stats":_metrics(navs,dates),"navs":navs,"dates":dates,
            "intervention_sessions":hits,"trades":p["trades"],
            "modeled_fees":p["fees"],"modeled_slippage":p["slippage"],
            "exposures":target_levels}


def _cap(qclose, index, name):
    if name=="frozen":return 3.
    if index<0:return 3.
    if index>=21:
        returns=[math.log(qclose[j]/qclose[j-1]) for j in range(index-19,index+1)]
        rv=_std(returns)*math.sqrt(252)
    else:
        rv=0.
    tier=1.25 if rv>=.42 else 2. if rv>=.32 else 3.
    shock=3.
    if index>=5:
        for j in range(max(5,index-4),index+1):
            if qclose[j]/qclose[j-5]-1<=-.07:
                shock=2.
                break
    if name=="vol_tiers":return tier
    if name=="five_day_shock":return shock
    if name=="combined":return min(tier,shock)
    raise ValueError("UNKNOWN_VARIANT")


def _calibrate(rows):
    """Development-only fixed ETF mix, calibrated on *historically reused* 2010-17."""
    start,end=SPLITS["development"]
    train=[x for x in rows if start<=x["date"]<=end]
    s=_daily_returns([r["s"] for r in train])
    q=_daily_returns([r["qc"] for r in train])
    t=_daily_returns([r["tc"] for r in train])
    target_vol=_std(s)*math.sqrt(252)
    target_beta=_beta(s,q)
    grid=[TARGET_INVESTED_FRACTION*j/100 for j in range(101)]
    answers={}
    for mode in ("volatility","beta"):
        candidates=[]
        for weight in grid:
            mixed=[weight*a+(TARGET_INVESTED_FRACTION-weight)*b
                   for a,b in zip(t,q)]
            achieved=(_std(mixed)*math.sqrt(252) if mode=="volatility"
                      else _beta(mixed,q))
            target=target_vol if mode=="volatility" else target_beta
            candidates.append((abs(achieved-target),weight,achieved))
        error, weight, achieved=min(candidates,key=lambda x:(x[0],x[1]))
        answers[mode]={"tqqq_weight":weight,
                       "qqq_weight":TARGET_INVESTED_FRACTION-weight,
                       "training_target":target,"training_approximation":achieved,
                       "calibration_error":error,
                       "calibration_only_development":True,
                       "reused_historical_training_not_new_out_of_sample":True}
    return answers


def _regimes(rows):
    groups={}
    for i in range(201,len(rows)):
        c=[float(r["qc"]) for r in rows]
        # All conditioning uses COMPLETED observations before the return date.
        previous=i-1
        r20=[math.log(c[j]/c[j-1]) for j in range(previous-19,previous+1)]
        rv=_std(r20)*math.sqrt(252)
        trend="above_sma200" if c[previous]>=mean(c[previous-199:previous+1]) else "below_sma200"
        volatility="low_rv_below25pct" if rv<.25 else "mid_rv_25_to35pct" if rv<.35 else "high_rv_atleast35pct"
        for label in (volatility, trend, volatility+"_"+trend):
            groups.setdefault(label,[]).append((
                math.log(c[i]/c[i-1]),
                math.log(float(rows[i]["tc"])/float(rows[i-1]["tc"]))))
    result={}
    for label,pairs in groups.items():
        if len(pairs)<30:continue
        qlogs=[a for a,_ in pairs]
        tlogs=[b for _,b in pairs]
        relative=[b-a for a,b in pairs]
        drag=[b-3*a for a,b in pairs]
        result[label]={"observations":len(pairs),
            "qqq_annualized_log_growth":252*mean(qlogs),
            "tqqq_annualized_log_growth":252*mean(tlogs),
            "tqqq_minus_qqq_annualized_log_growth":252*mean(relative),
            "tqqq_minus_3x_qqq_annualized_log_tracking_gap":252*mean(drag),
            "higher_geometric_growth_for_tqqq_observed":mean(relative)>0,
            "conditioning_uses_prior_20d_vol_and_prior_200d_trend":True}
    return result


def _bootstrap_pair(a,b,rep=250,seed=8010):
    """Descriptive paired block resampling, explicitly NOT a significance test."""
    delta=[math.log(x/y) for x,y in zip(_daily_returns(a,START_CAPITAL),
                                         _daily_returns(b,START_CAPITAL))]
    # Above log(x/y) uses gross RETURN ratios only if both are >0; fix to
    # actual log(1+return) ratio using the next expression.
    delta=[math.log1p(x)-math.log1p(y)
           for x,y in zip(_daily_returns(a,START_CAPITAL),
                          _daily_returns(b,START_CAPITAL))]
    out={}
    for width in (21,63):
        rng=random.Random(seed+width)
        samples=[]
        n=len(delta)
        for _ in range(rep):
            draw=[]
            while len(draw)<n:
                start=rng.randrange(n-width+1)
                draw.extend(delta[start:start+width])
            samples.append(252*mean(draw[:n]))
        vals=sorted(samples)
        out[str(width)]={"annualized_relative_log_growth_p05":vals[int(.05*(rep-1))],
                         "p50":vals[int(.5*(rep-1))],
                         "p95":vals[int(.95*(rep-1))],
                         "positive_resample_fraction_NOT_P_VALUE":sum(v>0 for v in vals)/len(vals)}
    return out


def evaluate(raw, *, bootstrap_reps=250):
    if raw.get("evidence")!="REAL_QQQ_TQQQ_ADJUSTED_DAILY_OPEN_EXECUTION_PROXY":
        raise ValueError("SOURCE_NOT_OBSERVED")
    rows=raw["daily"]
    if len(rows)<MIN_N:raise ValueError("INSUFFICIENT_OBSERVED_DATES")
    calibration=_calibrate(rows)
    paths={"frozen":_run(rows)}
    frozen=paths["frozen"]
    # Fail closed unless the independently replayed 8.0 daily-open model
    # reproduces the published historical endpoint and deep drawdown.
    recorded=raw["without_contributions"]["strategy"]
    if (abs(frozen["navs"][-1]/recorded["ending_equity"]-1)>0.001
        or abs(frozen["stats"]["max_drawdown"]-recorded["max_drawdown"])>.005):
        raise ValueError("INDEPENDENT_REPLAY_DOES_NOT_MATCH_FROZEN_BASELINE")
    for mode in ("volatility","beta"):
        paths[mode+"_matched_static"]=_run(rows,variant="static_mix",
                    tqqq_weight=calibration[mode]["tqqq_weight"])
    paths["qqq_static"]=_run(rows,variant="static_mix",tqqq_weight=0.)
    paths["tqqq_static"]=_run(rows,variant="static_mix",
                             tqqq_weight=TARGET_INVESTED_FRACTION)
    for mode in VARIANTS[1:]:
        paths[mode]=_run(rows,variant=mode)
    split_results={}
    for label,(start,end) in SPLITS.items():
        subset=[r for r in rows if start<=r["date"]<=end]
        if len(subset)<300:raise ValueError("SPLIT_TOO_SMALL:"+label)
        vals={}
        for name in paths:
            if name=="qqq_static":val=_run(subset,variant="static_mix",tqqq_weight=0.)
            elif name=="tqqq_static":val=_run(subset,variant="static_mix",tqqq_weight=TARGET_INVESTED_FRACTION)
            elif name.endswith("_matched_static"):
                key=name.replace("_matched_static","")
                val=_run(subset,variant="static_mix",tqqq_weight=calibration[key]["tqqq_weight"])
            else:val=_run(subset,variant=name)
            vals[name]=val["stats"]
        sl=vals["frozen"]
        for name,v in vals.items():
            v["vs_frozen_cagr_pp"]=100*(v["cagr"]-sl["cagr"])
            v["vs_frozen_drawdown_pp"]=100*(v["max_drawdown"]-sl["max_drawdown"])
        split_results[label]=vals
    growth=[s["s"] for s in rows]
    qqq=[s["q"] for s in rows]
    relative={}
    for label,(start,end) in {**SPLITS,"full":(rows[0]["date"],rows[-1]["date"])}.items():
        subset=[r for r in rows if start<=r["date"]<=end]
        relative[label]=_hac_alpha(_daily_returns([r["s"] for r in subset]),
                                   _daily_returns([r["q"] for r in subset]),lag=21)
    # All historical sensitivity variants are predeclared (not fitted to outcome).
    stress=[]
    for mode in VARIANTS:
        for lag in (0,1,2):
            for total_slip in (10.,20.,30.):
                s=_run(rows,variant=mode,lag=lag,slip_bps=total_slip)
                stress.append({"variant":mode,"signal_delay_sessions":lag,
                               "slippage_per_side_bps":total_slip,
                               "cagr":s["stats"]["cagr"],
                               "max_drawdown":s["stats"]["max_drawdown"],
                               "intervention_sessions":s["intervention_sessions"]})
    # Paired risk-matched bootstrap resamples a previously selected history.
    block=_bootstrap_pair(paths["frozen"]["navs"],
                          paths["volatility_matched_static"]["navs"],
                          rep=bootstrap_reps)
    result={"schema_version":1,"status":"RESEARCH_COMPLETE_NOT_LIVE_READY",
        "kind":"RISK_MATCHED_FALSIFICATION_OBSERVED_ETF_OPEN_PROXY",
        "source":"docs/portal-history.json","source_snapshot_sha256":raw.get("snapshot_sha256"),
        "source_report_content_sha256":raw.get("report_content_sha256"),
        "period":raw["period"],"capital_deployment_authorized":False,
        "automatic_model_change":False,"frozen_stocklens_8_mutated":False,
        "independent_vendor_fills_verified":False,"original_lean_inputs_verified":False,
        "historically_pristine_holdout":False,
        "risk_match_calibrated_only_on":SPLITS["development"],
        "benchmark_calibration":calibration,
        "full_period_results":{name:x["stats"] for name,x in paths.items()},
        "split_results":split_results,"alpha_hac_vs_qqq_zero_cash_rate":relative,
        "risk_matched_relative_log_bootstrap_NOT_P_VALUE":block,
        "observed_tqqq_geometric_growth_by_prior_regime":_regimes(rows),
        "volatility_overlay_execution_cost_and_lag_stress":stress,
        "predeclared_variants":{
            "frozen":"StockLens 8.0 untouched, modelled daily open executions with whole shares",
            "vol_tiers":"Previous 20 completed QQQ close returns realized volatility annualized >=32% cap2, >=42% cap1.25",
            "five_day_shock":"Any past 5-trading-day QQQ close decline at least 7% within previous 5 sessions cap2",
            "combined":"The lesser cap of volatility and shock; never increases frozen level"},
        "model_limits":["Yahoo observed adjusted daily ETF Open/Close, NOT original raw LEAN, NBBO or true broker fills.",
            "2018-2022 and 2023-2026 have been examined during model development; NOT untouched independent OOS.",
            "Static benchmark weight uses 2010-2017 development, matched by volatility or beta approximately.",
            "Static ETF weights monthly rebalanced at observed adjusted daily open, brokerage fees/slippage MODELLED.",
            "HAC alpha is relative to QQQ only and cannot prove independent alpha or correct multiple model selection.",
            "21/63 session moving-block intervals are descriptive and NOT p-values.",
            "Overlay scenarios are historical exploratory work; no automatic winner selection or capital promotion."]}
    return result


def markdown(result):
    metric=lambda x:f"{100*x:.2f}%"
    f=result["full_period_results"]["frozen"]
    vol=result["full_period_results"]["volatility_matched_static"]
    beta=result["full_period_results"]["beta_matched_static"]
    q=result["full_period_results"]["qqq_static"]
    h=result["alpha_hac_vs_qqq_zero_cash_rate"]["full"]
    lines=["# StockLens 8.0 — שתי שאלות המחקר (תוצאת סימולציה, לא מסחר חי)",
           "",f'חלון: {result["period"]["start"]} עד {result["period"]["end"]}. מקור: Yahoo QQQ/TQQQ נצפים; ביצוע מדומה בשער Open יומי עם עמלות והחלקה.',
           "",
           "## 1. האם היתרון הוא מעבר לחשיפה למינוף וסיכון?",
           "",
           "| מסלול | CAGR | MaxDD | תנודתיות שנתית |",
           "|---|---:|---:|---:|"]
    for name,z in [("StockLens 8.0",f),("QQQ (+cash)",q),
                   ("התאמת תנודתיות 2010–17",vol),("התאמת בטא 2010–17",beta)]:
        lines.append(f'| {name} | {metric(z["cagr"])} | {metric(z["max_drawdown"])} | {metric(z["annualized_volatility"])} |')
    lines+=["",f'רגרסיה יומית מול QQQ: בטא {h["beta_to_qqq"]:.2f}, אלפא אריתמטית שנתית {metric(h["annualized_arithmetic_alpha"])}; סטטיסטי t מסוג HAC-21 = {h["alpha_t_statistic_not_selection_corrected"]:.2f}. **לא מתוקן לבחירת מודל, לא הוכחת אלפא.**',
            "","## 2. האם ההגנות מפחיתות ירידות בלי להרוס את התשואה?","",
            "| מנגנון | CAGR | MaxDD | שינוי CAGR לעומת קפוא | שינוי MaxDD |",
            "|---|---:|---:|---:|---:|"]
    for name in VARIANTS:
        z=result["full_period_results"][name]
        lines.append(f'| {name} | {metric(z["cagr"])} | {metric(z["max_drawdown"])} | {100*(z["cagr"]-f["cagr"]):+.2f} נק׳ | {100*(z["max_drawdown"]-f["max_drawdown"]):+.2f} נק׳ |')
    lines+=["","## העברה בין תקופות", ""]
    for period,vals in result["split_results"].items():
        fr=vals["frozen"];lines.append(f'**{period}** — קפוא: CAGR {metric(fr["cagr"])}, MaxDD {metric(fr["max_drawdown"])}.')
        for name in VARIANTS[1:]:
            r=vals[name]
            lines.append(f'- {name}: שינוי CAGR {r["vs_frozen_cagr_pp"]:+.2f} נק׳; שינוי MaxDD {r["vs_frozen_drawdown_pp"]:+.2f} נק׳')
    lines+=["","## גבולות המסקנה","",
             "- כל התקופות **נבדקו בעבר**. גם חלון שנקרא validation אינו holdout נקי לאחר שהחוקרים כבר בחנו אותו.",
             "- מסחר מדומה במחירי ETF של Yahoo ו־Open יומי ≠ הוראות מלאות ב־09:31/09:32, ספר פקודות, או מילויי ברוקר.",
             "- התאמת סיכון הוגדרה רק על בסיס 2010–2017; גם הערכת האלפא ומובהקות אינן מתקנות חיפוש אסטרטגיות קודם.",
             "- 8.0 קפואה, אין קידום מנגנון הגנה, אין הרשאת מסחר בכסף אמיתי.",
             ""]
    return "\n".join(lines)


def build(out=OUT, report=REPORT):
    a=evaluate(load())
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    Path(report).parent.mkdir(parents=True,exist_ok=True)
    Path(out).write_text(json.dumps(a,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    Path(report).write_text(markdown(a),encoding="utf-8")
    compact={"status":a["status"],"full":{k:{"cagr":v["cagr"],"maxdd":v["max_drawdown"],
        "vol":v["annualized_volatility"]} for k,v in a["full_period_results"].items()},
        "alpha":a["alpha_hac_vs_qqq_zero_cash_rate"]["full"],
        "split_overlay":{k:{n:{"cagr_delta_pp":v[n]["vs_frozen_cagr_pp"],
            "dd_improvement_pp":v[n]["vs_frozen_drawdown_pp"]} for n in VARIANTS[1:]}
                         for k,v in a["split_results"].items()}}
    print("TWO_QUESTIONS_RESEARCH_RESULT="+json.dumps(compact,sort_keys=True))
    print(f"RESULT_JSON={out} RESULT_MARKDOWN={report}")
    return a


if __name__=="__main__":
    build()
