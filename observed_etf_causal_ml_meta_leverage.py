"""Research-only walk-forward ML meta-exposure on REAL observed QQQ/TQQQ.

Fits a FIXED ridge model to next-5-session observable ETF relative OPEN-to-CLOSE
growth; training labels are embargoed and fully completed before each monthly
refit. Decisions for trade session t consume ONLY information at t-1 close.
Model never replaces/edits frozen StockLens 8.0 and never trades at a broker.

All historical evaluation periods have been repeatedly inspected in prior
StockLens studies: a walk-forward *execution* is NOT a pristine OOS discovery.
Do not promote any candidate based on this research or a green CI.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from observed_etf_two_question_audit import (
    load, START_CAPITAL, FEE_BPS, _metrics, _prices,
    _run as frozen_reference
)
from stocklens.core import TARGET_INVESTED_FRACTION, weights_for_leverage
from tradable_tqqq_execution_comparison import _rebalance, _mark

OUT = Path("research/results/ml_meta_leverage_walkforward.json")
REPORT = Path("research/reports/ml_meta_leverage_walkforward.md")
FEATURE_NAMES = (
    "qqq_log_mom5", "qqq_log_mom20", "qqq_log_mom63",
    "qqq_realized_vol20", "qqq_realized_vol63", "qqq_sma200_gap",
    "qqq_drawdown63", "tqqq_minus_qqq_log_mom20",
    "qqq_overnight_gap5"
)
HORIZON = 5
TRAIN_SESSIONS = 756
EMBARGO = 5
RANDOMNESS = "NONE_RIDGE_CLOSED_FORM"
RIDGE_PENALTY = 20.
THRESHOLD = .005  # fixed predicted 5-session relative log growth >+/-0.5%
FIRST_TEST = "2018-01-02"
LAST_TEST = "2026-10-09"
WARMUP = 253
MODES = ("frozen", "ml_ups", "ml_down", "ml_both", "simple_momentum_up")
LAGS = (0, 1)
SLIPPAGE_BPS = (10., 20., 30.)
SPLITS = {
    "2018_2022_reused": ("2018-01-02","2022-12-30"),
    "2023_2026_reused": ("2023-01-03","2026-10-09")
}


def feature_at(rows, i):
    """Input to order at OPEN i; last observed QQQ/TQQQ CLOSE is i-1.

    Yahoo adjusted real price observations; never 'future' i open/close.
    """
    if i < WARMUP:
        raise ValueError("INSUFFICIENT_PRIOR_COMPLETED_FEATURES")
    q=np.asarray([float(r["qc"]) for r in rows[i-254:i]],dtype=float)
    t=np.asarray([float(r["tc"]) for r in rows[i-254:i]],dtype=float)
    if len(q)!=254 or len(t)!=254 or np.any(q<=0) or np.any(t<=0):
        raise ValueError("NONPOSITIVE_PAST_MARKET_INPUT")
    rets=np.diff(np.log(q))
    def rv(n):
        return float(np.std(rets[-n:],ddof=1)*math.sqrt(252.))
    gaps=[]
    for j in range(i-5,i):
        previous=float(rows[j-1]["qc"])
        today=float(rows[j]["qo"])
        if previous<=0 or today<=0:
            raise ValueError("NONPOSITIVE_PRIOR_OVER_NIGHT_GAP")
        gaps.append(math.log(today/previous))
    f=[
        math.log(q[-1]/q[-6]),
        math.log(q[-1]/q[-21]),
        math.log(q[-1]/q[-64]),
        rv(20),
        rv(63),
        q[-1]/float(np.mean(q[-200:]))-1.,
        q[-1]/float(np.max(q[-63:]))-1.,
        math.log(t[-1]/t[-21])-math.log(q[-1]/q[-21]),
        sum(gaps)/len(gaps),
    ]
    if len(f)!=len(FEATURE_NAMES) or not all(math.isfinite(x) for x in f):
        raise ValueError("INVALID_COMPLETED_SESSION_FEATURES")
    return np.asarray(f,dtype=float)


def forward_label(rows, j, horizon=HORIZON):
    """Log excess of real TQQQ over QQQ, OPEN j -> CLOSE j+horizon-1.

    The label is not observable until the END of trading day j+horizon-1.
    No synthetic triple leverage; no hypothetically executable intraday quote.
    """
    if j<0 or j+horizon>len(rows):
        raise ValueError("FUTURE_LABEL_NOT_YET_AVAILABLE")
    r0,r1=rows[j],rows[j+horizon-1]
    for key in ("to","qo"):
        if float(r0[key])<=0:
            raise ValueError("NONPOSITIVE_REAL_ETF_OPEN")
    for key in ("tc","qc"):
        if float(r1[key])<=0:
            raise ValueError("NONPOSITIVE_REAL_ETF_CLOSE")
    return math.log(float(r1["tc"])/float(r0["to"]))-math.log(
        float(r1["qc"])/float(r0["qo"]))


def _fit_ridge(X,y,latest_features):
    """Intercept unpenalized; means/std fitted on TRAINING rows only."""
    if len(X)<30 or X.shape[1]!=len(FEATURE_NAMES):
        raise ValueError("INSUFFICIENT_TRAINING_ROWS")
    x_mean=np.mean(X,axis=0)
    std=np.std(X,axis=0)
    std=np.maximum(std,1e-8)
    Z=np.clip((X-x_mean)/std,-5.,5.)
    ym=float(np.mean(y))
    centered=y-ym
    beta=np.linalg.solve(Z.T@Z+RIDGE_PENALTY*np.eye(Z.shape[1]),Z.T@centered)
    def predict(feature):
        standardized=np.clip((feature-x_mean)/std,-5.,5.)
        return float(ym+standardized@beta)
    return predict, {"train_mean_target":ym,
                     "coefficients_standardized":dict(zip(FEATURE_NAMES,map(float,beta)))}


def walkforward(rows, *, start=FIRST_TEST, train_min=TRAIN_SESSIONS,
                train_window=TRAIN_SESSIONS, embargo=EMBARGO,
                horizon=HORIZON):
    """Monthly rolling ridge fit; embargo excludes near-boundary labels.

    For model fitted as-of trade day i, latest training signal j <=
    i-(horizon+embargo), with last label close j+horizon-1 <= i-embargo-1.
    Hence even the most recent training LABEL finished >=5 sessions ago.
    Every scored x_i reads ONLY market history through close i-1.
    """
    if horizon!=HORIZON or embargo!=EMBARGO:
        raise ValueError("UNREGISTERED_HORIZON_OR_EMBARGO")
    if train_min<30 or train_window<train_min:
        raise ValueError("INVALID_TRAIN_WINDOW")
    dates=[r["date"] for r in rows]
    if dates!=sorted(set(dates)):
        raise ValueError("FUTURE_OR_DUPLICATE_OBSERVED_SESSIONS")
    for r in rows:
        if r.get("signal","") >= r["date"] or r.get("l") not in (0,1.25,2,3):
            raise ValueError("LOOKAHEAD_OR_MUTATED_FROZEN_LEVEL")
    indices=[i for i,d in enumerate(dates) if d>=start]
    if not indices or indices[0]<WARMUP+train_min+horizon+embargo:
        raise ValueError("NOT_ENOUGH_PRIOR_TRAINING_BEFORE_TEST")
    fx=[None]*len(rows)
    y=[None]*len(rows)
    for j in range(WARMUP,len(rows)):
        fx[j]=feature_at(rows,j)
        if j+HORIZON<=len(rows):
            y[j]=forward_label(rows,j)
    predictions=[None]*len(rows)
    train_baselines=[None]*len(rows)
    diagnostics=[]
    pred=None
    fit_meta={}
    previous_month=None
    for i in indices:
        month=dates[i][:7]
        if month!=previous_month:
            # Last label's market close is strictly before this model's
            # earliest eligible decision, plus five-session embargo.
            upper=i-(HORIZON+embargo)
            lower=max(WARMUP,upper-train_window+1)
            keep=[j for j in range(lower,upper+1)
                  if fx[j] is not None and y[j] is not None]
            if len(keep)<train_min:
                raise ValueError("TOO_FEW_MATURED_LABELS")
            X=np.stack([fx[j] for j in keep])
            Y=np.asarray([y[j] for j in keep],dtype=float)
            pred,fit_meta=_fit_ridge(X,Y,fx[i])
            assert keep[-1]+HORIZON-1<=i-embargo-1
            diagnostics.append({
                "fit_date":dates[i],
                "first_training_signal":dates[keep[0]],
                "last_training_signal":dates[keep[-1]],
                "last_completed_training_label_date":dates[keep[-1]+HORIZON-1],
                "label_embargo_sessions":embargo,
                "training_count":len(keep),
                "train_mean_5session_excess":fit_meta["train_mean_target"],
                "coefficient_norm":float(np.linalg.norm(
                    np.asarray(list(fit_meta["coefficients_standardized"].values())))),
            })
        prediction=pred(fx[i])
        if not math.isfinite(prediction):
            raise ValueError("INVALID_PREDICTION")
        predictions[i]=prediction
        train_baselines[i]=fit_meta["train_mean_target"]
        previous_month=month
    return {
        "predictions":predictions,
        "training_mean_predictions":train_baselines,
        "features":fx,
        "labels":y,
        "fits":diagnostics,
        "first_test_index":indices[0],
        "first_test_date":dates[indices[0]],
        "last_test_date":dates[indices[-1]]
    }


def candidate_level(frozen, pred, features, mode):
    """No leverage >3x, no ML override of the frozen cash defense."""
    if mode not in MODES:
        raise ValueError("UNREGISTERED_ML_CHALLENGER")
    if frozen not in (0.,1.25,2.,3.):
        raise ValueError("INVALID_FROZEN_TARGET")
    if mode=="frozen" or frozen==0 or pred is None:
        return frozen
    if mode=="simple_momentum_up":
        if features is not None and features[1]>.05 and features[3]<.28:
            return {1.25:2.,2.:3.,3.:3.}[frozen]
        return frozen
    if not math.isfinite(pred):
        raise ValueError("NONFINITE_ML_PREDICTION")
    if mode in ("ml_ups","ml_both") and pred>THRESHOLD:
        return {1.25:2.,2.:3.,3.:3.}[frozen]
    if mode in ("ml_down","ml_both") and pred< -THRESHOLD:
        return {1.25:1.25,2.:1.25,3.:2.}[frozen]
    return frozen


def simulate(rows, wf, *, mode="frozen", lag=0, slip=10.):
    if mode not in MODES or lag not in LAGS or slip not in SLIPPAGE_BPS:
        raise ValueError("UNREGISTERED_MODE_LAG_OR_COST")
    if len(rows)!=len(wf["predictions"]):
        raise ValueError("INVALID_WALKFORWARD_LENGTH")
    p={"cash":START_CAPITAL,"shares":{"QQQ":0,"TQQQ":0},
       "fees":0.,"slippage":0.,"trades":0,"turnover_notional":0.}
    navs=[]
    levels=[]
    previous_target=None
    interventions=0
    upshifts=0
    downshifts=0
    first=wf["first_test_index"]
    for i,r in enumerate(rows):
        frozen=float(r["l"])
        sourceidx=i-lag
        signal=(wf["predictions"][sourceidx]
                if sourceidx>=first and mode!="frozen" else None)
        signal_features=(wf["features"][sourceidx]
                         if sourceidx>=first else None)
        lev=candidate_level(frozen,signal,signal_features,mode)
        if lev not in (0.,1.25,2.,3.) or (frozen==0 and lev!=0):
            raise ValueError("CHALLENGER_ESCAPED_FROZEN_DEFENSE_OR_LEVERAGE_LIMIT")
        interventions+=int(lev!=frozen)
        upshifts+=int(lev>frozen)
        downshifts+=int(lev<frozen)
        q,t=weights_for_leverage(lev)
        weights={"QQQ":q*TARGET_INVESTED_FRACTION if lev else 0.,
                 "TQQQ":t*TARGET_INVESTED_FRACTION if lev else 0.}
        prices=_prices(r)
        if previous_target is None or lev!=previous_target:
            _rebalance(p,prices,weights,FEE_BPS,slip)
        net=_mark(p,prices,"close")
        if not math.isfinite(net) or net<=0 or p["cash"]<-.00001:
            raise ValueError("ML_CHALLENGER_ACCOUNT_INSOLVENT")
        navs.append(net)
        levels.append(lev)
        previous_target=lev
    return {
        "navs":navs,
        "levels":levels,
        "stats":_metrics(navs,[r["date"] for r in rows]),
        "trades":p["trades"],
        "modeled_fees":p["fees"],
        "modeled_slippage":p["slippage"],
        "intervention_sessions":interventions,
        "upshift_sessions":upshifts,
        "downshift_sessions":downshifts,
        "real_broker_fills_observed":False
    }


def period_stats(rows, navs, start, end):
    ix=[i for i,r in enumerate(rows) if start<=r["date"]<=end]
    if len(ix)<100:
        raise ValueError("INSUFFICIENT_COMPARABLE_TEST_WINDOW")
    i,j=ix[0],ix[-1]
    initial=navs[i-1] if i else START_CAPITAL
    return _metrics(navs[i:j+1],[r["date"] for r in rows[i:j+1]],first=initial)


def _forecast_score(rows, wf, start, end):
    indices=[i for i,r in enumerate(rows)
             if start<=r["date"]<=end
             and wf["labels"][i] is not None and wf["predictions"][i] is not None]
    if len(indices)<100:
        raise ValueError("INSUFFICIENT_MATURED_TEST_LABELS")
    forecast=np.asarray([wf["predictions"][i] for i in indices])
    base=np.asarray([wf["training_mean_predictions"][i] for i in indices])
    y=np.asarray([wf["labels"][i] for i in indices])
    err=float(np.mean((forecast-y)**2))
    base_err=float(np.mean((base-y)**2))
    if base_err<=0:
        raise ValueError("ZERO_BASELINE_FORECAST_MSE")
    cc=float(np.corrcoef(forecast,y)[0,1]) if np.std(forecast)>0 and np.std(y)>0 else None
    return {
        "matured_labels":len(indices),
        "R2_vs_past_training_mean":1.-err/base_err,
        "mean_square_error":err,
        "mean_square_error_no_ml_training_mean":base_err,
        "prediction_outcome_correlation_descriptive":cc,
        "positive_outcome_fraction":float(np.mean(y>0)),
        "forecast_positive_fraction":float(np.mean(forecast>0)),
        "overlapping_5session_outcomes_not_iid":True,
    }


def evaluate(raw, *, include_curves=False):
    if raw.get("evidence")!="REAL_QQQ_TQQQ_ADJUSTED_DAILY_OPEN_EXECUTION_PROXY":
        raise ValueError("NOT_REAL_ADJUSTED_ETF_PROXY")
    if raw.get("live_trading_authorized") is not False:
        raise ValueError("SOURCE_INAPPROPRIATELY_AUTHORIZED_LIVE")
    rows=raw["daily"]
    if rows[-1]["date"]!=LAST_TEST or rows[0]["date"]!="2010-02-11":
        raise ValueError("PINNED_HISTORICAL_COHORT_DRIFT")
    wf=walkforward(rows)
    baseline=simulate(rows,wf)
    ref=frozen_reference(rows,variant="frozen")
    if len(baseline["navs"])!=len(ref["navs"]):
        raise ValueError("FROZEN_REFERENCE_LENGTH_CHANGED")
    residual=max(abs(a-b)/b for a,b in zip(baseline["navs"],ref["navs"]))
    if residual>2e-10:
        raise ValueError("ML_BASELINE_DAILY_NAV_RECONCILIATION_FAILED")
    named={}
    for mode in MODES:
        a=baseline if mode=="frozen" else simulate(rows,wf,mode=mode)
        named[mode]=a
    stress=[]
    for mode in MODES:
        for lag in LAGS:
            for slip in SLIPPAGE_BPS:
                cur=(named[mode] if lag==0 and slip==10.
                     else simulate(rows,wf,mode=mode,lag=lag,slip=slip))
                stress.append({
                    "mode":mode,"signal_delay_sessions":lag,
                    "modeled_slippage_bps_per_side":slip,
                    "full_cagr":cur["stats"]["cagr"],
                    "full_max_drawdown":cur["stats"]["max_drawdown"],
                    "ending_equity":cur["stats"]["ending_equity"],
                    "test_cagr":period_stats(rows,cur["navs"],FIRST_TEST,LAST_TEST)["cagr"],
                    "model_trades":cur["trades"],
                    "upshift_sessions":cur["upshift_sessions"],
                    "downshift_sessions":cur["downshift_sessions"]
                })
    split={}
    for label,(a,b) in SPLITS.items():
        base=period_stats(rows,baseline["navs"],a,b)
        split[label]={
            "frozen":base,
            **{mode:period_stats(rows,named[mode]["navs"],a,b)
               for mode in MODES if mode!="frozen"}
        }
        for mode in MODES[1:]:
            split[label][mode]["cagr_delta_pp"] = 100*(
                split[label][mode]["cagr"]-base["cagr"])
            split[label][mode]["maxdd_improvement_pp"] = 100*(
                split[label][mode]["max_drawdown"]-base["max_drawdown"])
    score={
        name:_forecast_score(rows,wf,*bounds)
        for name,bounds in {
            **SPLITS,"all_test_reused":(FIRST_TEST,LAST_TEST)
        }.items()
    }
    # Historical continuation screen declared before seeing THIS ML batch
    # (all epochs have been previously inspected in other research). It is
    # NEVER an investability gate. Require both prediction and execution edge.
    gates={}
    for mode in MODES[1:]:
        good=[]
        for lag in LAGS:
            for slip in (10.,20.):
                challenger=next(x for x in stress
                    if x["mode"]==mode and x["signal_delay_sessions"]==lag
                    and x["modeled_slippage_bps_per_side"]==slip)
                frozen=next(x for x in stress
                    if x["mode"]=="frozen" and x["signal_delay_sessions"]==lag
                    and x["modeled_slippage_bps_per_side"]==slip)
                good.append(challenger["test_cagr"]-frozen["test_cagr"]>=.01
                    and challenger["full_max_drawdown"]-frozen["full_max_drawdown"]>=-.01)
        gate=(all(good)
              and all(score[x]["R2_vs_past_training_mean"]>0 for x in SPLITS)
              and all(split[x][mode]["cagr_delta_pp"]>0 for x in SPLITS))
        gates[mode]={
            "passed_cost_and_lag_cases":sum(good),"required_cases":4,
            "both_reused_eras_positive_test_cagr":all(
                split[x][mode]["cagr_delta_pp"]>0 for x in SPLITS),
            "prediction_outperformed_no_ml_mean_on_both_reused_eras":all(
                score[x]["R2_vs_past_training_mean"]>0 for x in SPLITS),
            "historical_research_continuation_screen":gate,
            "automatic_strategy_change":False,
            "capital_authorization":False
        }
    r={
        "schema_version":1,"kind":"FROZEN8_CAUSAL_MONTHLY_WALKFORWARD_RIDGE_META_LEVERAGE",
        "status":"HISTORICAL_HYPOTHESIS_SCREEN_NOT_CLEAN_OOS",
        "source":"docs/portal-history.json",
        "source_price_sha256":raw.get("snapshot_sha256"),
        "period":raw["period"],
        "test_window":{"start":FIRST_TEST,"end":LAST_TEST,
                       "session_count":sum(row["date"]>=FIRST_TEST for row in rows),
                       "previously_reused_in_StockLens_research":True},
        "model":{"estimator":"numpy_linear_ridge_closed_form",
                 "randomness":RANDOMNESS,"predictand":
                 "real observed TQQQ minus QQQ 5-session OPEN-to-CLOSE relative log growth",
                 "features_prior_completed_close_only":list(FEATURE_NAMES),
                 "training_rows":TRAIN_SESSIONS,"forward_label_horizon_sessions":HORIZON,
                 "train_label_embargo_sessions":EMBARGO,
                 "refit":"FIRST TRADING SESSION OF MONTH ONLY",
                 "ridge_penalty":RIDGE_PENALTY,"predicted_excess_trigger":THRESHOLD,
                 "max_gross_leverage":3.,"frozen_zero_defense_absolute":True,
                 "cost_and_signal_delay_grids":{"lags":list(LAGS),
                   "slippage_per_side_bps":list(SLIPPAGE_BPS)}},
        "monthly_training_provenance":wf["fits"],
        "monthly_fit_count":len(wf["fits"]),
        "baseline_daily_nav_verified_equal_to_frozen":True,
        "max_relative_baseline_NAV_difference":residual,
        "forecast_skill":score,
        "full_period_stats":{m:{k:v for k,v in x.items() if k!="navs" and k!="levels"}
                             for m,x in named.items()},
        "test_period_stats":{m:period_stats(rows,x["navs"],FIRST_TEST,LAST_TEST)
                             for m,x in named.items()},
        "reused_era_continuous_nav_splits":split,
        "cost_and_additional_delay_stress":stress,
        "historical_continuation_screen":gates,
        "actual_ETF_prices_used_without_synthetic_TQQQ":True,
        "real_order_fills_observed":False,
        "fully_original_lean_same_minute_portfolio_comparison_proven":False,
        "pristine_oos_or_selection_corrected_statistical_edge_proven":False,
        "frozen_8_code_or_shadow_signal_modified":False,
        "automatic_model_promotion":False,
        "capital_deployment_authorized":False,
        "disclaimers":[
            "Both 2018-2022 and 2023-2026 have been repeatedly inspected by StockLens researchers: NOT untouched holdout.",
            "All training labels mature before monthly model fit with full 5-session horizon plus 5-session embargo.",
            "5-session overlapping next-open relative excess target is NOT an independent daily label, so standard iid inference is invalid.",
            "Decisions executed at MODELED next daily Yahoo-adjusted OPEN, whole shares, 2bps commission and 10/20/30bps synthetic modeled slippage, not actual 09:31/09:32 broker fills.",
            "Only observed adjusted QQQ and TQQQ ETFs used; continuous source adjustment can be retrospectively revised.",
            "Model complexity and experiment family selection bias still unquantified; no claims of significant alpha or reliable future 40% return.",
            "No live inference, broker API actions, production state or frozen 8.0 changes. ML research is an isolated diagnostic."
        ]
    }
    if include_curves:
        r["debug_nonpublic_daily_strategy_curves"]={m:x["navs"] for m,x in named.items()}
    return r


def human_report(r):
    pp=lambda x:f"{100*x:.2f}%"
    base=r["test_period_stats"]["frozen"]
    lines=["# StockLens 8.0: walk-forward ML meta-leverage research (frozen)",
      "","**This is previously inspected historical data, not a clean out-of-sample investment test.**",
      "No model promotion, no broker fills, no synthetic TQQQ. Original 8.0 unchanged.",
      "", "## Operational method", "",
      "Monthly, expanding calendar-forward ridge fit uses 756 prior fully-matured 5-day labels,",
      "plus a five-session embargo. Scores at next OPEN only use information through previous CLOSE.",
      "Modes: frozen; ML-up one target tier; ML-down one tier; ML-symmetric;",
      "simple past 20d QQQ momentum + volatility heuristic control. All remain at or below 3x",
      "and always preserve frozen 0x defense. Fee 2bps plus 10/20/30bps modeled slip.",
      "",f'Monthly fits: {r["monthly_fit_count"]}. Test {r["test_window"]["start"]} to {r["test_window"]["end"]}.',
      "", "## Continuous-compounding test window",
      "| Mode | 2018-26 CAGR | MaxDD in test window | ΔCAGR pp vs frozen | Full-history trades | Interventions |",
      "|---|---:|---:|---:|---:|---:|"]
    for m in MODES:
        x=r["test_period_stats"][m]
        full=r["full_period_stats"][m]
        lines.append(f'| {m} | {pp(x["cagr"])} | {pp(x["max_drawdown"])} | '
                     f'{100*(x["cagr"]-base["cagr"]):+.2f} | '
                     f'{full["trades"]} | {full["intervention_sessions"]} |')
    lines+=["", "## Predictor sanity vs causal prior training-mean forecast",
            "| Previously inspected period | Ridge OOS-by-clock R² vs prior mean | observed labels |",
            "|---|---:|---:|"]
    for name,item in r["forecast_skill"].items():
        lines.append(f'| {name} | {item["R2_vs_past_training_mean"]:.4f} | {item["matured_labels"]} |')
    lines+=["","## Split stability (without portfolio NAV restart)",
            "| Mode | 2018–22 ΔCAGR pp | 2023–26 ΔCAGR pp |",
            "|---|---:|---:|"]
    for m in MODES[1:]:
        lines.append(f'| {m} | {r["reused_era_continuous_nav_splits"]["2018_2022_reused"][m]["cagr_delta_pp"]:+.2f} | '
                     f'{r["reused_era_continuous_nav_splits"]["2023_2026_reused"][m]["cagr_delta_pp"]:+.2f} |')
    lines+=["","## Cost/lag falsification",
            "Historical research continuation requires all four scenarios lag0/1 x 10/20bps:",
            ">=1 CAGR percentage point versus matched frozen and <=1pp MaxDD deterioration,",
            "PLUS positive forecast improvement versus baseline mean in both reused eras.",
            "Even historical continuation does not authorize deployment."]
    for name,g in r["historical_continuation_screen"].items():
        lines.append(f'- {name}: {g["passed_cost_and_lag_cases"]}/4 cases; '
                     f'predictor better both eras={g["prediction_outperformed_no_ml_mean_on_both_reused_eras"]}; '
                     f'historical continuation={g["historical_research_continuation_screen"]}; '
                     'automatic promotion=FALSE.')
    lines+=["","## Why ML can look good and still fail",
            "- Feature inputs and training labels are strictly time-ordered but ALL evaluated years are reused research data.",
            "- A 5-session overlapping target is strongly serially dependent; do not compute naive p-values.",
            "- Forecast correlation and R² do NOT prove net risk-adjusted excess returns.",
            "- Every model is just one historical hypothesis, not an investable champion.",
            "- Production code frozen, live trades/capital permission off.",
            ""]
    return "\n".join(lines)


def build(out=OUT, report=REPORT):
    data=evaluate(load())
    out=Path(out); report=Path(report)
    out.parent.mkdir(parents=True,exist_ok=True)
    report.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    report.write_text(human_report(data)+"\n")
    brief={"status":data["status"],"period":data["period"],
        "test_base":data["test_period_stats"]["frozen"],
        "test_cagr_by_mode":{k:{"cagr":v["cagr"],
              "max_drawdown":v["max_drawdown"]}
              for k,v in data["test_period_stats"].items()},
        "r2_by_split":{k:v["R2_vs_past_training_mean"]
                       for k,v in data["forecast_skill"].items()},
        "gates":data["historical_continuation_screen"],
        "monthly_fits":data["monthly_fit_count"],
        "nav_parity":data["baseline_daily_nav_verified_equal_to_frozen"],
        "no_promotions":not data["automatic_model_promotion"]}
    print("STOCKLENS_CAUSAL_ML_RESULT="+json.dumps(brief,sort_keys=True))
    print("OUTPUT_JSON="+str(out)+" OUTPUT_REPORT="+str(report))
    return data


if __name__=="__main__":
    build()
