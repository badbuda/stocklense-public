from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from publication_identity import identity

def audit(registry='research/prospective/registry.json', workbench='docs/workbench.json', data='docs/data.json'):
    r=json.loads(Path(registry).read_text());w=json.loads(Path(workbench).read_text());d=json.loads(Path(data).read_text())
    provenance_asof=d.get('data_provenance',{}).get('last_completed_date')
    workbench_asof=w.get('publication',{}).get('signal_asof')
    provenance_status=d.get('data_provenance',{}).get('status')
    source_consistent=bool(provenance_asof and provenance_status=='COMPLETE' and (not workbench_asof or workbench_asof==provenance_asof))
    rows=[];audits={x['experiment_id']:x for x in r.get('last_ingestion_audit',[])}
    for c in r.get('candidates',[]):
        inception=c.get('inception_date');audit=audits.get(c['experiment_id'],{});accepted=int(audit.get('accepted_completed_xnys_rows',0) or 0);persisted=int(audit.get('persisted_prospective_rows',0) or 0);persistence_consistent=persisted==accepted
        post=bool(source_consistent and inception and date.fromisoformat(provenance_asof)>date.fromisoformat(inception))
        if not source_consistent:status='BLOCKED_CANONICAL_SOURCE_INCONSISTENT'
        elif not post:status='ATTENTION_CANONICAL_MARKET_DATA_NOT_POST_INCEPTION'
        elif accepted==0:status='ATTENTION_INGESTION_LAG'
        elif not persistence_consistent:status='BLOCKED_PROSPECTIVE_PERSISTENCE_MISMATCH'
        else:status='CURRENT'
        rows.append({'experiment_id':c['experiment_id'],'inception_date':inception,'canonical_market_data_asof':provenance_asof,'workbench_signal_asof':workbench_asof,'canonical_source_consistent':source_consistent,'accepted_completed_xnys_sessions':accepted,'persisted_prospective_sessions':persisted,'persistence_consistent':persistence_consistent,'canonical_source_has_post_inception_session':post,'status':status})
    status='PASS' if rows and all(x['status']=='CURRENT' for x in rows) else ('BLOCKED' if (not source_consistent or any(str(x['status']).startswith('BLOCKED_') for x in rows)) else 'ATTENTION')
    return {'schema_version':2,'publication_identity':identity(workbench),'status':status,'canonical_source':{'artifact':data,'field':'data_provenance.last_completed_date','provenance_status':provenance_status,'last_completed_date':provenance_asof,'workbench_signal_asof':workbench_asof,'consistent':source_consistent},'experiments':rows,'semantics':'Forward freshness is anchored to explicit canonical market-data provenance. Workbench signal_asof is a consistency check, not the freshness source. No web prices or retrospective prospective backfill.'}
if __name__=='__main__':
    x=audit();Path('docs/prospective_freshness.json').write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x,indent=2))
