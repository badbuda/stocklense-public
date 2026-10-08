from __future__ import annotations
import json
from pathlib import Path
from benchmark_contract import load_benchmark,align
from benchmark_relative import relative_windows
from benchmark_distribution import summarize
from publication_identity import identity

def build(workbench='docs/workbench.json',benchmark_path='research/benchmarks/QQQ.json',out='docs/benchmark_evidence.json'):
    w=json.loads(Path(workbench).read_text());sr=w.get('replay',{}).get('rows') or []
    b=load_benchmark(benchmark_path);a=align(sr,b)
    robustness_path=Path('docs/backtest_robustness.json');robustness=json.loads(robustness_path.read_text()) if robustness_path.exists() else {}
    relative=relative_windows(robustness.get('windows') or [],a.get('rows') or []) if a.get('status')=='PASS' else []
    relative_complete=bool(relative) and all(x.get('status')=='PASS' for x in relative) and len(relative)==len(robustness.get('windows') or [])
    payload={'schema_version':1,'kind':'BENCHMARK_EVIDENCE','status':'PASS' if b.get('status')=='PASS' and a.get('status')=='PASS' else 'BLOCKED','publication_identity':identity(),'benchmark':{'symbol':b.get('symbol'),'status':b.get('status'),'reason':b.get('reason'),'row_count':b.get('row_count',0),'rows_sha256':b.get('rows_sha256'),'provenance':b.get('provenance')},'alignment':{k:v for k,v in a.items() if k!='rows'},'relative_metrics_status':'READY' if relative_complete else 'BLOCKED','relative_windows':relative,'relative_window_count':len(relative),'relative_complete':relative_complete,'distribution':summarize(relative) if relative_complete else {'status':'BLOCKED','reason':'RELATIVE_WINDOWS_INCOMPLETE'},'automatic_promotion':False,'retuning_authorized':False,'semantics':'Benchmark-relative metrics are forbidden until canonical adjusted-close provenance and exact-date alignment pass.'}
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(payload,indent=2)+'\n');return payload
if __name__=='__main__': print(json.dumps(build(),indent=2))
