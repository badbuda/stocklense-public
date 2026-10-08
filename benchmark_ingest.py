from __future__ import annotations
import csv,json,hashlib
from datetime import datetime,timezone
from pathlib import Path

def ingest_csv(source_csv,out='research/benchmarks/QQQ.json',symbol='QQQ',source_name=None,provider='FILE_IMPORT',dataset='ADJUSTED_CLOSE_CSV'):
    p=Path(source_csv)
    if not p.exists(): raise FileNotFoundError(source_csv)
    rows=[]
    with p.open(newline='') as f:
        reader=csv.DictReader(f)
        fields=set(reader.fieldnames or [])
        date_key='date' if 'date' in fields else 'Date' if 'Date' in fields else None
        price_key=next((k for k in ('adjusted_close','Adj Close','adj_close') if k in fields),None)
        if not date_key or not price_key: raise ValueError('BENCHMARK_CSV_REQUIRES_DATE_AND_ADJUSTED_CLOSE')
        for r in reader:
            rows.append({'date':r[date_key],'adjusted_close':float(r[price_key])})
    rows=sorted(rows,key=lambda x:x['date'])
    if not rows or len({x['date'] for x in rows})!=len(rows) or any(not __import__('math').isfinite(x['adjusted_close']) or x['adjusted_close']<=0 for x in rows): raise ValueError('BENCHMARK_CSV_INVALID_ROWS')
    payload={'schema_version':1,'symbol':symbol,'price_field':'ADJUSTED_CLOSE','provenance':{'source':source_name or str(p),'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'source_file_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'raw_source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'provider':provider,'dataset':dataset,'ingestion':'benchmark_ingest.py','return_semantics':'PROVIDER_DECLARED_ADJUSTED_CLOSE','currency':'USD'},'rows':rows}
    q=Path(out);q.parent.mkdir(parents=True,exist_ok=True);q.write_text(json.dumps(payload,indent=2)+'\n');return payload
