from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
from json_artifacts import write_json_atomic
BLOCKED={"BLOCKED_LATE_SIGNAL","MISSED_WINDOW"}
def build(cockpit_path="shadow_history/execution_cockpit.json",out="shadow_history/execution_policy.json",now_utc=None):
 p=Path(cockpit_path)
 if not p.exists():
  result={"schema_version":1,"status":"BLOCKED","next_action":"WAIT_FOR_VALID_COCKPIT","automatic_catchup":False,"live_submission_authorized":False}
  write_json_atomic(out,result);return result
 c=json.loads(p.read_text());windows=c.get("execution_windows") or {};statuses={k:v.get("status") for k,v in windows.items()};blocked=sorted(k for k,v in statuses.items() if v in BLOCKED)
 if blocked:status="HUMAN_REVIEW_REQUIRED";next_action="DO_NOT_CHASE_MISSED_WINDOW"
 elif c.get("orders"):status="PAPER_PLAN_READY";next_action="OBSERVE_SCHEDULED_WINDOWS"
 else:status="NO_ACTION_REQUIRED";next_action="WAIT_FOR_NEXT_SIGNAL"
 result={"schema_version":1,"generated_at_utc":(now_utc or datetime.now(timezone.utc)).isoformat(),"status":status,"next_action":next_action,"window_statuses":statuses,"blocked_sides":blocked,"automatic_catchup":False,"catchup_policy":"NEVER_AUTO_EXECUTE_AFTER_MISSED_OR_LATE_WINDOW","live_submission_authorized":False,"broker_reconciliation_required_for_live":True,"note":"Late or missed execution windows are never chased automatically; await review or the next valid frozen signal/session."}
 write_json_atomic(out,result);return result
if __name__=="__main__":print(json.dumps(build(),indent=2))
