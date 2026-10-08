"""Immutable paper-only execution assumptions shared by plans, receipts and audits."""
from __future__ import annotations

import hashlib
import json

from stocklens.paper import FEE_BPS, SLIPPAGE_BPS


def as_dict() -> dict:
    return {
        "schema_version": 1,
        "mode": "PROSPECTIVE_PAPER",
        "reductions_time_et": "09:31",
        "additions_time_et": "09:32",
        "whole_shares": True,
        "fee_bps": FEE_BPS,
        "slippage_bps": SLIPPAGE_BPS,
        "broker_orders_authorized": False,
        "live_trading_authorized": False,
    }


def fingerprint() -> str:
    payload = json.dumps(as_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
