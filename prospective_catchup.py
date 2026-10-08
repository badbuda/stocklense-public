from __future__ import annotations
import csv,json
from datetime import date
from pathlib import Path
from publication_identity import identity

def ledger_sessions(path='paper_portfolio/ledger.csv'):
    p=Path(path)
    if not p.exists() or p.stat().st_size==0:return []
    with p.open(newline='',encoding='utf-8') as f:return [r.get('session_date') for r in csv.DictReader(f) if r.get('session_date')]

def plan(inception_date, canonical_completed_dates, ledger_dates):
    inc=date.fromisoformat(inception_date); canon=sorted(set(canonical_completed_dates)); done=set(ledger_dates)
    eligible=[d for d in canon if date.fromisoformat(d)>inc]
    missing=[d for d in eligible if d not in done]
    return {'status':'CURRENT' if not missing else 'CATCHUP_REQUIRED','inception_date':inception_date,'eligible_completed_sessions':len(eligible),'ledger_sessions':len([d for d in ledger_dates if date.fromisoformat(d)>inc]),'missing_sessions':missing,'next_missing_session':missing[0] if missing else None,'strictly_post_inception':True,'automatic_backfill_before_inception':False}

def build(registry='research/prospective/registry.json', canonical_dates_path='docs/completed_market_sessions.json', ledger='paper_portfolio/ledger.csv',out='docs/prospective_catchup.json'):
    r=json.loads(Path(registry).read_text()); p=Path(canonical_dates_path)
    manifest=json.loads(p.read_text()) if p.exists() else {}; dates=(manifest.get('dates') or []) if manifest.get('status')=='PASS' else []
    rows=[dict(experiment_id=c['experiment_id'],**plan(c['inception_date'],dates,ledger_sessions(ledger))) for c in r.get('candidates',[])]
    x={'schema_version':2,'publication_identity':identity(),'status':('BLOCKED' if manifest.get('status')!='PASS' else ('CURRENT' if rows and all(v['status']=='CURRENT' for v in rows) else 'ATTENTION')),'canonical_session_manifest_status':manifest.get('status','MISSING'),'experiments':rows,'semantics':'Catch-up plan only. Sessions remain subject to original prospective timestamp/execution integrity gates.'}
    Path(out).write_text(json.dumps(x,indent=2)+'\n');return x
if __name__=='__main__':print(json.dumps(build(),indent=2))
