from __future__ import annotations
import csv,json
from pathlib import Path
from prospective_gate import gated_ledger_rows
def build_benchmark_summary(ledger_path="paper_portfolio/ledger.csv",out_path="shadow_history/benchmark.json"):
    rows,rejected,inception=gated_ledger_rows(ledger_path)
    result={"status":"WAITING_FOR_PROSPECTIVE_DATA","sessions":len(rows),"benchmark":"QQQ","stocklens_return":None,"qqq_return":None,"excess_return":None,"experiment_id":"SL9-007-UPSHIFT-CONFIRMATION","inception_date":inception.isoformat(),"rejected_rows":len(rejected),"gate":"STRICTLY_AFTER_INCEPTION"}
    if len(rows)>=2 and rows[0].get("qqq_close") and rows[-1].get("qqq_close"):
        a,b=float(rows[0]["qqq_close"]),float(rows[-1]["qqq_close"]);q=b/a-1
        sr=float(rows[-1].get("cumulative_return",0));result.update(status="ACTIVE",stocklens_return=sr,qqq_return=q,excess_return=sr-q)
    o=Path(out_path);o.parent.mkdir(parents=True,exist_ok=True);o.write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__": print(json.dumps(build_benchmark_summary(),indent=2))
