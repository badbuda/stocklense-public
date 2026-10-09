"""Strict, fail-closed evidence gate for ORIGINAL LEAN daily features.

The exported fields must be from the frozen LEAN algorithm. Yahoo features,
fitted substitutes and a handful of matching rows are NOT source evidence.
A structurally valid CSV is necessary, but NOT sufficient to certify origin.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path

from json_artifacts import write_json_atomic

SCHEMA = Path("governance/qc_lean_feature_export_schema.json")
DEFAULT = Path("governance/qc_lean_daily_features.csv")
TRANSITIONS = Path("governance/qc_724_leverage_transitions.json")
STATE = Path("governance/qc_724_daily_state_manifest.json")
LEVELS = {1: 1.25, 2: 2.0, 3: 3.0}
ACCEPTED_LEVERAGES = (0.0, 1.25, 2.0, 3.0)


def numeric(value):
    x = float(value)
    if not math.isfinite(x):
        raise ValueError("NONFINITE_VALUE")
    return x


def transition_hash(transitions):
    canonical = json.dumps(transitions, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def original_daily_leverage_hash(rows):
    """SHA256 all dated LEAN leverage decisions, not merely 67 transitions."""
    payload = [[r["date"], float(r["leverage"])] for r in rows]
    canonical = json.dumps(payload, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def original_session_dates_hash(dates):
    return hashlib.sha256("\\n".join(dates).encode()).hexdigest()


def validate_export(path=DEFAULT, schema_path=SCHEMA, transitions_path=TRANSITIONS, state_path=STATE):
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    source = Path(path)
    if not source.exists():
        return {"status": "MISSING", "path": str(source), "same_input_parity_ready": False,
                "source_authenticity_proven": False, "missing": "ORIGINAL LEAN daily feature export"}
    golden = json.loads(Path(transitions_path).read_text(encoding="utf-8"))
    state = json.loads(Path(state_path).read_text(encoding="utf-8"))
    errors = []
    with source.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = reader.fieldnames or []
        rows = list(reader)
    required = schema["required_columns"]
    missing = [name for name in required if name not in columns]
    if missing:
        return {"status": "INVALID", "path": str(source), "same_input_parity_ready": False,
                "source_authenticity_proven": False, "errors": ["COLUMNS_MISSING"],
                "missing_columns": missing}
    dates, counts, transitions, previous, values, daily_states = [], Counter(), [], None, [], []
    for i, row in enumerate(rows):
        try:
            day = date.fromisoformat(row["date"])
            if day.isoformat() != row["date"]:
                raise ValueError("NONCANONICAL_DATE")
            lev = numeric(row["leverage"])
            level = int(row["level"])
            if str(level) != str(row["level"]).strip():
                raise ValueError("INVALID_LEVEL_FORMAT")
            defense = str(row["defense"]).strip().lower()
            if defense not in ("true", "false"):
                raise ValueError("INVALID_DEFENSE_BOOLEAN")
            if level not in LEVELS or lev not in ACCEPTED_LEVERAGES:
                raise ValueError("ILLEGAL_LEVEL_OR_LEVERAGE")
            if lev != (0.0 if defense == "true" else LEVELS[level]):
                raise ValueError("INCONSISTENT_EFFECTIVE_LEVERAGE")
            feature_values = [numeric(row[k]) for k in ("close", "sma50", "sma200", "vol20", "mom12")]
            if feature_values[0] <= 0 or feature_values[1] <= 0 or feature_values[2] <= 0 or feature_values[3] < 0:
                raise ValueError("INVALID_FEATURE_RANGE")
            dates.append(day.isoformat())
            daily_states.append({"date": day.isoformat(), "leverage": lev})
            counts[str(lev)] += 1
            values.append(",".join(str(row.get(k, "")) for k in required))
            if previous is None or lev != previous:
                # Original golden reference serializes whole-number levels as ints.
                transitions.append([day.isoformat(), int(lev) if lev.is_integer() else lev])
            previous = lev
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            errors.append(f"INVALID_ROW_{i + 1}:{type(exc).__name__}")
            break
    if len(rows) != schema["expected_sessions"] or len(rows) != state["sessions"]:
        errors.append("SESSION_COUNT")
    if not dates or dates[0] != schema["first_date"] or dates[-1] != schema["last_date"]:
        errors.append("DATE_BOUNDARIES")
    if dates != sorted(set(dates)):
        errors.append("UNSORTED_OR_DUPLICATE_DATES")
    if transitions != golden["transitions"] or transition_hash(transitions) != golden["transition_sha256"]:
        errors.append("FROZEN_TRANSITION_DRIFT")
    expected_counts = {str(float(k)): v for k, v in state["leverage_counts"].items()}
    if dict(counts) != expected_counts:
        errors.append("FROZEN_DAILY_LEVERAGE_COUNTS_DRIFT")
    # Original chart-derived fingerprints lock EVERY dated level, even on
    # sessions where no transition occurred. This detects a substituted holiday,
    # a missing session and a fabricated duplicate (while transition SHA passes).
    daily_sha = original_daily_leverage_hash(daily_states)
    dates_sha = original_session_dates_hash(dates)
    if daily_sha != state.get("daily_date_leverage_sha256"):
        errors.append("FROZEN_DAILY_STATE_SHA_DRIFT")
    if dates_sha != state.get("daily_session_dates_sha256"):
        errors.append("FROZEN_SESSION_CALENDAR_SHA_DRIFT")
    checks = {
        "columns_complete": not missing,
        "session_count": len(rows) == schema["expected_sessions"] == state["sessions"],
        "first_date": bool(dates) and dates[0] == schema["first_date"],
        "last_date": bool(dates) and dates[-1] == schema["last_date"],
        "ordered_unique_dates": dates == sorted(set(dates)),
        "finite_valid_features_and_states": not any(x.startswith("INVALID_ROW") for x in errors),
        "frozen_transition_identity": transitions == golden["transitions"],
        "frozen_daily_leverage_distribution": dict(counts) == expected_counts,
        "original_daily_state_sha_match": daily_sha == state.get("daily_date_leverage_sha256"),
        "original_calendar_sha_match": dates_sha == state.get("daily_session_dates_sha256"),
    }
    valid = not errors and all(checks.values())
    return {
        "status": "VALID" if valid else "INVALID", "path": str(source),
        "rows": len(rows), "sha256": hashlib.sha256("\n".join(values).encode()).hexdigest(),
        "checks": checks, "errors": sorted(set(errors)), "missing_columns": [],
        "reference_transition_sha256": golden["transition_sha256"],
        "daily_date_leverage_sha256": daily_sha,
        "daily_session_dates_sha256": dates_sha,
        "source_authenticity_proven": False,
        "same_input_parity_ready": valid,
        "scope": "Structural and immutable original-LEAN state check only; original provenance still requires the native LEAN source artifact.",
    }


def build(out="shadow_history/qc_input_ingestion.json"):
    result = validate_export()
    write_json_atomic(out, result)
    return result


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
