from __future__ import annotations
import json
from pathlib import Path
REQUIRED_ROW={"date","close","sma50","sma200","vol20","mom12","frozen_level","frozen_defense","frozen_leverage","vix"}
def validate(path="docs/research.json"):
    p=Path(path)
    if not p.exists():return {"status":"FAIL","errors":["MISSING_RESEARCH_DATASET"]}
    x=json.loads(p.read_text());errors=[]
    if x.get("mode")!="RESEARCH_SANDBOX":errors.append("MODE_NOT_SANDBOX")
    if x.get("baseline")!="StockLens 8.0 FROZEN":errors.append("BASELINE_NOT_FROZEN_8")
    rows=x.get("rows",[])
    if rows and not REQUIRED_ROW.issubset(rows[0]):errors.append("ROW_SCHEMA_INCOMPLETE")
    dates=[r.get("date") for r in rows]
    if dates!=sorted(dates) or len(dates)!=len(set(dates)):errors.append("DATES_NOT_STRICT_UNIQUE_SORTED")
    if x.get("warning") is None:errors.append("MISSING_RESEARCH_WARNING")
    return {"status":"PASS" if not errors else "FAIL","errors":errors,"rows":len(rows),"schema_version":x.get("schema_version")}
if __name__=="__main__":
 r=validate();print(json.dumps(r,indent=2));raise SystemExit(0 if r["status"]=="PASS" else 2)
