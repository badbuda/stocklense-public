"""ST-only predeclared real 3x ETF alternatives to FROZEN StockLens 8.0.

Never synthesizes ETF prices, changes frozen signals, or places broker orders.
Research scores are not eligible for automatic promotion or real capital.
"""
from __future__ import annotations
import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path

ETFS = ("UPRO", "SOXL", "TECL", "FAS")
SYMS = ("QQQ", "TQQQ") + ETFS
BASE = Path("docs/portal-history.json")
RAW = Path("research/private/st_real_3x_etfs.json")
RESULT = Path("research/results/st_real_3x_etfs.json")
REPORT = Path("research/reports/st_real_3x_etfs.md")
MODES = ("frozen",) + tuple(p + s for p in ("replace3_", "blend25_") for s in ETFS)
LAGS, SLIPS, FEE = (0, 1), (10., 20.), 2.
INVESTED = .985
CAPITAL = 100000.

def download(base: dict) -> dict:
    """Yahoo is allowed for acquisition only; never impute a missing quote."""
    import yfinance as yf
    end_day = base["updated_session"]
    if date.fromisoformat(end_day) > datetime.now(timezone.utc).date():
        raise ValueError("FUTURE_FROZEN_END")
    end = (date.fromisoformat(end_day) + timedelta(days=1)).isoformat()
    bars = {}
    for s in ETFS:
        frame = yf.Ticker(s).history(start="2010-02-01", end=end,
                    interval="1d", auto_adjust=True, repair=False, actions=False)
        if frame is None or frame.empty:
            raise ValueError("REAL_VENDOR_DATA_MISSING:" + s)
        series = []
        for timestamp, r in frame.iterrows():
            d = timestamp.date().isoformat()
            if d > end_day:
                continue
            op, cl = float(r["Open"]), float(r["Close"])
            if not all(math.isfinite(x) and x > 0 for x in (op, cl)):
                raise ValueError("BAD_VENDOR_BAR:" + s)
            series.append({"date": d, "open": op, "close": cl})
        if len(series) < 3000 or len({x["date"] for x in series}) != len(series):
            raise ValueError("VENDOR_INCOMPLETE_OR_DUPLICATE:" + s)
        bars[s] = series
    return {"schema_version": 1, "vendor": "YAHOO_YFINANCE_AUTO_ADJUST",
            "captured_utc": datetime.now(timezone.utc).isoformat(),
            "symbols": list(ETFS), "bars": bars,
            "independently_verified": False, "synthetic_prices_used": False}

def validate(base: dict, ext: dict):
    if (base.get("evidence") != "REAL_QQQ_TQQQ_ADJUSTED_DAILY_OPEN_EXECUTION_PROXY"
            or base.get("instruments") != ["QQQ", "TQQQ"]
            or base.get("live_trading_authorized") is not False
            or base.get("observed_ohlc_available") is not True):
        raise ValueError("INVALID_OBSERVED_FROZEN_SOURCE")
    if (ext.get("schema_version") != 1 or
            ext.get("symbols") != list(ETFS) or
            ext.get("vendor") != "YAHOO_YFINANCE_AUTO_ADJUST" or
            set(ext.get("bars", {})) != set(ETFS) or
            ext.get("synthetic_prices_used") is not False or
            not ext.get("captured_utc")):
        raise ValueError("INVALID_3X_VENDOR_SOURCE")
    original = base["daily"]
    original_days = [r["date"] for r in original]
    if (len(original) < 3000 or original_days != sorted(set(original_days))
            or original_days[-1] != base["updated_session"]):
        raise ValueError("INVALID_FROZEN_HISTORY")
    for r in original:
        if r.get("signal", "") >= r["date"] or r.get("l") not in (0, 1.25, 2, 3):
            raise ValueError("FUTURE_OR_UNKNOWN_FROZEN_SIGNAL")
        if any(type(r.get(k)) not in (int, float) or not math.isfinite(r[k]) or r[k] <= 0
               for k in ("qo", "qc", "to", "tc")):
            raise ValueError("MISSING_OBSERVED_BASE_PRICE")
    maps = {}
    first = original_days[0]
    for s in ETFS:
        series = ext["bars"][s]
        days = [r["date"] for r in series]
        if not days or days != sorted(set(days)):
            raise ValueError("BAD_ETF_SOURCE_CALENDAR:" + s)
        maps[s] = {r["date"]: r for r in series}
        first = max(first, days[0])
    rows = [r for r in original if r["date"] >= first]
    if len(rows) < 3000:
        raise ValueError("INSUFFICIENT_MATCHED_3X_HISTORY")
    for s in ETFS:
        for r in rows:
            bar = maps[s].get(r["date"])
            if bar is None or any(type(bar.get(k)) not in (int, float) or
                                   not math.isfinite(bar[k]) or bar[k] <= 0
                                   for k in ("open", "close")):
                raise ValueError("MISSING_MATCHED_REAL_3X_BAR:" + s + ":" + r["date"])
    return rows, maps

def weights(lev: float, mode: str):
    from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
    if abs(TARGET_INVESTED_FRACTION - INVESTED) > 1e-10:
        raise ValueError("BASE_INVESTED_FRACTION_CHANGED")
    if mode not in MODES:
        raise ValueError("UNREGISTERED_3X_CHALLENGER")
    if lev not in (0, 1.25, 2, 3):
        raise ValueError("BAD_FROZEN_LEVEL")
    result = {s: 0. for s in SYMS}
    if lev == 0:
        return result
    q, t = weights_for_leverage(lev)
    result["QQQ"], result["TQQQ"] = q * INVESTED, t * INVESTED
    # Exactly the 3x state changes. 0x/1.25x/2x remain identical to frozen.
    if lev == 3 and mode != "frozen":
        ticker = mode.rsplit("_", 1)[1]
        proportion = 1. if mode.startswith("replace3_") else .25
        result[ticker] = t * INVESTED * proportion
        result["TQQQ"] *= 1. - proportion
    if min(result.values()) < 0 or sum(result.values()) > INVESTED + 1e-9:
        raise ValueError("INVALID_RESEARCH_EXPOSURE")
    return result

def replay(rows: list[dict], bars: dict, mode: str, lag: int, slip: float):
    if mode not in MODES or lag not in LAGS or slip not in SLIPS:
        raise ValueError("UNREGISTERED_TEST_CONFIGURATION")
    cash, shares, navs, trades = CAPITAL, {s: 0 for s in SYMS}, [], 0
    previous = None
    for i, r in enumerate(rows):
        level = rows[i - lag]["l"] if i >= lag else 0
        day = r["date"]
        prices = {"QQQ": {"open": r["qo"], "close": r["qc"]},
                  "TQQQ": {"open": r["to"], "close": r["tc"]}}
        prices.update({s: bars[s][day] for s in ETFS})
        if previous is None or level != previous:
            w = weights(level, mode)
            equity = cash + sum(shares[s] * prices[s]["open"] for s in SYMS)
            target = {s: math.floor(equity * w[s] / prices[s]["open"]) for s in SYMS}
            for s in SYMS:
                excess = shares[s] - target[s]
                if excess > 0:
                    cash += excess * prices[s]["open"] * (1-slip/10000.) * (1-FEE/10000.)
                    shares[s] -= excess
                    trades += 1
            for s in SYMS:
                missing = target[s] - shares[s]
                if missing > 0:
                    unit = prices[s]["open"] * (1+slip/10000.) * (1+FEE/10000.)
                    bought = min(missing, math.floor(max(0., cash)/unit))
                    if bought > 0:
                        cash -= bought * unit
                        shares[s] += bought
                        trades += 1
        nav = cash + sum(shares[s] * prices[s]["close"] for s in SYMS)
        if cash < -1e-6 or nav <= 0 or not math.isfinite(nav):
            raise ValueError("INVALID_REAL_ETF_PORTFOLIO_LEDGER")
        navs.append(nav)
        previous = level
    return navs, trades

def metrics(navs, dates):
    peak, dd, old = CAPITAL, 0., CAPITAL
    daily = []
    for nav in navs:
        peak = max(peak, nav)
        dd = min(dd, nav/peak-1)
        daily.append(nav/old-1)
        old = nav
    avg = sum(daily)/len(daily)
    variance = sum((x-avg)**2 for x in daily)/(len(daily)-1)
    years = (date.fromisoformat(dates[-1])-date.fromisoformat(dates[0])).days/365.2425
    return {"cagr": (navs[-1]/CAPITAL)**(1/years)-1, "maxdd": dd,
            "volatility": math.sqrt(variance*252), "ending_equity": round(navs[-1], 2)}

def evaluate(base, extra):
    rows, bars = validate(base, extra)
    days = [r["date"] for r in rows]
    paths = {(m,l,s): replay(rows,bars,m,l,s)
             for m in MODES for l in LAGS for s in SLIPS}
    # Independent, pre-existing whole-share frozen simulator: exact DAILY NAV parity.
    from observed_etf_four_challengers_batch import simulate as original
    for lag in LAGS:
        for slip in SLIPS:
            comparison = original(rows, mode="frozen", lag=lag, slippage_bps=slip)
            actual = paths["frozen",lag,slip][0]
            if (len(actual) != len(comparison["navs"]) or
                any(abs(a-b) > 1e-5 for a,b in zip(actual,comparison["navs"]))):
                raise ValueError("DAILY_FROZEN_8_PARITY_FAILED")
    experiments = []
    for mode in MODES:
        navs, trades = paths[mode,1,10.]
        main = metrics(navs,days)
        ref = metrics(paths["frozen",1,10.][0],days)
        cases = []
        for lag in LAGS:
            for slip in SLIPS:
                candidate = metrics(paths[mode,lag,slip][0],days)
                control = metrics(paths["frozen",lag,slip][0],days)
                d_cagr = 100*(candidate["cagr"]-control["cagr"])
                d_dd = 100*(candidate["maxdd"]-control["maxdd"])
                cases.append({"extra_lag":lag,"slippage_bps_side":slip,
                              "cagr_delta_pp":d_cagr,"drawdown_gain_pp":d_dd,
                              "continuation_screen":d_cagr>=.5 and d_dd>=-1.})
        experiments.append({"name":mode, **main, "trades":trades,
                            "cagr_delta_pp":100*(main["cagr"]-ref["cagr"]),
                            "maxdd_gain_pp":100*(main["maxdd"]-ref["maxdd"]),
                            "stress":cases, "continue_research":mode!="frozen" and
                            all(z["continuation_screen"] for z in cases)})
    digest = hashlib.sha256(json.dumps(extra["bars"],sort_keys=True,
                                 separators=(",",":")).encode()).hexdigest()
    return {"schema_version":1,"kind":"ST_REAL_3X_ETF_FROZEN_8_COMPARISON",
            "status":"HISTORICAL_REUSED_NO_PROMOTION",
            "asof":base["updated_session"],"captured_utc":extra["captured_utc"],
            "source_vendor":"YAHOO_YFINANCE_AUTO_ADJUST",
            "base_sha256":base.get("snapshot_sha256"),
            "additional_real_etf_data_sha256":digest,
            "period":{"start":days[0],"end":days[-1],"sessions":len(days)},
            "extra_etfs":list(ETFS),"baseline_nav_parity":True,
            "frozen8_modified":False,"broker_actions":False,
            "automatic_promotion":False,"source_independently_audited":False,
            "prospective_paper_observed":False,"clean_oos":False,
            "execution_proxy":"adjusted daily open, whole shares; 2 bps fee + 10/20 bps slippage per side",
            "modes":"replace entire TQQQ only at level 3; or blend 75% TQQQ 25% alternate at 3x; other frozen states untouched",
            "selection_gate":"at least +0.5 pp CAGR and no >1pp MaxDD worsening in all 4 stress cases; continuation only",
            "primary":"lag1,10bps","experiments":experiments}

def run(*, acquire, output=RESULT, report=REPORT):
    base = json.loads(BASE.read_text())
    if acquire:
        extra = download(base)
        RAW.parent.mkdir(parents=True,exist_ok=True)
        RAW.write_text(json.dumps(extra,sort_keys=True,separators=(",",":"))+"\n")
    else:
        extra = json.loads(RAW.read_text())
    findings = evaluate(base,extra)
    output.parent.mkdir(parents=True,exist_ok=True)
    report.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(findings,sort_keys=True,indent=2)+"\n")
    rows = ["# ST: additional actual 3x ETFs against frozen StockLens 8.0", "",
            "Historical reused ETF adjusted daily OPEN proxy; **not** real fills, pristine OOS, or future performance.",
            "Never trade, change PROD, or promote automatically.", "",
            "| Mode | CAGR | MaxDD | ΔCAGR pp | ΔMaxDD pp | Passes/4 |",
            "|---|---:|---:|---:|---:|---:|"]
    for e in findings["experiments"]:
        rows.append("| {name} | {cagr:.2%} | {maxdd:.2%} | {cagr_delta_pp:+.2f} | {maxdd_gain_pp:+.2f} | {count}/4 |".format(
            **e,count=sum(v["continuation_screen"] for v in e["stress"])))
    rows += ["", "Observed shared window: {start} through {end}, {sessions} trading sessions.".format(
             **findings["period"]),
             "All variants use the same original QQQ signal; no independent per-asset regime training.",
             "Yahoo adjustments, venue spreads and broker fees are not independently certified.",
             "The screen is for further research only; prospective validation is mandatory."]
    report.write_text("\n".join(rows)+"\n")
    print("ST_REAL_3X_RESEARCH=" + json.dumps({"status":findings["status"],
          "period":findings["period"],
          "summary":[{"name":e["name"],"cagr":e["cagr"],"maxdd":e["maxdd"],
          "continue_research":e["continue_research"]} for e in findings["experiments"]]}))
    return findings

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--acquire",action="store_true",
                        help="Download actual adjusted Yahoo ETF OHLC, fail on missing")
    args=parser.parse_args()
    run(acquire=args.acquire)
