from __future__ import annotations
import json
from pathlib import Path
from backtest_contract import FrozenExposureReplayAdapter, stocklens_8_request
from backtest_engine import run_backtest
from backtest_run_store import persist_run

def comparison_summary(result: dict) -> dict:
    """Human-facing, non-ranking summary for Control Center consumption."""
    return {
        "strategy_id":result["strategy_id"],
        "evidence_class":result["evidence_class"],
        "execution_parity":False,
        "window":{"start":result["start"],"end":result["end"],"sessions":result["sessions"]},
        "capital":{"paid":result["paid_capital"],"ending":result["end_equity"],"replay_profit_loss":result["replay_profit_loss"]},
        "risk":{"max_drawdown":result["max_drawdown"],"annualized_volatility_proxy":result.get("analytics",{}).get("annualized_volatility_proxy"),"sharpe_proxy_zero_risk_free":result.get("analytics",{}).get("sharpe_proxy_zero_risk_free")},
        "cost":{"estimated_total":result["total_estimated_transaction_cost"],"total_turnover_proxy":result.get("analytics",{}).get("total_turnover_proxy")},
        "provenance":{"request_sha256":result["request_sha256"],"rows_sha256":result["rows_sha256"],"ledger_sha256":result["ledger_sha256"]},
        "semantics":"Descriptive frozen replay result; no ranking, promotion, recommendation or LEAN execution-parity claim.",
    }


def run_workbench(path="docs/workbench.json", initial=100000.0, monthly=3500.0, cost_bps=5.0, start=None, end=None, persist=True):
    """Run the frozen replay through the generic M2 engine and optionally persist it."""
    doc=json.loads(Path(path).read_text())
    rows=doc.get("replay",{}).get("rows") or []
    if len(rows)<2:
        raise RuntimeError("BACKTEST_WORKBENCH_REPLAY_MISSING")
    start=start or rows[0]["date"]
    end=end or rows[-1]["date"]
    request=stocklens_8_request(initial,monthly,cost_bps,start,end)
    result=run_backtest(rows,request,FrozenExposureReplayAdapter())
    if persist:
        saved=persist_run(result)
        result=dict(result)
        result["run_id"]=saved.stem
        result["run_artifact"]=saved.as_posix()
    result["comparison_summary"]=comparison_summary(result)
    return result

if __name__=="__main__":
    print(json.dumps(run_workbench(),indent=2))
