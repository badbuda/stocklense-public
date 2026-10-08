from __future__ import annotations
import csv,json
from pathlib import Path
def build_change_digest(path="shadow_history/decision_journal.csv",out="shadow_history/change_digest.json"):
    p=Path(path);rows=list(csv.DictReader(p.open())) if p.exists() else []
    if not rows:r={"status":"NO_DATA","changes":[]}
    else:
        x=rows[-1];changes=[]
        pairs=[("level","previous_level"),("defense_active","previous_defense"),("target_leverage","previous_leverage")]
        for now,prev in pairs:
            if x.get(prev)!="" and x.get(now)!=x.get(prev):changes.append({"field":now,"from":x.get(prev),"to":x.get(now)})
        r={"status":"CHANGED" if changes else "UNCHANGED","date":x["asof_date"],"action":x["action"],"changes":changes}
    q=Path(out);q.parent.mkdir(parents=True,exist_ok=True);q.write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build_change_digest(),indent=2))
