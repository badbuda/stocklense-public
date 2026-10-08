from __future__ import annotations
import json
from pathlib import Path
from prospective_gate import GATE
from publication_identity import _git_sha

def build(registry='research/prospective/registry.json',out='docs/prospective_maturity.json'):
    r=json.loads(Path(registry).read_text());rows=[]
    git_sha=_git_sha();producer_sha=r.get('producer_git_sha');producer_current=bool(git_sha and producer_sha==git_sha and r.get('ingestion_gate')==GATE)
    audits={x['experiment_id']:x for x in r.get('last_ingestion_audit',[])}
    for candidate in r.get('candidates',[]):
        a=audits.get(candidate['experiment_id'],{})
        accepted_raw=a.get('accepted_completed_xnys_rows');persisted_raw=a.get('persisted_prospective_rows')
        source_available=a.get('source_status')=='AVAILABLE'
        definition_current=a.get('definition_matches_registration') is True
        evidence_fingerprint_current=a.get('fingerprint_matches_registration') is True
        schema_complete=producer_current and source_available and definition_current and accepted_raw is not None and persisted_raw is not None and a.get('gate')==GATE
        accepted=int(accepted_raw or 0);persisted=int(persisted_raw or 0)
        consistent=schema_complete and accepted==persisted
        audit_fields_present=accepted_raw is not None and persisted_raw is not None and a.get('gate')==GATE
        if not producer_current or not audit_fields_present:evidence_state='BLOCKED_INCOMPLETE_INGESTION_AUDIT'
        elif not source_available:evidence_state='BLOCKED_MISSING_RETURNS_SOURCE'
        elif not definition_current:evidence_state='BLOCKED_EXPERIMENT_DEFINITION_DRIFT'
        elif not schema_complete:evidence_state='BLOCKED_INCOMPLETE_INGESTION_AUDIT'
        elif not consistent:evidence_state='BLOCKED_PERSISTENCE_MISMATCH'
        elif persisted==0:evidence_state='WAITING_FOR_POST_INCEPTION_COMPLETED_XNYS'
        else:evidence_state='ACCUMULATING_FORWARD_EVIDENCE'
        rows.append({'experiment_id':candidate['experiment_id'],'status':candidate['status'],'inception_date':candidate['inception_date'],
          'accepted_completed_xnys_sessions':accepted_raw,'persisted_prospective_sessions':persisted_raw,
          'definition_current':definition_current,'registered_definition_fingerprint':a.get('registered_definition_fingerprint'),'current_definition_fingerprint':a.get('current_definition_fingerprint'),'evidence_fingerprint_current':evidence_fingerprint_current,'registered_fingerprint':a.get('registered_fingerprint'),'queue_fingerprint':a.get('queue_fingerprint'),'source_status':a.get('source_status','MISSING_AUDIT'),'returns_csv':a.get('returns_csv'),'audit_schema_complete':schema_complete,'persistence_consistent':consistent,'evidence_state':evidence_state,
          'zero_backfill_enforced':a.get('gate')==GATE,'automatic_promotion':False,'threshold_status':'NO_MATURITY_THRESHOLD_INVENTED'})
    x={'schema_version':5,'producer_git_sha':producer_sha,'current_git_sha':git_sha,'producer_current':producer_current,'registry_updated_at_utc':r.get('updated_at_utc'),'status':'BLOCKED' if any(not row['persistence_consistent'] for row in rows) else 'PASS','experiments':rows,
       'semantics':'Forward evidence only. Definition lineage is immutable while evidence fingerprints may refresh. Missing ingestion audit fields fail closed; no pre-inception backfill and no maturity threshold is invented by this report.'}
    Path(out).parent.mkdir(parents=True,exist_ok=True);Path(out).write_text(json.dumps(x,indent=2)+'\n');return x
if __name__=='__main__': print(json.dumps(build(),indent=2))
