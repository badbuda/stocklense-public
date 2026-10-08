from __future__ import annotations
import csv,json
from datetime import date,datetime,timezone
from pathlib import Path
from market_calendar import completed_sessions

EXPERIMENT_ID="SL9-007-UPSHIFT-CONFIRMATION"
GATE="STRICTLY_AFTER_INCEPTION_AND_COMPLETED_XNYS"

def inception_date(registry="research/prospective/registry.json"):
    data=json.loads(Path(registry).read_text())
    for item in data.get("candidates",[]):
        if item.get("experiment_id")==EXPERIMENT_ID:
            if item.get("status")!="ACTIVE_RESEARCH_ONLY" or item.get("automatic_promotion") is not False:
                raise RuntimeError("PROSPECTIVE_REGISTRY_GOVERNANCE_INVALID")
            return date.fromisoformat(item["inception_date"])
    raise RuntimeError("PROSPECTIVE_EXPERIMENT_NOT_REGISTERED")

def _completed_xnys_session(session: date, now_utc: datetime | None=None) -> tuple[bool,str | None]:
    completed={s.date() for s in completed_sessions(now_utc,start_date=session.isoformat())}
    if session in completed:
        return True,None
    # Distinguish a closed-calendar exclusion from a not-yet-completed trading session.
    future_probe={s.date() for s in completed_sessions(datetime.combine(session,datetime.max.time(),tzinfo=timezone.utc),start_date=session.isoformat())}
    return (False,"XNYS_SESSION_NOT_COMPLETED" if session in future_probe else "NOT_XNYS_SESSION")

def gated_ledger_rows(path="paper_portfolio/ledger.csv",registry="research/prospective/registry.json",now_utc: datetime | None=None):
    p=Path(path);rows=list(csv.DictReader(p.open())) if p.exists() else []
    inception=inception_date(registry)
    accepted=[];rejected=[]
    for row in rows:
        raw=row.get("session_date")
        try:session=date.fromisoformat(raw)
        except Exception:
            rejected.append({"session_date":raw,"reason":"INVALID_SESSION_DATE"});continue
        if session<=inception:
            rejected.append({"session_date":raw,"reason":"PRE_OR_AT_INCEPTION"});continue
        completed,reason=_completed_xnys_session(session,now_utc=now_utc)
        if not completed:
            rejected.append({"session_date":raw,"reason":reason});continue
        accepted.append(row)
    return accepted,rejected,inception
