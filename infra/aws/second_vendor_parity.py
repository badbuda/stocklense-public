"""Pure independent-vendor QQQ historical parity; NEVER changes StockLens 8.0.

Accepts offline CSV exported from a legally accessible independent provider,
not a second Yahoo endpoint. Corporate-action conventions are provenance:
Alpaca adjustment=all means split/dividend/spin-off; frozen yfinance's
auto-adjusted close is NOT assumed bitwise-identical to another vendor.
No credentials, network, AWS, S3 writes or brokerage calls in this module.
"""
from __future__ import annotations
import csv
import hashlib
import io
import math
from datetime import date
from pathlib import Path

from stocklens.core import replay_levels

PROVIDER = "ALPACA_STOCK_BARS_ADJUSTMENT_ALL"
REQUIRED = frozenset({"Date", "Close"})
MIN_ROWS = 300

def parse_csv(data: bytes, *, expected_date: str, name: str) -> tuple[list[str], list[float]]:
    if len(data) > 3_000_000 or b"\x00" in data:
        raise ValueError(name + "_INVALID_OR_OVERSIZE")
    try:
        raw = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(raw, newline=""))
        if set(reader.fieldnames or []) != REQUIRED:
            raise ValueError(name + "_REQUIRES_DATE_CLOSE_CSV")
        rows = list(reader)
        dates = [r["Date"] for r in rows]
        close = [float(r["Close"]) for r in rows]
    except (UnicodeError, csv.Error, KeyError, TypeError) as exc:
        raise ValueError(name + "_INVALID_CSV") from exc
    if len(dates) < MIN_ROWS or len(dates) != len(set(dates)) or dates != sorted(dates):
        raise ValueError(name + "_INCOMPLETE_OR_DUPLICATE_DATES")
    if dates[-1] != expected_date:
        raise ValueError(name + "_INCOMPLETE_LAST_SESSION")
    if any(date.fromisoformat(day).isoformat()!=day for day in dates):
        raise ValueError(name + "_INVALID_DATE")
    if any(not math.isfinite(x) or x <= 0 for x in close):
        raise ValueError(name + "_INVALID_PRICES")
    return dates, close

def _state(level):
    return (level.level, level.defense, level.target_leverage,
            level.qqq_weight, level.tqqq_weight)

def audit(*, frozen_csv: bytes, independent_csv: bytes, expected_session: str,
          vendor: str, adjustment: str, licensed_asof: str) -> dict:
    """Cross-vendor evidentiary diagnostics. Never authorizes a production cutover.

    Fail CLOSED on calendar/incomplete history, divergent decisions or unknown
    adjustment semantics. Accepted diagnostics are STILL not full provenance
    validation, licensed-market-data proof or executable fill parity.
    """
    if vendor != PROVIDER or adjustment != "all":
        raise ValueError("REQUIRE_INDEPENDENT_ADJUSTED_VENDOR_CONVENTION")
    if not licensed_asof or licensed_asof < expected_session:
        raise ValueError("REQUIRE_ASOF_AFTER_COMPLETED_SESSION")
    fdays, fprice = parse_csv(frozen_csv, expected_date=expected_session,name="FROZEN")
    vdays, vprice = parse_csv(independent_csv,expected_date=expected_session,name="INDEPENDENT")
    calendars_equal = fdays == vdays
    if not calendars_equal:
        return {"status":"SECOND_VENDOR_CALENDAR_MISMATCH","calendar_equal":False,
                "frozen_rows":len(fdays),"vendor_rows":len(vdays),
                "second_provider_proven":False,"broker_actions":False}
    # Frozen 8.0 must start after >=252 distinct pre-2009-09-01 warmup
    # sessions, else replay cannot reproduce the actual historical state.
    if sum(d<"2009-09-01" for d in fdays)<252 or expected_session<"2009-09-01":
        raise ValueError("SECOND_VENDOR_INSUFFICIENT_FROZEN_WARMUP")
    frozen_decisions = replay_levels(fprice, fdays)
    vendor_decisions = replay_levels(vprice, vdays)
    mismatches = [
        {"date":a.asof_date,"frozen":list(_state(a)),"vendor":list(_state(b))}
        for a,b in zip(frozen_decisions,vendor_decisions)
        if _state(a)!=_state(b)
    ]
    # Prices differ due to corporate-action history/adjustment publication
    # timing, precision, and venue. Report magnitudes without an arbitrary
    # 8-ULP same-vendor threshold for fundamentally independent datasets.
    diffs = [abs(a-b)/a for a,b in zip(fprice,vprice)]
    return {
        "status":"SECOND_VENDOR_POLICY_DIAGNOSTIC_MATCH" if not mismatches
                 else "SECOND_VENDOR_POLICY_MISMATCH_NO_GO",
        "provider":vendor,"adjustment":"all",
        "licensed_asof":licensed_asof,
        "calendar_equal":True,"sessions":len(fdays),
        "policy_sessions_checked":len(frozen_decisions),
        "policy_disagreement_count":len(mismatches),
        "first_policy_disagreements":mismatches[:8],
        "relative_close_diff_max":max(diffs),
        "relative_close_diff_last":diffs[-1],
        "relative_close_diff_median":sorted(diffs)[len(diffs)//2],
        "frozen_sha256":hashlib.sha256(frozen_csv).hexdigest(),
        "independent_sha256":hashlib.sha256(independent_csv).hexdigest(),
        "second_provider_data_received":True,
        "source_adjustment_reconciled":False,
        "second_provider_proven":False,
        "production_cutover_approved":False,
        "broker_actions":False,
        "warning":"Policy match cannot waive unresolved Yahoo path price drift or prove broker fills.",
    }

def main():
    import argparse
    import json
    p=argparse.ArgumentParser(description="Read-only two-vendor frozen StockLens policy diagnostics")
    p.add_argument("--frozen",type=Path,required=True)
    p.add_argument("--independent",type=Path,required=True)
    p.add_argument("--session",required=True)
    p.add_argument("--licensed-asof",required=True)
    args=p.parse_args()
    out=audit(frozen_csv=args.frozen.read_bytes(),
              independent_csv=args.independent.read_bytes(),
              expected_session=args.session,vendor=PROVIDER,
              adjustment="all",licensed_asof=args.licensed_asof)
    print(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True))
    if out["status"]!="SECOND_VENDOR_POLICY_DIAGNOSTIC_MATCH":
        raise SystemExit(2)

if __name__=="__main__":
    main()
