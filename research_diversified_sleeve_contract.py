"""Fail-closed external GLD/TLT observed-ETF source contract, NOT a return model.

No fabricated gold/bond correlations or synthetic prices. Even contract-valid
supplied data remain UNVERIFIED until an independent feed/source audit.
"""
from __future__ import annotations
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit
import hashlib
import json
import math

from observed_etf_two_question_audit import load

INPUT = Path("research/private/non_nasdaq_observed_etfs.json")
OUT = Path("research/results/non_nasdaq_sleeve_readiness.json")
REPORT = Path("research/reports/non_nasdaq_sleeve_readiness.md")
SYMBOLS = ("GLD", "TLT")


def inspect(market_rows, supplied):
    if not isinstance(supplied, dict) or supplied.get("schema_version") != 1:
        raise ValueError("SLEEVE_SCHEMA_INVALID")
    if supplied.get("price_basis") != "OBSERVED_ADJUSTED_DAILY_OPEN_CLOSE":
        raise ValueError("SLEEVE_NOT_OBSERVED_ADJUSTED_BARS")
    bars = supplied.get("bars")
    if not isinstance(bars, dict) or set(bars) != set(SYMBOLS):
        raise ValueError("SLEEVE_MISSING_REQUIRED_NONNASDAQ_ETF")
    refs = supplied.get("source_urls")
    if not isinstance(refs, dict) or set(refs) != set(SYMBOLS):
        raise ValueError("SLEEVE_MISSING_PRICE_PROVENANCE")
    for symbol in SYMBOLS:
        u = urlsplit(refs[symbol]) if isinstance(refs[symbol], str) else None
        if not u or u.scheme != "https" or not u.netloc or u.username or u.password:
            raise ValueError("SLEEVE_UNTRUSTED_SOURCE_URL")
    market_dates = [r["date"] for r in market_rows]
    if market_dates != sorted(set(market_dates)):
        raise ValueError("SLEEVE_BASE_MARKET_DATES_INVALID")
    if len(market_dates) < 2:
        raise ValueError("SLEEVE_BASE_MARKET_TOO_SHORT")
    for symbol in SYMBOLS:
        series = bars[symbol]
        if not isinstance(series, list) or len(series) != len(market_dates):
            raise ValueError("SLEEVE_MISSING_FULL_REAL_ETF_COVERAGE")
        days = []
        for p in series:
            if not isinstance(p, dict):
                raise ValueError("SLEEVE_INVALID_BAR")
            day = p.get("date")
            try:
                date.fromisoformat(day)
            except (TypeError, ValueError) as e:
                raise ValueError("SLEEVE_DATE_INVALID") from e
            days.append(day)
            for field in ("open", "close"):
                v = p.get(field)
                if type(v) not in (float, int) or not math.isfinite(v) or v <= 0:
                    raise ValueError("SLEEVE_INVALID_PRICE")
        if days != market_dates:
            raise ValueError("SLEEVE_ETF_DATES_NOT_ALIGNED")
    fingerprint = hashlib.sha256(
        json.dumps(bars, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "status": "CONTRACT_COMPLETE_SOURCE_AUDIT_STILL_REQUIRED",
        "source_data_sha256": fingerprint,
        "symbols": list(SYMBOLS),
        "matched_observed_sessions": len(market_dates),
        "source_first_seen_independently_proven": False,
        "split_distribution_adjustment_independently_audited": False,
        "live_trade_eligible": False, "price_alpha_proven": False,
        "strategy_model_promotion": False,
    }


def build():
    base = load()
    result = {
        "schema_version": 1, "kind": "NONNASDAQ_ETF_DIVERSIFICATION_READINESS",
        "status": "BLOCKED_NO_OBSERVED_GLD_TLT_SOURCE",
        "source_available": INPUT.exists(),
        "frozen_qqq_tqqq_sessions": len(base["daily"]),
        "price_source_snapshot_sha256": base.get("snapshot_sha256"),
        "instrument_scope": list(SYMBOLS),
        "historical_diversification_alpha_proven": False,
        "no_synthetic_etf_prices": True,
        "source_independently_audited": False,
        "frozen_stocklens8_changed": False,
        "capital_deployment_authorized": False,
        "automatic_promotion": False,
    }
    if INPUT.exists():
        try:
            result.update(inspect(base["daily"], json.loads(INPUT.read_text(encoding="utf-8"))))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            result.update(status="BLOCKED_INVALID_OR_INCOMPLETE_SLEEVE_PRICES",
                          error_code=str(e)[:120])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    REPORT.write_text("# Non-Nasdaq observed GLD/TLT data readiness\n\n" +
                      "Status: **" + result["status"] + "**.\n\n" +
                      "Complete adjusted observed bars, exact exchange-session alignment, " +
                      "proven source lineage and an independent source audit are prerequisites. " +
                      "No hypothetical diversification CAGR or cash-free bond sleeve is claimed.\n")
    print("STOCKLENS_SLEEVE_READINESS=" + json.dumps(result, sort_keys=True))
    return result


if __name__ == "__main__":
    build()
