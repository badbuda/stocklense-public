from __future__ import annotations
import json
from pathlib import Path
from typing import Iterable
from backtest_run_store import load_run

def _summary(run: dict) -> dict:
    a=run.get("analytics",{})
    ledger=run.get("ledger") or []
    path=[{"date":x["date"],"equity":x["net_nav"],"paid_capital":x["paid_capital"],"drawdown":x["drawdown"]} for x in ledger]
    return {
        "run_id":run["run_id"],
        "strategy_id":run["strategy_id"],
        "evidence_class":run.get("evidence_class"),
        "execution_parity":False,
        "start":run["start"],"end":run["end"],"sessions":run["sessions"],
        "initial_capital":run.get("request",{}).get("initial_capital"),
        "monthly_contribution":run.get("request",{}).get("monthly_contribution"),
        "transaction_cost_bps":run.get("request",{}).get("transaction_cost_bps"),
        "paid_capital":run["paid_capital"],"end_equity":run["end_equity"],
        "replay_profit_loss":run["replay_profit_loss"],"max_drawdown":run["max_drawdown"],
        "total_estimated_transaction_cost":run["total_estimated_transaction_cost"],
        "ending_to_paid_capital_multiple":a.get("ending_to_paid_capital_multiple"),
        "annualized_volatility_proxy":a.get("annualized_volatility_proxy"),
        "sharpe_proxy_zero_risk_free":a.get("sharpe_proxy_zero_risk_free"),
        "total_turnover_proxy":a.get("total_turnover_proxy"),
        "request_sha256":run["request_sha256"],"rows_sha256":run["rows_sha256"],"ledger_sha256":run["ledger_sha256"],
        "path":path,
    }

def build_history(root="research/backtest_runs", out="docs/backtest_history.json", manifest_path="docs/backtest_scenario_manifest.json") -> dict:
    root=Path(root)
    runs=[]
    for path in sorted(root.glob("*.json")) if root.exists() else []:
        runs.append(_summary(load_run(path)))
    ids=[x["run_id"] for x in runs]
    if len(ids)!=len(set(ids)):
        raise RuntimeError("BACKTEST_HISTORY_DUPLICATE_RUN_ID")
    manifest_file=Path(manifest_path)
    manifest=json.loads(manifest_file.read_text()) if manifest_file.exists() else {}
    manifest_ids={x.get("run_id") for x in manifest.get("runs",[])}
    history_ids={x.get("run_id") for x in runs}
    generation_ok=bool(manifest.get("generation_id")) and manifest_ids.issubset(history_ids)
    payload={
        "schema_version":1,
        "kind":"GENERIC_BACKTEST_HISTORY",
        "status":"PASS" if generation_ok else "BLOCKED",
        "generation_id":manifest.get("generation_id"),
        "generation_consistent":generation_ok,
        "run_count":len(runs),
        "runs":runs,
        "comparison_semantics":"Descriptive side-by-side evidence only. No winner, ranking, promotion, recommendation or execution-parity claim.",
        "automatic_promotion":False,
        "automatic_trading_authorized":False,
    }
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(payload,indent=2)+"\n")
    return payload

if __name__=="__main__":
    print(json.dumps(build_history(),indent=2))
