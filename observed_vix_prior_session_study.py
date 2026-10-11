"""SL9-016 Cboe REAL observed VIX prior close conditioned exposure; research only.

Two mechanisms preregistered, NOT a new EWMA or Kelly parameter sweep.
Index values are genuine Cboe daily VIX observations and never synthetic.
No broker fills, provider historical first-seen attestations, clean holdout,
automatic promotion, or StockLens 8.0 core changes.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import csv
import hashlib
import io
import json
import math
from urllib.request import Request, urlopen

from observed_etf_two_question_audit import load, _metrics, SPLITS, START_CAPITAL, _prices
from observed_etf_four_challengers_batch import simulate as frozen_reference
from stocklens.core import TARGET_INVESTED_FRACTION, weights_for_leverage
from tradable_tqqq_execution_comparison import _mark, _rebalance

OFFICIAL_VIX_URL = "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
SOURCE = Path("research/private/vix_official_history_as_observed_20261011.json")
OUT = Path("research/results/observed_vix_fixed_guard_results.json")
REPORT = Path("research/reports/observed_vix_fixed_guard_results.md")
EXPECTED_BASE_SHA = "bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129"
MODES = ("frozen", "vix_high_tier", "vix_five_session_shock")
LAGS = (0, 1)
SLIPPAGES_BPS = (10.0, 20.0)
FEE_BPS = 2.0


def _date(value):
    if not isinstance(value, str):
        raise ValueError("VIX_DATE_NOT_STRING")
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError("VIX_DATE_UNPARSEABLE")


def normalize_csv(raw):
    """Cboe official daily VIX CSV with no interpolation or lookahead."""
    if not isinstance(raw, str) or len(raw) < 30:
        raise ValueError("VIX_EMPTY_OFFICIAL_CSV")
    rd = csv.DictReader(io.StringIO(raw.lstrip("\ufeff")))
    if not rd.fieldnames:
        raise ValueError("VIX_OFFICIAL_CSV_HEADER_MISSING")
    fields = {str(k).strip().upper(): k for k in rd.fieldnames}
    if not {"DATE", "CLOSE"} <= set(fields):
        raise ValueError("VIX_OFFICIAL_DATE_CLOSE_COLUMNS_MISSING")
    pairs = {}
    for entry in rd:
        d = _date(entry[fields["DATE"]])
        try:
            close = float(entry[fields["CLOSE"]])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("VIX_INVALID_CLOSE") from exc
        if not math.isfinite(close) or not (0 < close < 200):
            raise ValueError("VIX_CLOSE_OUTSIDE_UNITS_OR_NONFINITE")
        if d in pairs:
            raise ValueError("VIX_DUPLICATE_EXCHANGE_DATE")
        pairs[d] = close
    if not pairs:
        raise ValueError("VIX_NO_OFFICIAL_OBSERVATIONS")
    return [{"date": d, "vix_close": pairs[d]} for d in sorted(pairs)]


def official_acquire():
    req = Request(OFFICIAL_VIX_URL, headers={
        "User-Agent": "StockLens-Research-PIT-Study/1.0",
        "Accept": "text/csv",
    })
    with urlopen(req, timeout=35) as resp:
        body = resp.read(3_000_001)
    if len(body) > 3_000_000:
        raise ValueError("VIX_CSV_TOO_LARGE")
    raw = body.decode("utf-8-sig")
    bars = normalize_csv(raw)
    return {"schema_version": 1, "series": "CBOE_VIX_INDEX_DAILY_CLOSE",
            "source_url": OFFICIAL_VIX_URL,
            "source_raw_csv_sha256": hashlib.sha256(body).hexdigest(),
            "downloaded_historical_snapshot_first_seen_proven": False,
            "provider_publication_time_independently_verified": False,
            "bars": bars}


def source_validation(source, market_days):
    if (not isinstance(source, dict) or source.get("schema_version") != 1
        or source.get("series") != "CBOE_VIX_INDEX_DAILY_CLOSE"
        or source.get("source_url") != OFFICIAL_VIX_URL
        or source.get("downloaded_historical_snapshot_first_seen_proven") is not False
        or source.get("provider_publication_time_independently_verified") is not False):
        raise ValueError("VIX_SOURCE_PROVENANCE_CONTRACT_INVALID")
    bars = source.get("bars")
    if not isinstance(bars, list) or not bars:
        raise ValueError("VIX_SOURCE_EMPTY")
    values = {}
    for row in bars:
        if not isinstance(row, dict) or not isinstance(row.get("date"), str):
            raise ValueError("VIX_SOURCE_INVALID_ROW")
        try:
            d = datetime.strptime(row["date"], "%Y-%m-%d").date().isoformat()
        except ValueError as exc:
            raise ValueError("VIX_SOURCE_BAD_DATE") from exc
        v = row.get("vix_close")
        if type(v) not in (int, float) or not math.isfinite(v) or not (0 < v < 200):
            raise ValueError("VIX_SOURCE_INVALID_PRICE")
        if d in values:
            raise ValueError("VIX_SOURCE_DUPLICATE_DATES")
        values[d] = float(v)
    if market_days != sorted(set(market_days)):
        raise ValueError("VIX_REFERENCE_MARKET_DATES_INVALID")
    # Only pre-decision completed sessions used in the original sample.
    missing = [d for d in market_days[:-1] if d not in values]
    if missing:
        raise ValueError("VIX_MISSING_PRIOR_COMPLETED_SESSION:" +
                         str(len(missing)) + ":" + ",".join(missing[:3]))
    encoded = json.dumps({d: values[d] for d in market_days[:-1]},
                         sort_keys=True, separators=(",", ":")).encode()
    return values, hashlib.sha256(encoded).hexdigest()


def target(level, mode, prior_close, five_earlier):
    if level not in (0, 1.25, 2, 3) or mode not in MODES:
        raise ValueError("VIX_UNREGISTERED_EXPOSURE")
    if level == 0 or mode == "frozen":
        return level
    if prior_close is None or not math.isfinite(prior_close):
        raise ValueError("VIX_PRIOR_CLOSE_NOT_AVAILABLE")
    cap = 3.0
    if mode == "vix_high_tier":
        if prior_close >= 40.0:
            cap = 1.25
        elif prior_close >= 30.0:
            cap = 2.0
    elif mode == "vix_five_session_shock":
        if prior_close >= 40.0:
            cap = 1.25
        elif five_earlier is not None and prior_close >= 25.0 and prior_close-five_earlier >= 5.0:
            cap = 2.0
    return min(level, cap)


def simulate(rows, source, mode="frozen", lag=0, slip_bps=10.0):
    if mode not in MODES or lag not in LAGS or slip_bps not in SLIPPAGES_BPS:
        raise ValueError("VIX_MODE_OR_COST_NOT_PREREGISTERED")
    dates = [r["date"] for r in rows]
    index, _ = source_validation(source, dates)
    p = {"cash": START_CAPITAL, "shares": {"QQQ": 0, "TQQQ": 0},
         "fees": 0., "slippage": 0., "trades": 0, "turnover_notional": 0.}
    navs, actual_levels, hits = [], [], 0
    last = None
    for i, r in enumerate(rows):
        if r.get("signal", "") >= r["date"] or r.get("l") not in (0, 1.25, 2, 3):
            raise ValueError("VIX_FROZEN_DECISION_NOT_ASOF")
        j = i-lag
        frozen_level = rows[j]["l"] if j >= 0 else 0.
        # To trade open i, use only the VIX close of session j-1.
        # Extra lag=1 shifts both StockLens and VIX signal back one full session.
        prior = index[dates[j-1]] if j >= 1 else None
        five = index[dates[j-6]] if j >= 6 else None
        if j == 0 and mode != "frozen":
            effective = frozen_level  # no pre-cohort VIX input, no fabricated hedge
        else:
            effective = target(frozen_level, mode, prior, five)
        if effective < frozen_level:
            hits += 1
        q, t = weights_for_leverage(effective) if effective else (0., 0.)
        weights = {"QQQ": q * TARGET_INVESTED_FRACTION,
                   "TQQQ": t * TARGET_INVESTED_FRACTION}
        prices = _prices(r)
        if last is None or last != effective:
            _rebalance(p, prices, weights, FEE_BPS, slip_bps)
        nav = _mark(p, prices, "close")
        if not math.isfinite(nav) or nav <= 0 or p["cash"] < -1e-5:
            raise ValueError("VIX_INVALID_MODELED_ACCOUNT")
        navs.append(nav)
        actual_levels.append(effective)
        last = effective
    return {"navs": navs, "dates": dates, "levels": actual_levels,
            "stats": _metrics(navs, dates), "intervention_sessions": hits,
            "trades": p["trades"]}


def era(path, first, last):
    indexes = [i for i, d in enumerate(path["dates"]) if first <= d <= last]
    if not indexes:
        raise ValueError("VIX_ERA_NOT_IN_SOURCE")
    a, b = indexes[0], indexes[-1]
    before = START_CAPITAL if a == 0 else path["navs"][a-1]
    return _metrics(path["navs"][a:b+1], path["dates"][a:b+1], first=before)


def evaluate(market, source):
    if market.get("snapshot_sha256") != EXPECTED_BASE_SHA:
        raise ValueError("VIX_FROZEN_QQQ_TQQQ_SOURCE_CHANGED")
    rows = market["daily"]
    idx, snapshot = source_validation(source, [r["date"] for r in rows])
    results = {(m, l, s): simulate(rows, source, m, l, s)
               for m in MODES for l in LAGS for s in SLIPPAGES_BPS}
    for lag in LAGS:
        for slip in SLIPPAGES_BPS:
            baseline = results[("frozen", lag, slip)]["navs"]
            independently = frozen_reference(
                rows, mode="frozen", lag=lag, slippage_bps=slip)["navs"]
            if len(baseline) != len(independently) or any(
                abs(a-b) > 1e-5 for a, b in zip(baseline, independently)
            ):
                raise ValueError("VIX_FROZEN_LEDGER_DAILY_PARITY_FAILED")
    base = results[("frozen", 0, 10.)]
    candidates = {}
    for m in MODES[1:]:
        v = results[(m, 0, 10.)]
        trials = []
        for lag in LAGS:
            for slip in SLIPPAGES_BPS:
                s = results[(m, lag, slip)]["stats"]
                b = results[("frozen", lag, slip)]["stats"]
                improvement = 100*(s["max_drawdown"]-b["max_drawdown"])
                penalty = 100*(s["cagr"]-b["cagr"])
                trials.append({
                    "lag": lag, "slippage_bps": slip,
                    "cagr_delta_pp": penalty, "maxdd_improvement_pp": improvement,
                    "passes_fixed_screen": improvement >= 3.0 and penalty >= -1.5,
                })
        candidates[m] = {
            "cagr": v["stats"]["cagr"],
            "maxdd": v["stats"]["max_drawdown"],
            "cagr_delta_pp": 100*(v["stats"]["cagr"]-base["stats"]["cagr"]),
            "maxdd_improvement_pp": 100*(v["stats"]["max_drawdown"]-base["stats"]["max_drawdown"]),
            "intervention_sessions": v["intervention_sessions"],
            "trades": v["trades"], "cost_lag_trials": trials,
            "historical_continuation_passes": sum(x["passes_fixed_screen"] for x in trials),
            "eras": {name: {
                "cagr_delta_pp": 100*(era(v, a, b)["cagr"]-era(base, a, b)["cagr"]),
                "maxdd_improvement_pp": 100*(era(v, a, b)["max_drawdown"]-era(base, a, b)["max_drawdown"]),
            } for name, (a, b) in SPLITS.items()},
        }
    return {
        "schema_version": 1, "kind": "OBSERVED_CBOE_VIX_FIXED_IMPLIED_RISK_STUDY",
        "period": market["period"], "full_vix_source_sha256": source.get("source_raw_csv_sha256"),
        "matched_prior_vix_sessions": len(rows)-1, "analysis_vix_snapshot_sha256": snapshot,
        "reference_source_sha256": market["snapshot_sha256"],
        "source_provider_first_seen_verified": False,
        "vix_daily_close_prior_session_only": True, "frozen_baseline_nav_parity": True,
        "baseline": base["stats"], "candidates": candidates,
        "reused_sample_no_pristine_oos": True,
        "real_qqq_tqqq_no_synthetic": True, "live_execution_verified": False,
        "baseline_stocklens8_changed": False, "automatic_promotion": False,
        "capital_deployment_authorized": False,
    }


def build():
    market = load()
    source = official_acquire()
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    SOURCE.write_text(json.dumps(source, sort_keys=True, separators=(",", ":"))+"\n")
    result = evaluate(market, source)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    base = result["baseline"]
    text = [
        "# SL9-016 Observed CBOE VIX-based protection (reused historical sample)",
        "", "Observed Cboe daily closes, one **completed prior trading session**",
        "before modeled open; no independent historical provider first-seen",
        "attestation and no precise broker fill/quote timestamps.",
        "Frozen QQQ/TQQQ inputs unchanged. Two rules only, preregistered.",
        "", "| Mode | CAGR | MaxDD | CAGR delta pp | MaxDD improvement pp | Events | Gate |",
        "|---|---:|---:|---:|---:|---:|---|",
        f'| frozen | {base["cagr"]:.3%} | {base["max_drawdown"]:.3%} | 0 | 0 | - | original |',
    ]
    for m, v in result["candidates"].items():
        text.append(f'| {m} | {v["cagr"]:.3%} | {v["maxdd"]:.3%} | '
                    f'{v["cagr_delta_pp"]:+.3f} | '
                    f'{v["maxdd_improvement_pp"]:+.3f} | '
                    f'{v["intervention_sessions"]} | '
                    f'{v["historical_continuation_passes"]}/4 |')
    text += ["", "Prices are observed daily adjusted ETF bars, not NBBO.",
             "No optimized thresholds, no new OOS, no model promotion or trading."]
    REPORT.write_text("\n".join(text)+"\n")
    short = {"market_sessions": result["period"]["sessions"],
             "vix_sessions": result["matched_prior_vix_sessions"],
             "vix_snapshot_sha256": result["analysis_vix_snapshot_sha256"],
             "base": {k: base[k] for k in ("cagr", "max_drawdown")},
             "candidates": {m: {k: v[k] for k in (
                 "cagr", "maxdd", "cagr_delta_pp", "maxdd_improvement_pp",
                 "intervention_sessions", "historical_continuation_passes")}
                 for m, v in result["candidates"].items()},
             "frozen_parity": True, "historical_vix_first_seen_proven": False,
             "broker_authorized": False}
    print("STOCKLENS_CBOE_VIX_FIXED="+json.dumps(short,sort_keys=True))
    return result


if __name__ == "__main__":
    build()
