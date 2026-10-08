from __future__ import annotations
import csv,json
from collections import Counter
from pathlib import Path
from json_artifacts import write_json_atomic
def build(out="shadow_history/context_analytics.json"):
    p=Path("shadow_history/market_context_history.csv");rows=list(csv.DictReader(p.open())) if p.exists() else []
    vals=[float(r["vix"]) for r in rows if r.get("vix")]
    counts=Counter(r.get("regime") for r in rows)
    r={"status":"ACTIVE" if rows else "WAITING_FOR_CONTEXT_HISTORY","sessions":len(rows),"vix_min":min(vals) if vals else None,"vix_max":max(vals) if vals else None,"vix_average":sum(vals)/len(vals) if vals else None,"regime_counts":dict(counts),"observational_only":True}
    write_json_atomic(out,r);return r
if __name__=="__main__":print(json.dumps(build(),indent=2))
