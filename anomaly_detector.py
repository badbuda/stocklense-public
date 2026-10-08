from __future__ import annotations
import csv,json,math,statistics
from pathlib import Path
ABS_LIMITS={"close":0.15,"sma50":0.05,"sma200":0.02,"vol20":0.75,"mom12":0.75}
def build_anomaly_report(path="historical_replay/daily_states.csv",out="shadow_history/anomalies.json"):
    p=Path(path);rows=list(csv.DictReader(p.open())) if p.exists() else [];alerts=[];diagnostics={}
    if len(rows)>=2:
        a,b=rows[-2],rows[-1]
        for k,lim in ABS_LIMITS.items():
            old,new=float(a[k]),float(b[k]);delta=abs(new-old)/(abs(old) or 1)
            history=[]
            for i in range(max(1,len(rows)-61),len(rows)-1):
                x,y=float(rows[i-1][k]),float(rows[i][k]);history.append(abs(y-x)/(abs(x) or 1))
            median=statistics.median(history) if history else 0
            mad=statistics.median([abs(x-median) for x in history]) if history else 0
            adaptive=max(lim,median+12*mad)
            diagnostics[k]={"relative_change":delta,"absolute_limit":lim,"rolling_median_change":median,"rolling_mad":mad,"effective_limit":adaptive}
            if not math.isfinite(new):alerts.append({"field":k,"kind":"NONFINITE"})
            elif delta>adaptive:alerts.append({"field":k,"kind":"SESSION_JUMP","relative_change":delta,"effective_limit":adaptive})
    r={"status":"BLOCK" if alerts else "CLEAR","alerts":alerts,"diagnostics":diagnostics,"sessions_available":len(rows),"policy":"absolute safety limits plus robust rolling baseline; never changes frozen model"}
    q=Path(out);q.parent.mkdir(parents=True,exist_ok=True);q.write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build_anomaly_report(),indent=2))
