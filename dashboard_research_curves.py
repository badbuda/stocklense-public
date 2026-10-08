"""Render explicit Yahoo-based research approximations for public visualization."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

SOURCE = "research/data/stocklens8_daily.csv"
OUTPUT = "docs/research_curves.json"


def build(source: str = SOURCE, output: str = OUTPUT) -> dict:
    path = Path(source)
    if not path.is_file():
        raise RuntimeError("RESEARCH_CURVES_SOURCE_MISSING")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"date", "qqq_return", "baseline_return"}
    if len(rows) < 2 or not required.issubset(rows[0]):
        raise RuntimeError("RESEARCH_CURVES_SOURCE_SCHEMA_INVALID")
    series = {"QQQ": [], "SL8_RESEARCH_APPROX": []}
    qqq = baseline = 100.0
    last_date = ""
    for row in rows:
        day = row["date"]
        if len(day) != 10 or day <= last_date:
            raise RuntimeError("RESEARCH_CURVES_DATE_SEQUENCE_INVALID")
        last_date = day
        qret = float(row["qqq_return"])
        bret = float(row["baseline_return"])
        if not all(math.isfinite(r) and r > -1.0 for r in (qret, bret)):
            raise RuntimeError("RESEARCH_CURVES_RETURN_INVALID")
        qqq *= 1.0 + qret
        baseline *= 1.0 + bret
        series["QQQ"].append({"date": day, "nav": round(qqq, 6)})
        series["SL8_RESEARCH_APPROX"].append({"date": day, "nav": round(baseline, 6)})
    payload = {
        "schema_version": 2,
        "evidence_scope": "RESEARCH_APPROXIMATION_NOT_QC_PARITY",
        "normalized_start": 100,
        "series": series,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_rows": len(rows),
        "full_lean_execution_parity": False,
        "automatic_promotion": False,
        "warning": "Yahoo-adjusted QQQ compounded with modeled baseline exposure; not executable TQQQ returns or canonical QuantConnect parity. No challenger is promoted."
    }
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = build()
    print(json.dumps({"status": "PASS", "sessions": result["source_rows"], "scope": result["evidence_scope"]}))
