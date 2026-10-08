from __future__ import annotations
from datetime import date

def _years(a,b): return max((date.fromisoformat(b)-date.fromisoformat(a)).days/365.2425,1e-9)

def benchmark_window_metrics(aligned_rows,start,end,expected_sessions=None):
    rows=[x for x in aligned_rows if start<=x['date']<=end]
    if len(rows)<2: return {'status':'BLOCKED','reason':'INSUFFICIENT_SHARED_WINDOW_SESSIONS','shared_sessions':len(rows),'expected_sessions':expected_sessions}
    if expected_sessions is not None and len(rows)!=int(expected_sessions):
        return {'status':'BLOCKED','reason':'INCOMPLETE_EXACT_SESSION_PARITY','shared_sessions':len(rows),'expected_sessions':int(expected_sessions),'coverage_ratio':len(rows)/int(expected_sessions) if int(expected_sessions)>0 else 0.0}
    first,last=rows[0],rows[-1]; total=last['benchmark_adjusted_close']/first['benchmark_adjusted_close']-1
    years=_years(first['date'],last['date']); cagr=(last['benchmark_adjusted_close']/first['benchmark_adjusted_close'])**(1/years)-1
    peak=rows[0]['benchmark_adjusted_close'];dd=0.0
    for r in rows:
        peak=max(peak,r['benchmark_adjusted_close']);dd=min(dd,r['benchmark_adjusted_close']/peak-1)
    return {'status':'PASS','start':first['date'],'end':last['date'],'shared_sessions':len(rows),'expected_sessions':expected_sessions,'coverage_ratio':1.0 if expected_sessions is not None else None,'benchmark_total_return':total,'benchmark_cagr':cagr,'benchmark_max_drawdown':dd}

def relative_windows(strategy_windows,aligned_rows):
    out=[]
    for w in strategy_windows:
        b=benchmark_window_metrics(aligned_rows,w['start'],w['end'],w.get('sessions'))
        row={'window_id':w['window_id'],'start':w['start'],'end':w['end'],'status':b['status'],'benchmark':b}
        if b['status']=='PASS':
            row.update({'strategy_cagr':w.get('cagr'),'strategy_max_drawdown':w.get('max_drawdown'),'excess_cagr':(w['cagr']-b['benchmark_cagr']) if w.get('cagr') is not None else None,'drawdown_delta':(w['max_drawdown']-b['benchmark_max_drawdown']) if w.get('max_drawdown') is not None else None})
        out.append(row)
    return out
