"""Audit user-supplied QC 7.33 observer CSV without publishing native input history.

Usage:
 python qc_733_observer_audit.py /private/stocklens_qc_lean_daily_features_3774.csv
Source is an observer-instrumented 7.33 reconciliation algorithm, NOT original
7.24 source identity. No execution fill or Yahoo feature parity is claimed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from pathlib import Path

from qc_input_ingestion import validate_export
from stocklens.core import Features, next_level, defense_active, LEVEL_LEVERAGE

def evaluate(path: str | Path) -> dict:
    path = Path(path)
    structural = validate_export(path=path)
    result = {
        "schema_version": 1,
        "kind": "QC733_NATIVE_OBSERVER_SAME_INPUT_DECISION_AUDIT",
        "source_version": "7.33-FROZEN724-PARITY-RECONCILIATION",
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None,
        "structural_check_status": structural["status"],
        "source_authenticity_proven": False,
        "original_724_source_identity_proven": False,
        "native_chart_precision_bit_exact_proven": False,
        "lean_to_yahoo_feature_parity_proven": False,
        "broker_execution_parity_proven": False,
        "live_trading_authorized": False,
        "claim_boundary": "QC 7.33 chart observer state-machine agreement only; private QC 7.24 source, chart serialization and Yahoo feature differences remain unverified.",
    }
    if structural["status"] != "VALID":
        result.update(status="BLOCKED_INVALID_OR_INCOMPLETE_OBSERVER", compared_sessions=0,
                      errors=structural.get("errors", []))
        return result
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    prior = None
    mismatches = []
    matched = 0
    for row in rows:
        f = Features(*(float(row[k]) for k in ("close","sma50","sma200","vol20","mom12")))
        level = next_level(f, prior)
        defense = defense_active(f)
        exposure = 0.0 if defense else LEVEL_LEVERAGE[level]
        same = (level == int(row["level"])
                and defense == (row["defense"].lower() == "true")
                and math.isclose(exposure, float(row["leverage"]), rel_tol=0, abs_tol=1e-12))
        if same:
            matched += 1
        elif len(mismatches) < 20:
            mismatches.append({"date":row["date"],"python_level":level,"qc_level":row["level"],
                               "python_defense":defense,"qc_defense":row["defense"],
                               "python_leverage":exposure,"qc_leverage":row["leverage"]})
        prior = level
    result.update(
        status=("OBSERVER_733_DECISIONS_MATCH_REFERENCE_SOURCE_UNATTESTED" if matched == len(rows)
                else "OBSERVER_733_SAME_INPUT_MISMATCH"),
        compared_sessions=len(rows), matched_sessions=matched,
        mismatched_sessions=len(rows)-matched, first_mismatches=mismatches,
        observer_math_parity=(matched == len(rows)),
        structurally_matches_frozen_724_states=True,
    )
    return result

if __name__ == "__main__":
    if len(sys.argv) not in (2,3):
        raise SystemExit("usage: python qc_733_observer_audit.py INPUT.csv [OUTPUT.json]")
    result=evaluate(sys.argv[1])
    if len(sys.argv)==3:
        Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))
    if not result.get("observer_math_parity"):
        raise SystemExit(1)
