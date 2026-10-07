from __future__ import annotations
from datetime import date

def _years(start,end):
    a=date.fromisoformat(start);b=date.fromisoformat(end)
    return max(0.0,(b-a).days/365.2425)

def fixed_subperiods(start,end):
    a=date.fromisoformat(start);b=date.fromisoformat(end)
    total=_years(start,end)
    windows=[]
    # Deterministic non-overlapping thirds: descriptive stability evidence, never optimized.
    days=(b-a).days
    cuts=[a, date.fromordinal(a.toordinal()+days//3), date.fromordinal(a.toordinal()+2*days//3), b]
    for i in range(3):
        windows.append({'window_id':f'THIRD_{i+1}','start':cuts[i].isoformat(),'end':cuts[i+1].isoformat(),'selection_policy':'FIXED_TIME_PARTITION'})
    # Deterministic rolling windows when enough history exists.
    if total>=6:
        width_days=int(5*365.2425); step_days=int(2*365.2425); cur=a
        n=1
        while cur.toordinal()+width_days<=b.toordinal():
            e=date.fromordinal(cur.toordinal()+width_days)
            windows.append({'window_id':f'ROLLING_5Y_{n:02d}','start':cur.isoformat(),'end':e.isoformat(),'selection_policy':'FIXED_5Y_WINDOW_2Y_STEP'})
            cur=date.fromordinal(cur.toordinal()+step_days);n+=1
    return {'schema_version':1,'kind':'ROBUSTNESS_WINDOW_SET','status':'PASS','start':start,'end':end,'windows':windows,'selection_policy':'PREDEFINED_TIME_PARTITIONS_ONLY','automatic_promotion':False,'retuning_authorized':False}
