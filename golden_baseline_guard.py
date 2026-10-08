from __future__ import annotations
import json
from pathlib import Path
POLICY=Path("research/GOLDEN_BASELINE_POLICY.json")
def validate_challenger(spec):
 p=json.loads(POLICY.read_text())
 errors=[]
 if spec.get("baseline") not in ("StockLens 8.0","StockLens 8.0 FROZEN"):errors.append("MUST_REFERENCE_STOCKLENS_8")
 if spec.get("version") in (None,"8.0","StockLens 8.0"):errors.append("CHALLENGER_REQUIRES_SEPARATE_VERSION")
 if spec.get("research_only") is not True:errors.append("CHALLENGER_MUST_BE_RESEARCH_ONLY")
 return {"status":"PASS" if not errors else "BLOCK","errors":errors,"baseline_id":p["baseline_id"],"parallel":True}
