from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from json_artifacts import write_json_atomic
ROOTS=("output","shadow_history","paper_portfolio","historical_replay","governance")
def build(out="shadow_history/artifact_catalog.json"):
    items=[]
    for root in ROOTS:
        p=Path(root)
        if not p.exists():continue
        for f in sorted(x for x in p.rglob("*") if x.is_file() and x.name!="artifact_catalog.json"):
            b=f.read_bytes();items.append({"path":str(f),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest(),"mtime_ns":f.stat().st_mtime_ns})
    r={"schema_version":1,"generated_at_utc":datetime.now(timezone.utc).isoformat(),"artifact_count":len(items),"artifacts":items}
    write_json_atomic(out,r);return r
if __name__=="__main__":print(json.dumps(build(),indent=2))
