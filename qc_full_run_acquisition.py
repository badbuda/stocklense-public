from __future__ import annotations
import json
from pathlib import Path
def build():
 s=json.loads(Path("governance/qc_lean_full_run_export_schema.json").read_text());m=json.loads(Path("governance/qc_724_daily_state_manifest.json").read_text())
 return {"status":"RAW_SOURCE_NOT_IN_REPOSITORY","source_run":"Determined Red Orange Duck / SL724","required_sessions":m["sessions"],"boundaries":[m["first_time_utc"],m["last_time_utc"]],"known_evidence":{"leverage_sha256":m["leverage_sha256"],"full_state_sha256":m["full_state_sha256"],"leverage_counts":m["leverage_counts"],"max_drawdown_pct":m["max_drawdown_pct"],"last_nav_multiple":m["last_nav_multiple"]},"required_raw_fields":s["daily_required_columns"],"required_orders":s["golden_constraints"]["order_count"],"prohibitions":["no synthetic daily rows","no recomputation presented as original LEAN export","no model changes to produce matching evidence"],"repository_search":{"current_tree":False,"code_search_exact_source_name":False},"next_step":"Acquire/export original daily feature/equity/cash/holdings rows and canonical orders from the evidenced frozen LEAN run outside the current repository."}
if __name__=="__main__":print(json.dumps(build(),indent=2))
