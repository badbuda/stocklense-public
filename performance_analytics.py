from __future__ import annotations
import csv, json, math
from pathlib import Path

def _rows(path):
    p=Path(path)
    if not p.exists() or p.stat().st_size==0:return []
    with p.open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))

def _f(x, default=0.0):
    try:return float(x)
    except (TypeError,ValueError):return default

def build_performance(out="shadow_history/performance.json"):
    rows=_rows("paper_portfolio/ledger.csv")
    result={"status":"WAITING_FOR_PROSPECTIVE_DATA","sessions":len(rows)}
    if rows:
        equities=[_f(r.get("equity")) for r in rows]
        rets=[equities[i]/equities[i-1]-1 for i in range(1,len(equities)) if equities[i-1]>0]
        peak=max(equities); current=equities[-1]
        max_dd=min((_f(r.get("drawdown"),0) for r in rows),default=0)
        vol=(math.sqrt(252)*math.sqrt(sum((x-(sum(rets)/len(rets)))**2 for x in rets)/(len(rets)-1))) if len(rets)>1 else None
        result={"status":"ACTIVE","sessions":len(rows),"start_equity":equities[0],
                "current_equity":current,"cumulative_return":current/equities[0]-1 if equities[0] else None,
                "peak_equity":peak,"max_drawdown":max_dd,"annualized_volatility":vol,
                "cumulative_fees":_f(rows[-1].get("cumulative_fees")),
                "cumulative_slippage_cost":_f(rows[-1].get("cumulative_slippage_cost")),
                "trade_count":sum(int(_f(r.get("trade_count_session"))) for r in rows),
                "total_return_pct":(current/equities[0]-1)*100 if equities[0] else None,
                "max_drawdown_pct":max_dd*100,
                "annualized_volatility_pct":vol*100 if vol is not None else None,
                "fee_drag_pct":(_f(rows[-1].get("cumulative_fees"))/equities[0]*100) if equities[0] else None,
                "slippage_drag_pct":(_f(rows[-1].get("cumulative_slippage_cost"))/equities[0]*100) if equities[0] else None}
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(result,indent=2)+"\n")
    return result
if __name__=="__main__":print(json.dumps(build_performance(),indent=2))
