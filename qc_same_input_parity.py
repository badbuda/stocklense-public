"""Compare Python's frozen decision rules to ORIGINAL LEAN-exported feature inputs.

A match on an incomplete or unverifiable CSV can never certify parity.
The comparison intentionally does not modify model parameters or historical decisions.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from stocklens.core import Features, next_level, defense_active, LEVEL_LEVERAGE
from qc_input_ingestion import validate_export
from json_artifacts import write_json_atomic


def compare(path="governance/qc_lean_daily_features.csv",
            out="shadow_history/qc_same_input_parity.json"):
    check = validate_export(path=path)
    if check["status"] != "VALID":
        result = {
            "status": "BLOCKED_MISSING_IDENTICAL_INPUT_EXPORT"
                if check["status"] == "MISSING" else "BLOCKED_INVALID_LEAN_EXPORT",
            "same_input_parity_proven": False,
            "same_input_state_match": False,
            "compared_sessions": 0, "input_validation": check,
            "claim_boundary": "No partial or malformed input may establish parity.",
        }
        write_json_atomic(out, result)
        return result
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    prev = None
    mismatches = []
    matched = 0
    for row in rows:
        features = Features(
            close=float(row["close"]), sma50=float(row["sma50"]),
            sma200=float(row["sma200"]), vol20=float(row["vol20"]),
            mom12=float(row["mom12"]),
        )
        level = next_level(features, prev)
        defense = defense_active(features)
        effective = 0.0 if defense else LEVEL_LEVERAGE[level]
        lean_level = int(row["level"])
        lean_defense = row["defense"].strip().lower() == "true"
        lean_leverage = float(row["leverage"])
        ok = (level == lean_level and defense == lean_defense
              and math.isclose(effective, lean_leverage, rel_tol=0, abs_tol=1e-12))
        if ok:
            matched += 1
        elif len(mismatches) < 20:
            mismatches.append({
                "date": row["date"],
                "python": {"level": level, "defense": defense, "leverage": effective},
                "lean": {"level": lean_level, "defense": lean_defense, "leverage": lean_leverage},
                "features": {key: getattr(features, key)
                             for key in ("close", "sma50", "sma200", "vol20", "mom12")},
            })
        prev = level
    identical = bool(rows) and matched == len(rows)
    # Structural validation / immutable transition matching cannot independently
    # prove the CSV was captured from the original LEAN run. Keep that distinction.
    provenance_proven = check.get("source_authenticity_proven") is True
    proven = identical and provenance_proven
    result = {
        "status": "EXACT_SAME_INPUT_COMPUTATION_SOURCE_UNATTESTED" if identical and not proven
                  else "FULL_SAME_INPUT_PARITY_PROVEN" if proven else "MISMATCH",
        "same_input_parity_proven": proven,
        "same_input_state_match": identical,
        "source_authenticity_proven": provenance_proven,
        "compared_sessions": len(rows),
        "matched_sessions": matched,
        "mismatch_count": len(rows) - matched,
        "match_rate": matched / len(rows) if rows else 0,
        "first_mismatches": mismatches,
        "input_validation": check,
        "claim_boundary": "Same-input decision agreement is conditional on LEAN CSV provenance; structural validity alone never proves original LEAN source identity.",
    }
    write_json_atomic(out, result)
    return result


if __name__ == "__main__":
    print(json.dumps(compare(), indent=2))
