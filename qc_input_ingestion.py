from __future__ import annotations
import csv,hashlib,json,math
from pathlib import Path
from json_artifacts import write_json_atomic
SCHEMA=Path("governance/qc_lean_feature_export_schema.json")
DEFAULT=Path("governance/qc_lean_daily_features.csv")
def validate_export(path=DEFAULT):
    schema=json.loads(SCHEMA.read_text());p=Path(path)
    if not p.exists():return {"status":"MISSING","path":str(p),"same_input_parity_ready":False,"missing":"LEAN daily feature export"}
    rows=list(csv.DictReader(p.open(encoding="utf-8",newline="")))
    cols=set(rows[0]) if rows else set();missing=[x for x in schema["required_columns"] if x not in cols]
    dates=[r.get("date") for r in rows]
    finite=True
    for r in rows:
        for k in ("close","sma50","sma200","vol20","mom12","leverage"):
            try:finite &= math.isfinite(float(r[k]))
            except:finite=False
    canonical="\n".join(",".join(str(r.get(k,"")) for k in schema["required_columns"]) for r in rows)
    checks={"columns_complete":not missing,"session_count":len(rows)==schema["expected_sessions"],"first_date":bool(rows) and dates[0]==schema["first_date"],"last_date":bool(rows) and dates[-1]==schema["last_date"],"unique_dates":len(dates)==len(set(dates)),"finite_numeric_features":bool(finite)}
    return {"status":"VALID" if all(checks.values()) else "INVALID","path":str(p),"rows":len(rows),"sha256":hashlib.sha256(canonical.encode()).hexdigest(),"checks":checks,"missing_columns":missing,"same_input_parity_ready":all(checks.values())}
def build(out="shadow_history/qc_input_ingestion.json"):
    r=validate_export();write_json_atomic(out,r);return r
if __name__=="__main__":print(json.dumps(build(),indent=2))
