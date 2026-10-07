from __future__ import annotations
import json
from pathlib import Path

def persist_run(result: dict, root: str = "research/backtest_runs") -> Path:
    """Persist a deterministic research run without overwriting divergent evidence."""
    if result.get("kind") != "GENERIC_BACKTEST_RESULT" or result.get("status") != "PASS":
        raise ValueError("BACKTEST_RESULT_NOT_PERSISTABLE")
    required=("request_sha256","rows_sha256","ledger_sha256","strategy_id")
    if any(not result.get(k) for k in required):
        raise ValueError("BACKTEST_RESULT_PROVENANCE_MISSING")
    run_id=f'{result["strategy_id"]}-{result["request_sha256"][:12]}-{result["rows_sha256"][:12]}-{result["ledger_sha256"][:12]}'
    path=Path(root)/f"{run_id}.json"
    payload=dict(result)
    payload["run_id"]=run_id
    encoded=json.dumps(payload,sort_keys=True,indent=2)+"\n"
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        existing=path.read_text()
        if existing!=encoded:
            raise RuntimeError("BACKTEST_RUN_ID_COLLISION_OR_MUTATION")
        return path
    path.write_text(encoded)
    return path

def load_run(path: str | Path) -> dict:
    payload=json.loads(Path(path).read_text())
    if payload.get("kind")!="GENERIC_BACKTEST_RESULT" or not payload.get("run_id"):
        raise ValueError("BACKTEST_RUN_INVALID")
    return payload
