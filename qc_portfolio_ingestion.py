from __future__ import annotations
import csv,hashlib,json,math
from pathlib import Path
DEFAULT=Path("governance/qc_lean_daily_portfolio.csv")
OUT=Path("shadow_history/qc_portfolio_ingestion.json")
REQUIRED=("date","total_portfolio_value","cash","tqqq_quantity","qld_quantity","qqq_quantity")
EXPECTED_FIRST="2009-09-01";EXPECTED_LAST="2024-08-29"
def validate(path=DEFAULT):
 p=Path(path)
 if not p.exists():return {"status":"MISSING","portfolio_parity_ready":False,"path":str(p)}
 rows=list(csv.DictReader(p.open(encoding="utf-8",newline="")));cols=set(rows[0]) if rows else set();dates=[r.get("date") for r in rows]
 finite=True
 for r in rows:
  for k in REQUIRED[1:]:
   try:finite &= math.isfinite(float(r[k]))
   except:finite=False
 checks={"columns_complete":all(k in cols for k in REQUIRED),"nonempty":bool(rows),"first_date":bool(rows) and dates[0]==EXPECTED_FIRST,"last_date":bool(rows) and dates[-1]==EXPECTED_LAST,"unique_dates":len(dates)==len(set(dates)),"finite_numeric":bool(finite),"positive_nav":bool(rows) and all(float(r["total_portfolio_value"])>0 for r in rows)}
 ok=all(checks.values());canonical="\n".join(",".join(str(r.get(k,"")) for k in REQUIRED) for r in rows)
 return {"status":"VALID" if ok else "INVALID","portfolio_parity_ready":ok,"rows":len(rows),"checks":checks,"sha256":hashlib.sha256(canonical.encode()).hexdigest()}
def build(out=OUT):
 r=validate();Path(out).write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build(),indent=2))
