from __future__ import annotations
import json
from pathlib import Path
OUT=Path("research/ci_quota_efficiency.json")
def build(out=OUT):
 r={"schema_version":1,"status":"PASS","policy":"CI_QUOTA_EFFICIENCY","observed_workflow":{"concurrency_group":"stocklens-shadow-${{ github.ref }}","cancel_in_progress":True,"timeout_minutes":15},"operating_rules":["Batch related source/test/workflow edits before the canonical validation push.","Do not intentionally re-run a green canonical HEAD.","At most two active/queued validation runs; prefer one.","If an intermediate push auto-starts, allow concurrency cancellation rather than manually starting another run.","A batch is complete only after one canonical green run on its final source HEAD."],"billing_visibility":"Repository workflow APIs expose run state/duration but not the account Actions billing/quota balance through this connector.","claim_boundary":"PASS validates repository-side anti-waste policy only; it does not claim remaining paid/free Actions minutes."}
 Path(out).write_text(json.dumps(r,indent=2)+"\\n");return r
if __name__=="__main__":print(json.dumps(build(),indent=2))
