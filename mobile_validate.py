from __future__ import annotations
import json
from pathlib import Path

REQUIRED=("docs/index.html","docs/data.json","docs/manifest.webmanifest","docs/sw.js")

def validate():
    missing=[p for p in REQUIRED if not Path(p).is_file() or Path(p).stat().st_size==0]
    if missing: raise SystemExit("MOBILE_BUNDLE_MISSING:"+",".join(missing))
    d=json.loads(Path("docs/data.json").read_text(encoding="utf-8"))
    if d.get("model")!="StockLens 8.0": raise SystemExit("MOBILE_DATA_WRONG_MODEL")
    s=d.get("signal") or {}
    for k in ("asof_date","level","target_leverage","qqq_weight","tqqq_weight","features"):
        if k not in s: raise SystemExit("MOBILE_DATA_MISSING_SIGNAL_FIELD:"+k)
    if d.get("integrity",{}).get("qc_reference")!="LOCKED": raise SystemExit("MOBILE_QC_REFERENCE_NOT_LOCKED")
    m=json.loads(Path("docs/manifest.webmanifest").read_text(encoding="utf-8"))
    if m.get("display")!="standalone": raise SystemExit("MOBILE_MANIFEST_NOT_STANDALONE")
    print("MOBILE_BUNDLE_VALIDATION=PASS")
if __name__=="__main__": validate()
