from __future__ import annotations
import csv,json
from pathlib import Path
def build_event_journal(signal_path="output/latest_signal.json",out_path="shadow_history/event_journal.json"):
    s=json.loads(Path(signal_path).read_text());x=s["latest"];f=x["features"]
    reasons=[f"QQQ {float(f['close'])/float(f['sma200'])-1:+.2%} vs SMA200",f"VOL20 {float(f['vol20']):.2%}",f"MOM12 {float(f['mom12']):+.2%}",f"Defense {'ON' if x['defense_active'] else 'OFF'}"]
    event={"date":x["asof_date"],"action":s["action"],"level":x["level"],"target_leverage":x["target_leverage"],"reasons":reasons}
    p=Path(out_path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps({"latest":event},indent=2)+"\n");return event
if __name__=="__main__": print(json.dumps(build_event_journal(),indent=2))
