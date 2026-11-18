"""Fail-closed paired-run research evidence gate; no strategy or tax-law claims.

Inputs are per-session ledger rows from identical market data and execution assumptions.
This does not calculate Israeli statutory tax; tax must be independently modeled.
"""
from decimal import Decimal, InvalidOperation
from datetime import date
import re

def number(value):
    try:
        x = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("INVALID_NUMBER") from exc
    if not x.is_finite():
        raise ValueError("NONFINITE_NUMBER")
    return x

def audit_pair(before, after):
    try:
        required = ("dataset_sha256", "execution_sha256", "sessions", "lag_sessions", "source_kind")
        if any(k not in obj for obj in (before, after) for k in required):
            raise ValueError("MISSING_PROVENANCE")
        for key in ("dataset_sha256", "execution_sha256", "sessions", "lag_sessions", "source_kind"):
            if before[key] != after[key]:
                raise ValueError("UNPAIRED_" + key.upper())
        if not all(isinstance(obj["sessions"], list) and obj["sessions"] for obj in (before, after)):
            raise ValueError("EMPTY_SESSIONS")
        for key in ("dataset_sha256", "execution_sha256"):
            if not isinstance(before[key], str) or re.fullmatch(r"[0-9a-f]{64}", before[key]) is None:
                raise ValueError("INVALID_" + key.upper())
        try:
            days = [date.fromisoformat(s) for s in before["sessions"]]
        except (TypeError, ValueError) as exc:
            raise ValueError("INVALID_SESSION_DATE") from exc
        if any(days[i] >= days[i + 1] for i in range(len(days) - 1)):
            raise ValueError("NON_MONOTONIC_OR_DUPLICATE_SESSIONS")
        if type(before["lag_sessions"]) is not int or before["lag_sessions"] < 1:
            raise ValueError("LAG_1_REQUIRED")
        if before["source_kind"] not in ("observed_pit", "proxy", "synthetic"):
            raise ValueError("UNDECLARED_SOURCE_KIND")
        if before.get("tax_mode") != "none" or after.get("tax_mode") != "illustrative":
            raise ValueError("TAX_MODE_NOT_EXPLICIT")
        if after.get("statutory_tax_verified") is not False:
            raise ValueError("TAX_LEGAL_STATUS_MISSING")
        if before.get("cash_timing") != after.get("cash_timing"):
            raise ValueError("CASH_TIMING_MISMATCH")
        if before.get("cash_timing") not in ("immediate", "year_end"):
            raise ValueError("CASH_TIMING_UNDECLARED")
        a, b = before["rows"], after["rows"]
        if len(a) != len(b) or len(a) != len(before["sessions"]):
            raise ValueError("ROW_COUNT_MISMATCH")
        cumulative_tax = Decimal(0)
        for i, (raw, taxed) in enumerate(zip(a, b)):
            if raw["session"] != before["sessions"][i] or taxed["session"] != raw["session"]:
                raise ValueError("ROW_SESSION_MISMATCH")
            for key in ("gross_equity_nis", "fees_nis", "trade_fingerprint"):
                if raw[key] != taxed[key]:
                    raise ValueError("TRADE_OR_GROSS_MISMATCH")
            tax = number(taxed["tax_paid_nis"])
            if tax < 0:
                raise ValueError("NEGATIVE_TAX")
            cumulative_tax += tax
            gross = number(raw["gross_equity_nis"])
            net = number(taxed["net_equity_nis"])
            # Illustrative immediate settlement: gross portfolio wealth minus
            # cumulative tax payments, not realized P&L or total sale proceeds.
            if before["cash_timing"] == "immediate" and net != gross - cumulative_tax:
                raise ValueError("NET_EQUITY_RECONCILIATION_FAILED")
        if before["cash_timing"] == "year_end":
            raise ValueError("YEAR_END_SETTLEMENT_NOT_IMPLEMENTED")
        return {"status": "STRUCTURAL_ONLY", "source_kind": before["source_kind"],
                "sessions": len(a), "cumulative_tax_nis": str(cumulative_tax),
                "performance_verified": False, "tax_law_verified": False}
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return {"status": "BLOCKED", "reason": str(exc),
                "performance_verified": False, "tax_law_verified": False}
