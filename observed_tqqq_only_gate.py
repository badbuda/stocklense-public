"""Current research authorization: only observed TQQQ, never synthetic leverage."""
from __future__ import annotations

import json
from pathlib import Path

POLICY = "research/OBSERVED_TQQQ_ONLY_POLICY.json"
REPORT = "research/tradable_tqqq_execution_comparison.json"
PUBLIC = "docs/tradable_tqqq_execution_comparison.json"


def check(policy_path=POLICY, report_path=REPORT, public_path=PUBLIC):
    policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    actual = json.loads(Path(report_path).read_text(encoding="utf-8"))
    errors = []
    if policy.get("policy_id") != "OBSERVED_TQQQ_ONLY_FOR_NEW_RESEARCH":
        errors.append("POLICY_ID")
    if policy.get("active") is not True or policy.get("never_fallback_to_synthetic") is not True:
        errors.append("POLICY_NOT_ENFORCED")
    if actual.get("kind") != "OBSERVED_QQQ_TQQQ_DAILY_OPEN_EXECUTION_PROXY":
        errors.append("NONOBSERVED_INSTRUMENT_PIPELINE")
    if actual.get("observed_instruments") != ["QQQ", "TQQQ"]:
        errors.append("NOT_TWO_OBSERVED_INSTRUMENTS")
    if actual.get("price_source") != "YFINANCE_AUTO_ADJUSTED_DAILY_OPEN_AND_CLOSE":
        errors.append("SYNTHETIC_OR_UNKNOWN_PRICE_SOURCE")
    if not actual.get("price_fingerprint_sha256"):
        errors.append("UNVERIFIED_SOURCE_FINGERPRINT")
    if actual.get("first_valid_real_TQQQ_date", "9999") > "2010-02-12":
        errors.append("TQQQ_INCEPTION_MISMATCH")
    if actual.get("period", {}).get("start", "") < policy.get("earliest_eligible_date", "9999"):
        errors.append("SYNTHETIC_PREINCEPTION_DATES")
    if actual.get("execution_policy", "").find("Next-session") < 0:
        errors.append("LOOKAHEAD_UNCHECKED")
    if actual.get("broker_fills_observed") is not False or actual.get("full_lean_execution_parity") is not False:
        errors.append("FALSE_EXECUTION_PARITY")
    if actual.get("automatic_model_promotion") is not False or actual.get("automatic_trading_authorized") is not False:
        errors.append("UNAUTHORIZED_PROMOTION_OR_BROKER")
    if Path(report_path).read_bytes() != Path(public_path).read_bytes():
        errors.append("PUBLIC_SOURCE_MISMATCH")
    for label in ("no_contributions", "initial_100k_monthly_3500"):
        m = actual.get(label, {})
        if m.get("start") != actual.get("period", {}).get("start") or m.get("end") != actual.get("period", {}).get("end"):
            errors.append(label + "_UNMATCHED_COHORT")
        if (m.get("stocklens", {}).get("paid_capital") !=
                m.get("qqq_buy_hold", {}).get("paid_capital")):
            errors.append(label + "_UNEQUAL_CONTRIBUTIONS")
    if errors:
        raise RuntimeError("OBSERVED_TQQQ_ONLY_POLICY_FAILED:" + ",".join(errors))
    return {
        "status": "PASS",
        "policy_id": policy["policy_id"],
        "report_period": actual["period"],
        "model_changes_allowed": False,
        "synthetic_as_active_performance_evidence": False,
    }


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
