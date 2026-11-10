"""Research-only real QQQE equal-weight participation proxy for transition timing.

NOT percentage of Nasdaq-100 stocks above SMA50. Historical daily adjusted
QQQE ETF market prices are a proxy for participation vs cap-weighted QQQ.
Fails closed if vendor data/calendar unavailable. No broker orders/prod writes.
"""
from __future__ import annotations
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

INPUT = Path("research/frozen_sources/observed_qqq_tqqq_ml_20100211_20261009.json")
OUT = Path("research/results/qqqe_transition_proxy_20261110.json")
VENDOR = Path("research/results/qqqe_observed_vendor_20261110.json")
CAP = 100000.0
INV = 0.985
FEE = 0.0002
START_DATE = "2012-05-01"
END_DATE = "2026-10-09"


def download():
    import yfinance as yf
    frame = yf.Ticker("QQQE").history(
        start="2012-03-19", end="2026-10-10",
        interval="1d", auto_adjust=True, repair=False, actions=False
    )
    if frame is None or frame.empty:
        raise ValueError("QQQE_VENDOR_NO_PRICE_HISTORY")
    observations = []
    for ts, row in frame.iterrows():
        day = ts.date().isoformat()
        if day > END_DATE:
            continue
        close = float(row["Close"])
        if not math.isfinite(close) or close <= 0:
            raise ValueError("QQQE_BAD_CLOSE")
        observations.append({"date": day, "close": close})
    dates = [x["date"] for x in observations]
    if len(dates) < 3000 or dates != sorted(set(dates)):
        raise ValueError("QQQE_HISTORY_INSUFFICIENT_OR_DUPLICATED")
    if dates[0] > "2012-04-10" or dates[-1] != END_DATE:
        raise ValueError("QQQE_VENDOR_COVERAGE_INCOMPLETE")
    digest = hashlib.sha256(
        json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "kind": "OBSERVED_QQQE_ADJUSTED_CLOSE_RESEARCH_ONLY",
        "vendor": "YAHOO_YFINANCE_AUTO_ADJUSTED",
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "sha256": digest,
        "independently_audited": False,
        "bars": observations,
    }


def ema(values, period):
    alpha = 2.0 / (period + 1)
    z = values[0]
    out = []
    for v in values:
        z = v * alpha + z * (1 - alpha)
        out.append(z)
    return out


def compute(source, ext):
    rows = source["daily"]
    dates = [r["date"] for r in rows]
    if (
        source.get("snapshot_sha256")
        != "bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129"
        or len(rows) != 4191
    ):
        raise ValueError("BASE_FROZEN_SOURCE_CHANGED")
    q = [float(r["qc"]) for r in rows]
    qqqe = {r["date"]: r["close"] for r in ext["bars"]}
    start = next(i for i, day in enumerate(dates) if day >= START_DATE)
    if start < 200:
        raise ValueError("NO_QQQ_WARMUP")
    absent = [day for day in dates[start:] if day not in qqqe]
    if absent:
        raise ValueError(f"QQQE_CALENDAR_MISMATCH:{len(absent)}:{absent[:3]}")
    # Need at least 20 completed QQQE sessions, avoiding lookahead.
    if not all(dates[i] in qqqe for i in range(start - 20, start)):
        raise ValueError("QQQE_INITIAL_20DAY_WARMUP_GAP")
    e20 = ema(q, 20)
    f = ema(q, 6)
    s = ema(q, 13)
    macd = [a - b for a, b in zip(f, s)]
    sig = ema(macd, 5)
    sma = []
    for i in range(len(q)):
        sma.append(sum(q[i - 199:i + 1]) / 200 if i >= 199 else None)
    rsi = [50.0] * len(q)
    up = down = 0.0
    for i in range(1, len(q)):
        delta = q[i] - q[i - 1]
        up = (6 * up + max(delta, 0)) / 7
        down = (6 * down + max(-delta, 0)) / 7
        rsi[i] = 100 - 100 / (1 + up / down) if down else 100.0

    # Observed relative 20-session return, NOT actual constituent breadth.
    relative = [None] * len(rows)
    for i in range(start, len(rows)):
        j = i - 1
        a, b = dates[j], dates[j - 20]
        if a not in qqqe or b not in qqqe:
            raise ValueError("QQQE_RELATIVE_WINDOW_INCOMPLETE")
        relative[i] = (qqqe[a] / qqqe[b]) / (q[j] / q[j - 20]) - 1.0

    def levels(kind):
        lv = [0.0] * len(rows)
        prev = 0.0
        pending = 0
        last_boost = -100
        boost_until = -1
        changed = {"delay_sessions": 0, "advanced_sessions": 0}
        for i in range(start, len(rows)):
            base = float(rows[i]["l"])
            j = i - 1
            strong = q[j] > e20[j] and macd[j] > sig[j]
            full_recovery = (
                base in (1.25, 2.0)
                and q[j] > sma[j] * 1.01
                and strong
                and rsi[j] >= 55
                and q[j] > q[j - 5]
            )
            breadth_positive = relative[i] > 0
            target = base
            if "confirm" in kind:
                if base > prev and not breadth_positive and pending < 2:
                    target = prev
                    pending += 1
                    changed["delay_sessions"] += 1
                else:
                    pending = 0
            if "rebound" in kind:
                plateau = (
                    i >= start + 3 and rows[i - 1]["l"] == base
                    and rows[i - 2]["l"] == base and rows[i - 3]["l"] == base
                )
                # QQQ-only is a control; the QQQE-gated challenger additionally
                # requires positive actual equal-weight relative strength.
                confirmed = full_recovery and (
                    breadth_positive if "qqqe" in kind else True
                )
                if confirmed and plateau and i > last_boost + 8:
                    last_boost = i
                    boost_until = i + 2
                if confirmed and i <= boost_until:
                    target = max(target, 2.0 if base == 1.25 else 3.0)
                    if target > base:
                        changed["advanced_sessions"] += 1
            if base == 0:
                target = 0.0
            if target not in (0.0, 1.25, 2.0, 3.0):
                raise ValueError("BAD_TARGET")
            lv[i] = target
            prev = target
        return lv, changed

    def replay(levels, lag=0, slippage_bps=10):
        slip = slippage_bps / 10000
        cash = CAP
        shares = {"q": 0, "t": 0}
        ntrades = 0
        notional = 0.0
        navs = []
        previous = None

        def trade(symbol, qty, price, buying):
            nonlocal cash, ntrades, notional
            qty = max(0, int(qty))
            if buying:
                unit = price * (1 + slip) * (1 + FEE)
                qty = min(qty, math.floor(max(0, cash) / unit))
            else:
                qty = min(qty, shares[symbol])
            if not qty:
                return
            amt = qty * price
            cash += -amt * (1 + slip) * (1 + FEE) if buying else amt * (1 - slip) * (1 - FEE)
            shares[symbol] += qty if buying else -qty
            ntrades += 1
            notional += amt

        for i in range(start, len(rows)):
            row = rows[i]
            target = levels[i - lag] if i - lag >= start else 0.0
            if previous is None or previous != target:
                equity = cash + shares["q"] * row["qo"] + shares["t"] * row["to"]
                wt_t = (target - 1) / 2 if target else 0
                wt_q = 1 - wt_t if target else 0
                qtarget = math.floor(equity * INV * wt_q / row["qo"])
                ttarget = math.floor(equity * INV * wt_t / row["to"])
                trade("q", shares["q"] - qtarget, row["qo"], False)
                trade("t", shares["t"] - ttarget, row["to"], False)
                trade("q", qtarget - shares["q"], row["qo"], True)
                trade("t", ttarget - shares["t"], row["to"], True)
            nav = cash + shares["q"] * row["qc"] + shares["t"] * row["tc"]
            if nav <= 0 or not math.isfinite(nav) or cash < -0.000001:
                raise ValueError("INVALID_LEDGER")
            navs.append(nav)
            previous = target
        return {"navs": navs, "trades": ntrades, "turnover": notional}

    def score(result):
        navs = result["navs"]
        peak = CAP
        dd = 0.0
        for v in navs:
            peak = max(peak, v)
            dd = min(dd, v / peak - 1)
        years = (
            datetime.fromisoformat(dates[-1]) - datetime.fromisoformat(dates[start])
        ).days / 365.2425
        return {
            "cagr": (navs[-1] / CAP) ** (1 / years) - 1,
            "maxdd": dd,
            "terminal_equity": navs[-1],
            "trades": result["trades"],
            "turnover": result["turnover"],
        }

    kinds = ["baseline", "rebound_qqq", "rebound_qqqe", "confirm_qqqe", "confirm_qqqe+rebound_qqqe"]
    variants = {}
    for kind in kinds:
        lv, activity = levels(kind)
        variants[kind] = {"levels": lv, "activity": activity}
    base = score(replay(variants["baseline"]["levels"]))
    results = []
    for kind in kinds:
        obj = variants[kind]
        primary = score(replay(obj["levels"]))
        stress = []
        for lag in (0, 1):
            for slip in (10, 20):
                own = score(replay(obj["levels"], lag, slip))
                benchmark = score(replay(variants["baseline"]["levels"], lag, slip))
                stress.append(
                    {"extra_lag": lag, "slippage_bps": slip,
                     "delta_cagr_pp": 100 * (own["cagr"] - benchmark["cagr"]),
                     "delta_maxdd_pp": 100 * (own["maxdd"] - benchmark["maxdd"])}
                )
        results.append({
            "name": kind, **primary, "activity": obj["activity"],
            "cagr_delta_pp": 100 * (primary["cagr"] - base["cagr"]),
            "maxdd_gain_pp": 100 * (primary["maxdd"] - base["maxdd"]),
            "stress": stress,
        })
    return {
        "status": "OBSERVED_QQQE_PROXY_RESEARCH_ONLY",
        "source_sha256": source["snapshot_sha256"],
        "external_source_sha256": ext["sha256"],
        "external_vendor": ext["vendor"],
        "calendar_aligned": True,
        "period": {"start": dates[start], "end": dates[-1], "sessions": len(rows) - start},
        "QQQE_proxy_NOT_actual_NDXA50R": True,
        "pristine_oos": False,
        "actual_broker_trades": False,
        "israeli_tax_modeled": False,
        "prod_changed": False,
        "automatic_promotion": False,
        "results": results,
    }


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        source = json.loads(INPUT.read_text())
        external = download()
        VENDOR.write_text(json.dumps(external, sort_keys=True, indent=2) + "\n")
        output = compute(source, external)
    except Exception as exc:
        # Explicit fail-closed evidence; never invent a breadth backtest.
        output = {
            "status": "BLOCKED_NO_QUALIFIED_QQQE_PRICE_INPUT",
            "reason": str(exc)[:600],
            "results": [],
            "prod_changed": False,
            "automatic_promotion": False,
        }
    OUT.write_text(json.dumps(output, sort_keys=True, indent=2) + "\n")
    print("QQQE_PROXY_STATUS=" + output["status"])
    if output.get("results"):
        for r in output["results"]:
            print(
                "QQQE_CASE", r["name"], "CAGR", round(r["cagr"] * 100, 2),
                "MaxDD", round(r["maxdd"] * 100, 2), "trades", r["trades"]
            )


if __name__ == "__main__":
    main()
