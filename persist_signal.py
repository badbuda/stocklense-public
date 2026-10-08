from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any


def _decision_fingerprint(report: dict[str, Any]) -> dict[str, Any]:
    """Fields that define the frozen StockLens decision for one completed session."""
    x = report["latest"]
    return {
        "asof_date": x["asof_date"],
        "level": x["level"],
        "defense_active": x["defense_active"],
        "target_leverage": x["target_leverage"],
        "qqq_weight": x["qqq_weight"],
        "tqqq_weight": x["tqqq_weight"],
        "action": report["action"],
        "execution_plan": report.get("execution_plan"),
    }


def _full_fingerprint(report: dict[str, Any]) -> dict[str, Any]:
    """Scientific rerun identity, excluding only volatile timestamps."""
    audit = report.get("data_audit", {})
    return {
        "version": report.get("version"),
        "mode": report.get("mode"),
        "signal_source": report.get("signal_source"),
        "state_replay": report.get("state_replay"),
        "latest": report.get("latest"),
        "previous": report.get("previous"),
        "action": report.get("action"),
        "execution_plan": report.get("execution_plan"),
        "data_identity": {
            "rows": audit.get("rows"),
            "first_date": audit.get("first_date"),
            "last_date": audit.get("last_date"),
            "last_close": audit.get("last_close"),
            "last_completed_date": audit.get("last_completed_date"),
        },
    }


def _stable_hash(value: dict[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _write_csv_index(history_dir: Path, report: dict[str, Any]) -> None:
    path = history_dir / "signals.csv"
    x = report["latest"]
    feat = x["features"]
    audit = report["data_audit"]
    row = {
        "asof_date": x["asof_date"],
        "version": report["version"],
        "action": report["action"],
        "level": x["level"],
        "defense_active": x["defense_active"],
        "target_leverage": x["target_leverage"],
        "qqq_weight": x["qqq_weight"],
        "tqqq_weight": x["tqqq_weight"],
        "qqq_adjusted_close": feat["close"],
        "sma50": feat["sma50"],
        "sma200": feat["sma200"],
        "vol20": feat["vol20"],
        "mom12": feat["mom12"],
        "generated_at_utc": report["generated_at_utc"],
        "source": audit.get("source"),
        "raw_last_date": audit.get("raw_last_date"),
        "last_completed_date": audit.get("last_completed_date"),
        "dropped_incomplete_current_session": audit.get("dropped_incomplete_current_session"),
    }

    rows: list[dict[str, Any]] = []
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    if any(r["asof_date"] == row["asof_date"] for r in rows):
        return
    rows.append({k: str(v) for k, v in row.items()})
    rows.sort(key=lambda r: r["asof_date"])
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerows(rows)


def _record_nonmaterial_revision(
    hist: Path,
    asof: str,
    old: dict[str, Any],
    new: dict[str, Any],
) -> tuple[str, str]:
    """Preserve input drift without rewriting the original prospective decision."""
    old_hash = _stable_hash(_full_fingerprint(old))
    new_hash = _stable_hash(_full_fingerprint(new))
    revisions = hist / "revisions"
    revisions.mkdir(parents=True, exist_ok=True)
    candidate = revisions / f"{asof}_{new_hash[:12]}.json"
    if not candidate.exists():
        candidate.write_text(json.dumps(new, indent=2), encoding="utf-8")

    audit_path = hist / "revision_audit.csv"
    row = {
        "asof_date": asof,
        "observed_at_utc": new.get("generated_at_utc"),
        "original_hash": old_hash,
        "rerun_hash": new_hash,
        "decision_changed": False,
        "disposition": "ORIGINAL_PRESERVED_NONMATERIAL_INPUT_DRIFT",
    }
    existing_hashes: set[str] = set()
    if audit_path.exists():
        with audit_path.open("r", encoding="utf-8", newline="") as fh:
            existing_hashes = {r.get("rerun_hash", "") for r in csv.DictReader(fh)}
    if new_hash not in existing_hashes:
        exists = audit_path.exists()
        with audit_path.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
            if not exists:
                writer.writeheader()
            writer.writerow(row)
    return old_hash, new_hash


def persist(
    signal_json: str = "output/latest_signal.json",
    signal_md: str = "output/latest_signal.md",
    history_dir: str = "shadow_history",
) -> dict[str, str]:
    signal_json_path = Path(signal_json)
    signal_md_path = Path(signal_md)
    hist = Path(history_dir)
    hist.mkdir(parents=True, exist_ok=True)

    report = json.loads(signal_json_path.read_text(encoding="utf-8"))
    asof = report["latest"]["asof_date"]
    action = report["action"]
    dated_json = hist / f"{asof}.json"
    dated_md = hist / f"{asof}.md"

    new_signal_date = not dated_json.exists()
    input_drift = False

    if dated_json.exists():
        old = json.loads(dated_json.read_text(encoding="utf-8"))
        if _decision_fingerprint(old) != _decision_fingerprint(report):
            raise RuntimeError(
                "DATA_REVISION_CONFLICT: rerun changed the frozen StockLens decision "
                f"for completed session {asof}. Historical record was NOT overwritten."
            )
        if _full_fingerprint(old) != _full_fingerprint(report):
            input_drift = True
            _record_nonmaterial_revision(hist, asof, old, report)
    else:
        shutil.copy2(signal_json_path, dated_json)
        shutil.copy2(signal_md_path, dated_md)
        _write_csv_index(hist, report)
        shutil.copy2(signal_json_path, hist / "latest.json")
        shutil.copy2(signal_md_path, hist / "latest.md")

    state_changed = action != "NO_CHANGE"
    notify = new_signal_date and state_changed
    result = {
        "asof_date": asof,
        "action": action,
        "new_signal_date": str(new_signal_date).lower(),
        "state_changed": str(state_changed).lower(),
        "notify": str(notify).lower(),
        "input_drift_detected": str(input_drift).lower(),
        "target_leverage": str(report["latest"]["target_leverage"]),
        "defense": "ON" if report["latest"]["defense_active"] else "OFF",
    }
    return result


def main() -> int:
    result = persist()
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fh:
            for key, value in result.items():
                fh.write(f"{key}={value}\n")
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
