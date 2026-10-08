from __future__ import annotations
import csv,json
from pathlib import Path

FIELDS=["asof_date","action","level","defense_active","target_leverage","qqq_weight","tqqq_weight","close","sma50","sma200","vol20","mom12","previous_date","previous_level","previous_defense","previous_leverage"]
def build_journal(signal_path="shadow_history/latest.json",out="shadow_history/decision_journal.csv"):
    s=json.loads(Path(signal_path).read_text())
    x=s["latest"]; p=s.get("previous") or {}; f=x["features"]
    row={"asof_date":x["asof_date"],"action":s["action"],"level":x["level"],"defense_active":x["defense_active"],
         "target_leverage":x["target_leverage"],"qqq_weight":x["qqq_weight"],"tqqq_weight":x["tqqq_weight"],
         "close":f["close"],"sma50":f["sma50"],"sma200":f["sma200"],"vol20":f["vol20"],"mom12":f["mom12"],
         "previous_date":p.get("asof_date"),"previous_level":p.get("level"),"previous_defense":p.get("defense_active"),
         "previous_leverage":p.get("target_leverage")}
    path=Path(out);path.parent.mkdir(parents=True,exist_ok=True)
    rows=[]
    if path.exists():
        with path.open(encoding="utf-8",newline="") as z:rows=list(csv.DictReader(z))
    existing=next((r for r in rows if r["asof_date"]==row["asof_date"]),None)
    if existing:
        # Journal is prospective/immutable: a rerun may not rewrite a day's recorded decision.
        comparable={k:str(row[k]) for k in FIELDS}
        if any(str(existing.get(k,""))!=comparable[k] for k in FIELDS):
            raise RuntimeError("DECISION_JOURNAL_CONFLICT")
        return row
    with path.open("a",encoding="utf-8",newline="") as z:
        w=csv.DictWriter(z,fieldnames=FIELDS)
        if not rows:w.writeheader()
        w.writerow(row)
    return row
if __name__=="__main__":print(json.dumps(build_journal(),indent=2,default=str))
