from __future__ import annotations
import csv,json
from pathlib import Path
from json_artifacts import write_json_atomic
def _f(x):
    try:return float(x or 0)
    except:return 0.0
def build_execution_quality(ledger="paper_portfolio/ledger.csv",trades="paper_portfolio/trades.csv",out="shadow_history/execution_quality.json"):
    lp=Path(ledger);rows=list(csv.DictReader(lp.open())) if lp.exists() else []
    tp=Path(trades);trs=list(csv.DictReader(tp.open())) if tp.exists() else []
    turnover=sum(_f(r.get("turnover_notional")) for r in rows)
    fees=_f(rows[-1].get("cumulative_fees")) if rows else 0
    slip=_f(rows[-1].get("cumulative_slippage_cost")) if rows else 0
    start=_f(rows[0].get("equity")) if rows else 0
    result={"status":"ACTIVE" if rows else "WAITING_FOR_PROSPECTIVE_DATA","sessions":len(rows),"trades":len(trs),"total_turnover_notional":turnover,"cumulative_fees":fees,"cumulative_modeled_slippage":slip,"total_modeled_execution_cost":fees+slip,"execution_cost_bps_of_turnover":((fees+slip)/turnover*10000 if turnover else None),"execution_cost_pct_of_start_equity":((fees+slip)/start*100 if start else None),"assumption_note":"Paper model costs, not observed broker fills."}
    write_json_atomic(out,result);return result
if __name__=="__main__":print(json.dumps(build_execution_quality(),indent=2))
