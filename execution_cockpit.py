from __future__ import annotations
import math
import csv,json
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from json_artifacts import write_json_atomic
from order_planner import desired_orders
from order_state import make_order,save
from broker_reconciliation import Position,reconcile
from execution_scheduler import next_xnys_session,readiness_by_side
from paper_rebalance_math import target_shares, weight_gap, within_band

NY=ZoneInfo("America/New_York")

def _rows(path):
 p=Path(path)
 return list(csv.DictReader(p.open())) if p.exists() else []

def build(plan_path="shadow_history/execution_plan.json",signal_path="output/latest_signal.json",ledger_path="paper_portfolio/ledger.csv",out="shadow_history/execution_cockpit.json"):
 plan=json.loads(Path(plan_path).read_text())
 sp=Path(signal_path)
 if not sp.exists():
  payload={"schema_version":1,"status":"WAITING_FOR_SIGNAL","mode":"PAPER","live_submission_authorized":False,"current_positions":{},"target_positions":{},"reference_prices":{},"orders":[],"order_state":{"status":"WAITING_FOR_SIGNAL","live_submission_authorized":False},"reconciliation":{"status":"NOT_RUN","live_gate_eligible":False},"execution_window":{"status":"BLOCKED_NO_SIGNAL"},"note":"Fail-closed: no prospective signal artifact is available; no order can be planned or submitted."}
  write_json_atomic(out,payload);return payload
 sig=json.loads(sp.read_text())
 rows=_rows(ledger_path);last=rows[-1] if rows else {}
 current={"QQQ":int(float(last.get("qqq_shares",0) or 0)),"TQQQ":int(float(last.get("tqqq_shares",0) or 0))}
 equity=float(last.get("equity",100000) or 100000)
 f=sig["latest"]["features"]; qqq=float(f.get("close") or 0)
 tqqq=float(last.get("tqqq_close",0) or 0)
 prices={"QQQ":qqq,"TQQQ":tqqq}
 # The cockpit has only the last published reference price, NOT next-session
 # 09:31 / 09:32 observed opens. Common sizing/band math does not prove
 # a same-execution-session decision or broker fill parity.
 if not all(math.isfinite(px) and px>0 for px in prices.values()):
  raise ValueError("COCKPIT_MISSING_VALID_REFERENCE_PRICES")
 weights={s:float(plan["target"][s.lower()+"_weight"]) for s in ("QQQ","TQQQ")}
 target=target_shares(weights,equity,prices)
 gap=weight_gap(current,weights,prices,equity)
 hold_no_change=(sig.get("action")=="NO_CHANGE" and within_band(current,weights,prices,equity))
 if hold_no_change:
  target=dict(current)
 session=next_xnys_session(plan["signal_date"])
 intents=desired_orders(current,target,session,float(plan["target"]["leverage"]))
 records=[make_order(x.session,x.symbol,x.side,x.quantity,x.idempotency_key) for x in intents]
 state=save(records)
 target_gap=reconcile([Position(k,v) for k,v in target.items()],[Position(k,v) for k,v in current.items()])
 target_gap={**target_gap,"semantics":"PRE_EXECUTION_TARGET_GAP_NOT_BROKER_RECONCILIATION","live_gate_eligible":False}
 broker_rec={"status":"NOT_RUN","semantics":"REQUIRES_EXTERNAL_BROKER_POSITION_SNAPSHOT","differences":[],"live_gate_eligible":False}
 generated=sig.get("generated_at_utc") or sig.get("latest",{}).get("generated_at_utc") or plan["signal_date"]+"T22:00:00Z"
 sides=[x.side for x in intents]
 windows=readiness_by_side(datetime.now(timezone.utc),session,sides,generated) if sides else {}
 payload={"schema_version":1,"status":"READY","mode":"PAPER","live_submission_authorized":False,
 "current_positions":current,"target_positions":target,"reference_prices":prices,
 "orders":[{**o.__dict__,"idempotency_key":o.idempotency_key,"status":"PLANNED","dry_run":True} for o in intents],
 "order_state":state,"target_gap":target_gap,"reconciliation":broker_rec,"execution_windows":windows,"execution_window":(next(iter(windows.values())) if len(windows)==1 else {"status":"MULTI_WINDOW" if windows else "NO_ORDERS","windows":windows}),
 "no_change_tolerance_applied":hold_no_change,"pretrade_target_weight_gap":gap,
 "price_semantics":"INDICATIVE_LAST_PUBLISHED_REFERENCE_NOT_NEXT_SESSION_09_31_09_32",
 "note":"Dry-run plan only. No live broker order is submitted."}
 write_json_atomic(out,payload);return payload
if __name__=="__main__":print(json.dumps(build(),indent=2))
