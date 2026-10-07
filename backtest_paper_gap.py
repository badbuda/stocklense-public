from __future__ import annotations
import csv,json
from pathlib import Path
from publication_identity import identity

def build(ledger="paper_portfolio/ledger.csv",replay="docs/replay_session_returns.json",out="docs/backtest_paper_gap.json"):
    p=Path(ledger);rows=list(csv.DictReader(p.open(encoding="utf-8",newline=""))) if p.exists() and p.stat().st_size else []
    rr=json.loads(Path(replay).read_text()) if Path(replay).exists() else {};by={x["session_date"]:x for x in rr.get("observations",[])}
    obs=[];prev=None
    for r in rows:
        eq=float(r["equity"]);actual=None if prev is None else eq/prev-1;ex=by.get(r["session_date"]);expected=ex.get("net_replay_return_proxy") if ex else None
        gap=(actual-expected) if actual is not None and expected is not None else None
        obs.append({"session_date":r["session_date"],"actual_paper_return":actual,"expected_replay_return":expected,"gap":gap,"target_leverage":float(r["target_leverage"]),"fees_cumulative":float(r["cumulative_fees"]),"slippage_cumulative":float(r["cumulative_slippage_cost"]),"status":"PAIRED" if gap is not None else "WAITING_FOR_CANONICAL_SAME_SESSION_REPLAY_OR_PRIOR_PAPER_NAV"})
        prev=eq
    paired=[x for x in obs if x["gap"] is not None]
    x={"schema_version":2,"publication_identity":identity(),"status":"READY" if paired else "WAITING_FOR_PAIRED_EVIDENCE","paper_sessions":len(obs),"paired_sessions":len(paired),"mean_gap":sum(x["gap"] for x in paired)/len(paired) if paired else None,"max_abs_gap":max(abs(x["gap"]) for x in paired) if paired else None,"observations":obs,"component_attribution":{"status":"NOT_IDENTIFIED","reason":"Aggregate gap mixes ETF path/basis, intraday timing, cash/whole-share effects, fees/slippage and other implementation differences. Current evidence cannot causally allocate the residual."},"semantics":"Replay is a close-to-close exposure approximation. Paper uses intraday fills, TQQQ/QQQ holdings, whole shares, cash, fees, slippage and corporate actions. Gap measures model-to-paper divergence, not broker execution alpha.","execution_parity_claimed":False}
    Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))
