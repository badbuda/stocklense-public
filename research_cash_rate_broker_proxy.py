"""As-of interest-rate *research* on frozen StockLens modeled cash.

Reference rates are not broker deposit rates. Supplied timestamp strings are
assertions until independently audited; no annualized trading alpha is claimed.
No network requests, automatic model changes, or broker orders.
"""
from __future__ import annotations
from datetime import date, datetime, timezone
from pathlib import Path
import json
import math

import exchange_calendars as xcals
from observed_etf_two_question_audit import load, _metrics, _prices, START_CAPITAL
from tradable_tqqq_execution_comparison import _mark, _rebalance
from stocklens.core import TARGET_INVESTED_FRACTION, weights_for_leverage

INPUT = Path("research/private/rates_asof.json")
OUT = Path("research/results/cash_rate_asof_readiness.json")
REPORT = Path("research/reports/cash_rate_asof_readiness.md")
ALLOWED = {"EFFR", "SOFR"}  # Both market benchmarks, NEVER broker cash terms.


def _utc(v):
    if not isinstance(v, str):
        raise ValueError("RATE_TIMESTAMP_REQUIRED")
    try:
        t = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError("RATE_TIMESTAMP_INVALID") from e
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("RATE_TIMESTAMP_MUST_BE_AWARE")
    return t.astimezone(timezone.utc)


def normalize(quotes):
    if not isinstance(quotes, dict) or quotes.get("schema_version") != 1:
        raise ValueError("RATE_SOURCE_SCHEMA_INVALID")
    series = quotes.get("series")
    if series not in ALLOWED:
        raise ValueError("RATE_SERIES_NOT_OVERNIGHT_BENCHMARK")
    data = quotes.get("observations")
    if not isinstance(data, list) or not data:
        raise ValueError("RATE_SOURCE_NO_OBSERVATIONS")
    out = []
    for r in data:
        if not isinstance(r, dict):
            raise ValueError("RATE_ROW_INVALID")
        try:
            effective = date.fromisoformat(r["effective_date"])
            available = _utc(r["claimed_published_at_utc"])
            rate = r["rate_percent"]
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError("RATE_ROW_REQUIRED_FIELDS") from e
        if type(rate) not in (int, float) or not math.isfinite(rate) or not 0 <= rate <= 25:
            raise ValueError("RATE_OUTSIDE_PERCENT_UNITS_OR_RANGE")
        if available.date() < effective:
            raise ValueError("RATE_PUBLISHED_BEFORE_EFFECTIVE_DATE")
        out.append((effective, available, float(rate) / 100.0))
    if out != sorted(out, key=lambda x: (x[1], x[0])):
        raise ValueError("RATE_CLAIMED_PUBLICATIONS_NOT_SORTED")
    if len(set(e for e, _, _ in out)) != len(out):
        # Revision histories require a separate explicitly versioned contract.
        raise ValueError("RATE_DUPLICATE_EFFECTIVE_DATE")
    return out


def asof_open_rates(price_rows, source):
    """Use only claimed publications available by the PRIOR XNYS close.

    For interest accrual from day t-1 to open t, the t rate must NOT use
    an EFFR/SOFR observation published during that overnight interval.
    Gaps over 7 calendar days fail closed instead of 0%-cash backfill.
    """
    if not price_rows:
        raise ValueError("RATE_NO_MARKET_DAYS")
    quotes = normalize(source)
    cal = xcals.get_calendar("XNYS")
    days = [date.fromisoformat(r["date"]) for r in price_rows]
    if days != sorted(set(days)):
        raise ValueError("RATE_NONMONOTONE_EXCHANGE_DAYS")
    result = [0.0]
    for i in range(1, len(days)):
        prior = days[i - 1]
        cutoff = cal.session_close(prior.isoformat()).to_pydatetime()
        known = [q for q in quotes if q[1] <= cutoff and q[0] <= prior]
        if not known:
            raise ValueError("RATE_NO_ASOF_QUOTE")
        effective, available, rate = max(known, key=lambda x: (x[1], x[0]))
        if (prior - effective).days > 7:
            raise ValueError("RATE_QUOTE_STALE")
        result.append(rate)
    return result


def simulate(rows, rates):
    """Frozen decisions, real observed QQQ/TQQQ price rows; modeled whole shares."""
    if len(rows) != len(rates) or rates[0] != 0.0:
        raise ValueError("RATE_DAILY_ALIGNMENT_INVALID")
    p = {"cash": START_CAPITAL, "shares": {"QQQ": 0, "TQQQ": 0},
         "fees": 0.0, "slippage": 0.0, "trades": 0, "turnover_notional": 0.0}
    navs, dates = [], []
    prior_level = None
    interest = 0.0
    for i, row in enumerate(rows):
        now = date.fromisoformat(row["date"])
        if i:
            elapsed = (now - date.fromisoformat(rows[i - 1]["date"])).days
            r = rates[i]
            if type(r) not in (float, int) or not math.isfinite(r) or not 0 <= r <= .25:
                raise ValueError("RATE_DAILY_VALUE_INVALID")
            if elapsed <= 0:
                raise ValueError("RATE_INVALID_EXCHANGE_ORDER")
            credit = p["cash"] * ((1 + r) ** (elapsed / 365.2425) - 1)
            p["cash"] += credit
            interest += credit
        level = row["l"]
        if level not in (0, 1.25, 2, 3) or row.get("signal", "") >= row["date"]:
            raise ValueError("RATE_INVALID_FROZEN_DECISION")
        q, t = weights_for_leverage(level) if level else (0., 0.)
        if prior_level is None or level != prior_level:
            _rebalance(p, _prices(row),
                       {"QQQ": q * TARGET_INVESTED_FRACTION,
                        "TQQQ": t * TARGET_INVESTED_FRACTION},
                       2., 10.)
        nav = _mark(p, _prices(row), "close")
        if not math.isfinite(nav) or nav <= 0 or p["cash"] < -1e-5:
            raise ValueError("RATE_INVALID_NAV")
        navs.append(nav)
        dates.append(row["date"])
        prior_level = level
    return {"stats": _metrics(navs, dates), "navs": navs,
            "cash_interest_dollars": interest, "synthetic_tqqq_used": False,
            "broker_interest_entitlement_proven": False,
            "rate_clock_independently_verified": False}


def build():
    raw = load()
    result = {
        "schema_version": 1, "kind": "REFERENCE_RATE_CASH_ASOF_RESEARCH",
        "status": "BLOCKED_NO_HISTORICAL_ASOF_RATE_INPUT",
        "observed_qqq_tqqq_sessions": len(raw["daily"]),
        "price_source_snapshot_sha256": raw.get("snapshot_sha256"),
        "claimed_rate_source_supplied": INPUT.exists(),
        "reference_rate_is_not_broker_cash_yield": True,
        "source_publication_clock_independently_proven": False,
        "broker_interest_entitlement_proven": False,
        "cash_alpha_proven": False,
        "frozen_stocklens8_changed": False,
        "synthetic_tqqq_used": False,
        "automatic_promotion": False,
        "capital_deployment_authorized": False,
    }
    if INPUT.exists():
        try:
            source = json.loads(INPUT.read_text(encoding="utf-8"))
            schedule = asof_open_rates(raw["daily"], source)
            simulated = simulate(raw["daily"], schedule)
            result.update(status="UNVERIFIED_HISTORICAL_RATE_CLAIMS_DESCRIPTIVE_ONLY",
                          reference_series=source["series"],
                          modeled_conditional_cagr=simulated["stats"]["cagr"],
                          modeled_conditional_maxdd=simulated["stats"]["max_drawdown"],
                          quoted_gross_cash_interest=simulated["cash_interest_dollars"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            result.update(status="BLOCKED_INVALID_OR_INCOMPLETE_RATE_INPUT",
                          error_code=str(e)[:120])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    REPORT.write_text("# Historical cash-rate as-of readiness\n\nStatus: **" +
                      result["status"] + "**.\n\n" +
                      "Reference EFFR/SOFR observations are not actual brokerage " +
                      "cash sweep rates. Even complete claimed publication clocks " +
                      "require independent audit and actual broker terms. No promotion.\n")
    print("STOCKLENS_CASH_ASOF_READINESS=" + json.dumps(result, sort_keys=True))
    return result


if __name__ == "__main__":
    build()
