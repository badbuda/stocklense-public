"""SL9-021: fixed Cboe VIX/VIX3M previous-close term-structure inversion.

Research ONLY. VIX3M is an option-implied 93-day index, NOT a futures
contract, quote, tradable price, historical publication-time certificate
or broker fill. Frozen 8.0 and real observed QQQ/TQQQ ETF price path intact.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen

from observed_etf_two_question_audit import load, _metrics, START_CAPITAL, _prices, SPLITS
from observed_etf_four_challengers_batch import simulate as original_frozen
from observed_vix_prior_session_study import official_acquire as acquire_vix, normalize_csv
from stocklens.core import TARGET_INVESTED_FRACTION, weights_for_leverage
from tradable_tqqq_execution_comparison import _mark, _rebalance

THREE_MONTH_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv"
BASE_SHA = "bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129"
SNAPSHOT = Path("research/private/sl9_021_cboe_vix_vix3m_snapshot.json")
RESULT = Path("research/results/sl9_026_vix3m_two_day_placebo.json")
REPORT = Path("research/reports/sl9_026_vix3m_two_day_placebo.md")
MODES = ("frozen", "two_consecutive_days_cap2")
LAGS = (0, 1)
SLIPPAGE_BPS = (10., 20.)
FEE_BPS = 2.


def acquire_three_month():
    req = Request(THREE_MONTH_URL, headers={
        "Accept": "text/csv", "User-Agent": "StockLens-research-source-validation/1.0"})
    with urlopen(req, timeout=25) as resp:
        body = resp.read(3_000_001)
    if len(body) > 3_000_000:
        raise ValueError("TERM_CSV_TOO_LARGE")
    bars = normalize_csv(body.decode("utf-8-sig"))
    return {"series": "CBOE_VIX3M_93_DAY_OPTION_IMPLIED_INDEX",
            "source_url": THREE_MONTH_URL,
            "source_raw_csv_sha256": hashlib.sha256(body).hexdigest(),
            "provider_historical_first_seen_verified": False,
            "provider_revisions_independently_audited": False,
            "bars": [{"date": b["date"], "vix3m_close": b["vix_close"]} for b in bars]}


def _valid_series(source, name, field, days):
    if not isinstance(source, dict) or source.get("series") != name:
        raise ValueError("TERM_BAD_SOURCE_TYPE")
    bars = source.get("bars")
    if not isinstance(bars, list) or not bars:
        raise ValueError("TERM_SOURCE_NO_BARS")
    vals = {}
    previous = ""
    for b in bars:
        day = b.get("date") if isinstance(b, dict) else None
        v = b.get(field) if isinstance(b, dict) else None
        if (not isinstance(day, str) or len(day)!=10 or
            day<=previous or type(v) not in (int,float) or
            not math.isfinite(v) or v<=0 or v>=200):
            raise ValueError("TERM_INVALID_ORDER_OR_PRICE")
        previous = day
        vals[day] = float(v)
    missing = [d for d in days[:-1] if d not in vals]
    if missing:
        raise ValueError("TERM_MISSING_REAL_PREVIOUS_SESSION_INDEX:"+
                         name+":"+str(len(missing))+":"+str(missing[:2]))
    return vals


def validate(source, dates):
    if not isinstance(source,dict) or source.get("schema_version")!=1:
        raise ValueError("TERM_SCHEMA")
    if dates != sorted(set(dates)) or len(dates)<3:
        raise ValueError("TERM_MARKET_CALENDAR")
    if (source.get("baseline_sha256")!=BASE_SHA
       or source.get("provider_first_seen_proven") is not False
       or source.get("futures_curve_observed") is not False
       or source.get("broker_fills_observed") is not False):
        raise ValueError("TERM_UNTRUSTED_PROVENANCE")
    vix = source.get("vix")
    vix3m = source.get("vix3m")
    if (not isinstance(vix,dict) or not isinstance(vix3m,dict) or
        vix.get("source_url")!="https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
        or vix3m.get("source_url")!=THREE_MONTH_URL
        or vix.get("provider_publication_time_independently_verified") is not False
        or vix3m.get("provider_historical_first_seen_verified") is not False):
        raise ValueError("TERM_UNVERIFIED_CBOE_SOURCE_METADATA")
    x = _valid_series(vix,"CBOE_VIX_INDEX_DAILY_CLOSE","vix_close",dates)
    y = _valid_series(vix3m,"CBOE_VIX3M_93_DAY_OPTION_IMPLIED_INDEX","vix3m_close",dates)
    encoded=json.dumps({d:[x[d],y[d]] for d in dates[:-1]},
                       separators=(",",":"),sort_keys=True).encode()
    return x,y,hashlib.sha256(encoded).hexdigest()


def gate_leverage(frozen, a, a3m, b, b3m, mode):
    if frozen not in (0,1.25,2,3) or mode not in MODES:
        raise ValueError("TERM_UNREGISTERED_EXPOSURE")
    if mode=="frozen":return frozen
    if any(type(x) not in (int,float) or not math.isfinite(x) or x<=0
           for x in (a,a3m,b,b3m)):
        raise ValueError("TERM_PRIOR_INDEX_INVALID")
    return min(frozen,2.) if a/a3m>1. and b/b3m>1. else frozen


def simulate(rows,source,*,mode="frozen",lag=0,slip_bps=10.,fee_bps=FEE_BPS,placebo_indices=None):
    if mode not in MODES or lag not in LAGS or (slip_bps not in SLIPPAGE_BPS and not (slip_bps==0. and fee_bps==0.)):
        raise ValueError("TERM_UNREGISTERED_TEST")
    dates=[r["date"] for r in rows]
    x,y,_=validate(source,dates)
    p={"cash": START_CAPITAL, "shares":{"QQQ":0,"TQQQ":0},
       "fees":0.,"slippage":0.,"trades":0,"turnover_notional":0.}
    navs=[]
    previous=None
    hits=0
    for i,row in enumerate(rows):
        if row.get("l") not in (0,1.25,2,3) or row.get("signal","")>=row["date"]:
            raise ValueError("TERM_INVALID_FROZEN_DECISION")
        j=i-lag
        desired=float(rows[j]["l"]) if j>=0 else 0.
        if mode=="frozen":
            actual=desired
        elif placebo_indices is not None:
            # Placebo exposure reduction is applied to EXACTLY K eligible
            # frozen 3x sessions, no VIX information or hindsight.
            actual=min(desired,2.) if i in placebo_indices else desired
        elif j>1:
            a,b=dates[j-2],dates[j-1]
            actual=gate_leverage(desired,x[a],y[a],x[b],y[b],mode)
        else:
            actual=desired  # pre-cohort lookback unavailable
        if actual<desired: hits+=1
        q,t=weights_for_leverage(actual) if actual else (0.,0.)
        weights={"QQQ":q*TARGET_INVESTED_FRACTION,"TQQQ":t*TARGET_INVESTED_FRACTION}
        px=_prices(row)
        if previous is None or abs(previous-actual)>1e-10:
            _rebalance(p,px,weights,fee_bps,slip_bps)
        nav=_mark(p,px,"close")
        if not math.isfinite(nav) or nav<=0 or p["cash"]<-1e-5:
            raise ValueError("TERM_INVALID_NAV")
        navs.append(nav)
        previous=actual
    return {"navs":navs,"dates":dates,"stats":_metrics(navs,dates),
            "trades":p["trades"],"intervention_days":hits}


def _era(path,first,last):
    ids=[i for i,d in enumerate(path["dates"]) if first<=d<=last]
    if not ids:raise ValueError("TERM_ERA_MISSING")
    a,b=ids[0],ids[-1]
    cash=START_CAPITAL if a==0 else path["navs"][a-1]
    return _metrics(path["navs"][a:b+1],path["dates"][a:b+1],first=cash)


def evaluate(market, source):
    if market.get("snapshot_sha256")!=BASE_SHA:
        raise ValueError("TERM_BASE_SOURCE_CHANGED")
    rows=market["daily"]
    x,y,sha=validate(source,[r["date"] for r in rows])
    runs={(m,l,s):simulate(rows,source,mode=m,lag=l,slip_bps=s)
          for m in MODES for l in LAGS for s in SLIPPAGE_BPS}
    for lag in LAGS:
        for slip in SLIPPAGE_BPS:
            a=runs[("frozen",lag,slip)]["navs"]
            b=original_frozen(rows,mode="frozen",lag=lag,slippage_bps=slip)["navs"]
            if len(a)!=len(b) or any(abs(c-d)>1e-5 for c,d in zip(a,b)):
                raise ValueError("TERM_FROZEN_DAY_BY_DAY_NAV_NOT_MATCHED")
    a=runs[("frozen",0,10.)]
    c=runs[("two_consecutive_days_cap2",0,10.)]
    cases=[]
    for lag in LAGS:
        for slip in SLIPPAGE_BPS:
            j=runs[("two_consecutive_days_cap2",lag,slip)]["stats"]
            b=runs[("frozen",lag,slip)]["stats"]
            dc=100*(j["cagr"]-b["cagr"])
            dd=100*(j["max_drawdown"]-b["max_drawdown"])
            cases.append({"lag":lag,"slippage_bps":slip,
                          "cagr_delta_pp":dc,"maxdd_improvement_pp":dd,
                          "passes": dd>=3.0 and dc>=-0.5})
    result = {"schema_version":1,"kind":"CBOE_VIX3M_VIX3M_TWO_CONSECUTIVE_DAYS_RESEARCH",
            "status":"OBSERVED_INDEX_PAST_CLOSE_RESEARCH_ONLY",
            "period":market["period"],
            "baseline_source_sha256":market["snapshot_sha256"],
            "observed_vix3m_prior_sessions":len(rows)-1,
            "historical_join_sha256":sha,
            "baseline":a["stats"],
            "candidate":{"cagr":c["stats"]["cagr"],
                         "max_drawdown":c["stats"]["max_drawdown"],
                         "cagr_delta_pp":100*(c["stats"]["cagr"]-a["stats"]["cagr"]),
                         "maxdd_gain_pp":100*(c["stats"]["max_drawdown"]-a["stats"]["max_drawdown"]),
                         "trades":c["trades"],"intervention_days":c["intervention_days"],
                         "cases":cases,"passes":sum(v["passes"] for v in cases)},
            "frozen_nav_parity_all_cases":True,
            "source_historical_first_seen_proven":False,
            "full_vix3m_futures_contract_quotes_observed":False,
            "historical_qqq_tqqq_actual_etf_bars_not_synthetic":True,
            "historical_holdout_pristine":False,
            "broker_fill_verified":False,
            "capital_deployment_authorized":False,
            "automatic_promotion":False,
            "eras":{name:{"cagr_delta_pp":100*(_era(c,f,t)["cagr"]-_era(a,f,t)["cagr"]),
                          "maxdd_gain_pp":100*(_era(c,f,t)["max_drawdown"]-_era(a,f,t)["max_drawdown"])}
                    for name,(f,t) in SPLITS.items()}}
    import random
    # One ex-ante matched exposure-duty-cycle placebo cohort (not turnover
    # matched; exploratory historical diagnostic, NOT a causal p-value).
    eligible=[i for i,row in enumerate(rows) if float(row["l"])==3.]
    interventions=c["intervention_days"]
    if interventions>len(eligible) or interventions<0:
        raise ValueError("PLACEBO_INVALID_INTERVENTION_DUTY")
    frozen_gross=simulate(rows,source,mode="frozen",slip_bps=0.,fee_bps=0.)
    candidate_gross=simulate(rows,source,mode="two_consecutive_days_cap2",
                             slip_bps=0.,fee_bps=0.)
    observed=100*(candidate_gross["stats"]["cagr"]-frozen_gross["stats"]["cagr"])
    draws=[]
    placebo_trades=[]
    rng=random.Random(20261011)
    for _ in range(1000):
        indices=set(rng.sample(eligible,interventions))
        path=simulate(rows,source,mode="two_consecutive_days_cap2",
                      slip_bps=0.,fee_bps=0.,placebo_indices=indices)
        draws.append(100*(path["stats"]["cagr"]-frozen_gross["stats"]["cagr"]))
        placebo_trades.append(path["trades"])
    p=(1+sum(x>=observed for x in draws))/(1+len(draws))
    result["placebo"]={
       "n_randomizations":1000,
       "seed":20261011,
       "eligible_frozen3x_days":len(eligible),
       "exact_matched_intervention_days":interventions,
       "realized_gross_cagr_delta_pp":observed,
       "placebo_mean_gross_cagr_delta_pp":sum(draws)/len(draws),
       "one_sided_1000_day_permutation_tail_probability_exploratory":p,
       "placebo_median_trade_count":sorted(placebo_trades)[len(placebo_trades)//2],
       "original_challenger_trade_count":c["trades"],
       "turnover_or_episode_structure_matched":False,
       "independent_causal_alpha_p_value_valid":False,
       "sample_selected_before_this_experiment":True,
    }
    result["official_vix3m_zip_source_bytes_sha256"] = "0ff8ef25ee51388e39d53378fad2ba233b8e9e7c5fa55cf765e550a399c77749"
    result["automatic_promotion"]=False
    return result



def build():
    if not SNAPSHOT.is_file():
        raise ValueError("VIX3M_PRIOR_CI_SOURCE_MISSING_NO_REACQUISITION")
    raw=SNAPSHOT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != "0ff8ef25ee51388e39d53378fad2ba233b8e9e7c5fa55cf765e550a399c77749":
        raise ValueError("VIX3M_CBOE_ARCHIVE_CHANGED")
    source=json.loads(raw)
    result=evaluate(load(),source)
    RESULT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    RESULT.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    a,b=result["baseline"],result["candidate"]
    p=result["placebo"]
    REPORT.write_text("# SL9-026 two-day consecutive VIX/VIX3M inverse term challenge\n\n"
        "Retrospective, single preregistered test on reused 2010-2026 real QQQ/TQQQ ETF opening proxy. "
        "Two prior completed Cboe index closes must exceed VIX3M; cap 3x at 2x. "
        "Real ETF source, NOT synthetic TQQQ; Cboe index closes NOT futures/NBBO.\n\n"
        f'Frozen CAGR {a["cagr"]:.6%} MaxDD {a["max_drawdown"]:.6%}; '
        f'candidate CAGR {b["cagr"]:.6%} MaxDD {b["max_drawdown"]:.6%}; '
        f'research gates {b["passes"]}/4; interventions {b["intervention_days"]}.\n\n'
        f'One thousand exact intervention-day-count but NOT turnover/episode-matched placebo '
        f'permutations: gross/CAGR tail probability exploratory {p["one_sided_1000_day_permutation_tail_probability_exploratory"]:.5f}; '
        "NOT a valid corrected causal p-value. No clean holdout. No model promotion.\n")
    print("STOCKLENS_VIX3M_2DAY_RESULT="+json.dumps({
        "candidate":result["candidate"],"baseline":result["baseline"],
        "placebo":result["placebo"],
        "historical_holdout_pristine":False,"promotion":False},sort_keys=True))
    return result


if __name__=="__main__":
    build()
