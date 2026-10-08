from __future__ import annotations
import argparse,csv,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from benchmark_ingest import ingest_csv

def raw_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def materialize(source_csv, provider, dataset, return_semantics, currency='USD', out='research/benchmarks/QQQ.json'):
    if not all(str(x).strip() for x in (provider,dataset,return_semantics,currency)): raise ValueError('BENCHMARK_SOURCE_METADATA_REQUIRED')
    x=ingest_csv(source_csv,out,source_name=f'{provider}:{dataset}')
    p=Path(out); data=json.loads(p.read_text())
    rows=data.get('rows') or []
    data['provenance'].update({'provider':provider,'dataset':dataset,'return_semantics':return_semantics,'currency':currency,'raw_source_sha256':raw_sha(source_csv),'coverage_start':rows[0]['date'] if rows else None,'coverage_end':rows[-1]['date'] if rows else None,'materializer':'benchmark_acquire.py'})
    p.write_text(json.dumps(data,indent=2)+'\n')
    return data

if __name__=='__main__':
    ap=argparse.ArgumentParser(description='Materialize canonical QQQ from an explicitly acquired provider CSV.')
    ap.add_argument('--source-csv',required=True);ap.add_argument('--provider',required=True);ap.add_argument('--dataset',required=True);ap.add_argument('--return-semantics',required=True);ap.add_argument('--currency',default='USD');ap.add_argument('--out',default='research/benchmarks/QQQ.json')
    a=ap.parse_args();print(json.dumps(materialize(a.source_csv,a.provider,a.dataset,a.return_semantics,a.currency,a.out),indent=2))
