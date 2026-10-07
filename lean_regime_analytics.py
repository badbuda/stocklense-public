from __future__ import annotations
import json
from datetime import date
from pathlib import Path
def build(src="governance/qc_724_leverage_transitions.json",out="docs/lean_regime_analytics.json"):
 d=json.loads(Path(src).read_text());t=d["transitions"];rows=[];matrix={};up=down=0
 for i,(ds,lev) in enumerate(t):
  start=date.fromisoformat(ds);end=date.fromisoformat(t[i+1][0]) if i+1<len(t) else date(2024,8,29)
  days=max(0,(end-start).days);nxt=t[i+1][1] if i+1<len(t) else None
  rows.append({"start":ds,"end_exclusive":end.isoformat(),"leverage":lev,"calendar_days":days,"next_leverage":nxt})
  if nxt is not None:
   k=f"{lev:g}x→{nxt:g}x";matrix[k]=matrix.get(k,0)+1
   if nxt>lev:up+=1
   elif nxt<lev:down+=1
 by={}
 for r in rows:
  k=f'{r["leverage"]:g}x';x=by.setdefault(k,{"regimes":0,"calendar_days":0,"longest_calendar_days":0})
  x["regimes"]+=1;x["calendar_days"]+=r["calendar_days"];x["longest_calendar_days"]=max(x["longest_calendar_days"],r["calendar_days"])
 payload={"kind":"VERIFIED_TRANSITION_DERIVED_REGIME_ANALYTICS","source_transition_sha256":d["transition_sha256"],"transition_count":d["transition_count"],"note":"Durations are calendar-day intervals between verified transition dates; not reconstructed trading-session rows.","upshifts":up,"downshifts":down,"by_leverage":by,"transition_matrix":matrix,"regimes":rows}
 Path(out).write_text(json.dumps(payload,indent=2)+"\n");return payload
if __name__=="__main__":print(json.dumps(build(),indent=2))
