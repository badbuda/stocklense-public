from __future__ import annotations
import hashlib,json,math
from datetime import date,datetime,timezone
from pathlib import Path

def sha(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def load_benchmark(path='research/benchmarks/QQQ.json'):
    p=Path(path)
    if not p.exists(): return {'status':'BLOCKED','reason':'CANONICAL_BENCHMARK_SERIES_MISSING','symbol':'QQQ','rows':[],'provenance':None}
    try: x=json.loads(p.read_text())
    except Exception: return {'status':'BLOCKED','reason':'BENCHMARK_JSON_INVALID','symbol':'QQQ','rows':[],'provenance':None}
    rows=x.get('rows') or [];prov=x.get('provenance') or {};symbol=x.get('symbol')
    try:
        dates=[r.get('date') for r in rows]; parsed=[date.fromisoformat(v) for v in dates]
        prices=[float(r.get('adjusted_close')) for r in rows]
        retrieved=datetime.fromisoformat(str(prov.get('retrieved_at_utc')).replace('Z','+00:00'))
        valid=bool(rows) and symbol=='QQQ' and all(math.isfinite(v) and v>0 for v in prices) and dates==sorted(dates) and len(dates)==len(set(dates)) and max(parsed)<=datetime.now(timezone.utc).date() and bool(prov.get('source')) and bool(prov.get('source_file_sha256')) and bool(prov.get('raw_source_sha256')) and bool(prov.get('provider')) and bool(prov.get('dataset')) and bool(prov.get('return_semantics')) and bool(prov.get('currency')) and retrieved.tzinfo is not None
    except Exception: valid=False
    return {'status':'PASS' if valid else 'BLOCKED','reason':None if valid else 'BENCHMARK_CONTRACT_INVALID','symbol':symbol or 'QQQ','rows':rows if valid else [],'provenance':prov if valid else None,'rows_sha256':sha(rows) if valid else None,'row_count':len(rows) if valid else 0,'coverage_start':dates[0] if valid else None,'coverage_end':dates[-1] if valid else None}

def align(strategy_rows,benchmark):
    if benchmark.get('status')!='PASS': return {'status':'BLOCKED','reason':benchmark.get('reason'),'rows':[]}
    try:
        sdates=[r['date'] for r in strategy_rows]
        if sdates!=sorted(sdates) or len(sdates)!=len(set(sdates)): raise ValueError()
    except Exception: return {'status':'BLOCKED','reason':'STRATEGY_SESSION_DATES_INVALID','rows':[]}
    b={r['date']:r['adjusted_close'] for r in benchmark['rows']}
    out=[{'date':r['date'],'strategy_close':r.get('close'),'benchmark_adjusted_close':b[r['date']]} for r in strategy_rows if r.get('date') in b]
    coverage=len(out)/len(strategy_rows) if strategy_rows else 0.0
    return {'status':'PASS' if len(out)>=2 else 'BLOCKED','reason':None if len(out)>=2 else 'INSUFFICIENT_SHARED_SESSIONS','rows':out,'shared_sessions':len(out),'strategy_sessions':len(strategy_rows),'benchmark_sessions':benchmark.get('row_count',0),'strategy_coverage_ratio':coverage}
