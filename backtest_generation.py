from __future__ import annotations
import hashlib, json

def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def generation_identity(manifest: dict) -> str:
    rows=manifest.get('runs') or []
    evidence=[{'scenario_id':x.get('scenario_id'),'run_id':x.get('run_id'),'request_sha256':x.get('request_sha256'),'rows_sha256':x.get('rows_sha256'),'ledger_sha256':x.get('ledger_sha256')} for x in rows]
    return fingerprint({'kind':'M2_PUBLICATION_GENERATION','expected':manifest.get('expected'),'completed':manifest.get('completed'),'runs':evidence})
