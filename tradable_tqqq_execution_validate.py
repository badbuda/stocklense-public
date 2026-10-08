"""Fail-closed validation of the observed QQQ/TQQQ execution-proxy report."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

SOURCE = Path("research/tradable_tqqq_execution_comparison.json")
PUBLIC = Path("docs/tradable_tqqq_execution_comparison.json")


def validate(source=SOURCE, public=PUBLIC):
    a, b = Path(source), Path(public)
    if not a.is_file() or not b.is_file() or a.read_bytes() != b.read_bytes():
        raise ValueError("TRADABLE_REPORT_PUBLICATION_MISMATCH")
    r = json.loads(a.read_text(encoding="utf-8"))
    fail = []
    if r.get("status") != "PASS" or r.get("baseline") != "StockLens 8.0 FROZEN":
        fail.append("STATUS_OR_BASELINE")
    if r.get("observed_instruments") != ["QQQ", "TQQQ"]:
        fail.append("REAL_INSTRUMENTS")
    if r.get("full_lean_execution_parity") is not False or r.get("broker_fills_observed") is not False:
        fail.append("EXECUTION_CLAIM")
    if r.get("intraday_0931_0932_fills_observed") is not False:
        fail.append("MINUTE_FILL_CLAIM")
    if r.get("automatic_trading_authorized") is not False or r.get("automatic_model_promotion") is not False:
        fail.append("GOVERNANCE")
    period = r.get("period", {})
    if period.get("start", "") < "2010-02-09" or period.get("end", "") < period.get("start", "") or period.get("sessions", 0) < 3000:
        fail.append("OBSERVED_TQQQ_PERIOD")
    sha = r.get("price_fingerprint_sha256", "")
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        fail.append("PROVENANCE_SHA256")
    for key in ("no_contributions", "initial_100k_monthly_3500"):
        cohort = r.get(key, {})
        if cohort.get("sessions") != period.get("sessions"):
            fail.append(key + "_PERIOD")
        s, q = cohort.get("stocklens", {}), cohort.get("qqq_buy_hold", {})
        for name, model in (("stocklens", s), ("qqq", q)):
            fields = ("ending_equity", "paid_capital", "max_drawdown", "total_modeled_commissions",
                      "total_modeled_slippage", "trades")
            if not all(isinstance(model.get(field), (int, float))
                       and math.isfinite(float(model[field])) for field in fields):
                fail.append(key + "_" + name + "_METRICS")
            if model.get("max_drawdown", 1) > 0 or model.get("max_drawdown", -2) < -1:
                fail.append(key + "_" + name + "_DRAWDOWN")
        if s.get("paid_capital") != q.get("paid_capital"):
            fail.append(key + "_PAID_CAPITAL")
        if cohort.get("additional_signal_lag_sessions") != 0:
            fail.append(key + "_SIGNAL_LAG")
    if len(r.get("slippage_stress_no_contributions", [])) != 5:
        fail.append("COST_GRID")
    if len(r.get("signal_lag_stress_no_contributions", [])) != 3:
        fail.append("LAG_GRID")
    if fail:
        raise ValueError("INVALID_OBSERVED_ETF_REPLAY:" + ",".join(sorted(set(fail))))
    print(json.dumps({"status": "PASS", "sessions": period["sessions"],
                      "source_sha256": sha, "claim_boundary": "OBSERVED_ETF_DAILY_OPEN_PROXY_ONLY"}))
    return r


if __name__ == "__main__":
    validate()
