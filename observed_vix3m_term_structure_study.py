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
RESULT = Path("research/results/sl9_021_vix3m_term_structure.json")
REPORT = Path("research/reports/sl9_021_vix3m_term_structure.md")
MODES = ("frozen", "term_inversion_cap2")
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


def capped_leverage(frozen, vix, vix3m, mode):
    if frozen not in (0,1.25,2,3) or mode not in MODES:
        raise ValueError("TERM_UNREGISTERED_EXPOSURE")
    if mode=="frozen":
        return frozen
    if type(vix) not in (float,int) or type(vix3m) not in (float,int):
        raise ValueError("TERM_PRIOR_OBSERVATION_MISSING")
    if not all(math.isfinite(x) and x>0 for x in (vix,vix3m)):
        raise ValueError("TERM_PRIOR_INDEX_INVALID")
    # One mechanism, no thresholds selected after outcomes.
    return min(frozen,2.) if vix/vix3m >= 1. else frozen


def simulate(rows,source,*,mode="frozen",lag=0,slip_bps=10.):
    if mode not in MODES or lag not in LAGS or slip_bps not in SLIPPAGE_BPS:
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
        if j>0:
            day=dates[j-1]
            actual=capped_leverage(desired,x[day],y[day],mode)
        else:
            actual=desired  # no pre-cohort observed term structure
        if actual<desired: hits+=1
        q,t=weights_for_leverage(actual) if actual else (0.,0.)
        weights={"QQQ":q*TARGET_INVESTED_FRACTION,"TQQQ":t*TARGET_INVESTED_FRACTION}
        px=_prices(row)
        if previous is None or abs(previous-actual)>1e-10:
            _rebalance(p,px,weights,FEE_BPS,slip_bps)
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
    c=runs[("term_inversion_cap2",0,10.)]
    cases=[]
    for lag in LAGS:
        for slip in SLIPPAGE_BPS:
            j=runs[("term_inversion_cap2",lag,slip)]["stats"]
            b=runs[("frozen",lag,slip)]["stats"]
            dc=100*(j["cagr"]-b["cagr"])
            dd=100*(j["max_drawdown"]-b["max_drawdown"])
            cases.append({"lag":lag,"slippage_bps":slip,
                          "cagr_delta_pp":dc,"maxdd_improvement_pp":dd,
                          "passes": dd>=3.0 and dc>=-1.5})
    return {"schema_version":1,"kind":"CBOE_VIX3M_VIX_TERM_INVERSION_FIXED_RESEARCH",
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


def build():
    result={"schema_version":1,"kind":"SL9_021_SOURCE_ACQUISITION_AND_TERM_STRUCTURE",
            "status":"BLOCKED_MISSING_OR_INVALID_OFFICIAL_CBOE_INDEX_DATA",
            "frozen_stocklens_8_changed":False,
            "capital_deployment_authorized":False,
            "automatic_promotion":False,
            "source_historical_first_seen_proven":False}
    market=load()
    try:
        vix=acquire_vix()
        three=acquire_three_month()
        source={"schema_version":1,"baseline_sha256":BASE_SHA,
                "provider_first_seen_proven":False,
                "futures_curve_observed":False,"broker_fills_observed":False,
                "vix":vix,"vix3m":three}
        validate(source,[r["date"] for r in market["daily"]])
        result=evaluate(market,source)
        SNAPSHOT.parent.mkdir(parents=True,exist_ok=True)
        SNAPSHOT.write_text(json.dumps(source,sort_keys=True,separators=(",",":"))+"\n")
    except (ValueError, KeyError, TypeError, OSError, UnicodeError, TimeoutError) as exc:
        result["blocked_reason"]=str(exc)[:250]
    RESULT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    RESULT.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    c=result.get("candidate")
    lines=["# SL9-021: prior-close VIX/VIX3M term-structure fixed challenge","",
           "Status: **"+result["status"]+"**.",
           "The VIX3M index is 93-day SPX option-implied volatility, not",
           "a VIX futures trading series, and there is no independently",
           "authenticated historical first-seen timestamp or broker fill.",""]
    if c:
        b=result["baseline"]
        lines += ["| Portfolio | CAGR | MaxDD | Cost+lag gate |",
                  "|---|---:|---:|---|",
                  f'| Frozen 8.0 | {b["cagr"]:.3%} | {b["max_drawdown"]:.3%} | baseline |',
                  f'| Prior VIX/VIX3M >=1 => cap 2x | {c["cagr"]:.3%} | {c["max_drawdown"]:.3%} | {c["passes"]}/4 |']
    else:
        lines+=["Blocked reason: `"+result.get("blocked_reason","none")+"`",
                "No ETF returns computed from incomplete index data."]
    REPORT.write_text("\n".join(lines)+"\n")
    print("STOCKLENS_VIX3M_TERM_RESULT="+json.dumps({
        "status":result["status"],"observed":result.get("observed_vix3m_prior_sessions",0),
        "base":result.get("baseline"),"candidate":result.get("candidate"),
        "blocked_reason":result.get("blocked_reason"),
        "promoted":False},sort_keys=True))
    return result


if __name__=="__main__":
    build()
