from __future__ import annotations
import csv,json
from collections import Counter
from pathlib import Path
def build_regime_analytics(path="historical_replay/daily_states.csv",out="shadow_history/regime_analytics.json"):
    p=Path(path);rows=list(csv.DictReader(p.open())) if p.exists() else []
    counts=Counter(r["level"] for r in rows);defense=sum(str(r.get("defense_active","")).lower()=="true" for r in rows)
    streak=0;current=None
    if rows:
        current=rows[-1]["level"]
        for r in reversed(rows):
            if r["level"]!=current:break
            streak+=1
    transitions=sum(rows[i]["level"]!=rows[i-1]["level"] or rows[i].get("defense_active")!=rows[i-1].get("defense_active") for i in range(1,len(rows)))
    result={"status":"ACTIVE" if rows else "NO_DATA","sessions":len(rows),"level_counts":dict(counts),"defense_sessions":defense,"state_transitions":transitions,"current_level":int(current) if current else None,"current_level_streak_sessions":streak}
    q=Path(out);q.parent.mkdir(parents=True,exist_ok=True);q.write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build_regime_analytics(),indent=2))
