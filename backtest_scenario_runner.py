from __future__ import annotations
import json
from pathlib import Path
from backtest_contract import BacktestRequest, FrozenExposureReplayAdapter
from backtest_engine import run_backtest
from backtest_run_store import persist_run
from backtest_scenarios import canonical_scenario_set
from backtest_generation import generation_identity
from publication_identity import identity as publication_identity

def run_matrix(workbench='docs/workbench.json', root='research/backtest_runs', out='docs/backtest_scenario_manifest.json'):
    doc=json.loads(Path(workbench).read_text())
    rows=doc.get('replay',{}).get('rows') or []
    if len(rows)<2: raise RuntimeError('SCENARIO_REPLAY_MISSING')
    matrix=canonical_scenario_set(rows[0]['date'],rows[-1]['date'])
    completed=[]
    for spec in matrix['scenarios']:
        q=BacktestRequest(**spec['request'])
        result=run_backtest(rows,q,FrozenExposureReplayAdapter())
        path=persist_run(result,root)
        completed.append({'scenario_id':spec['scenario_id'],'run_id':path.stem,'request_sha256':result['request_sha256'],'rows_sha256':result['rows_sha256'],'ledger_sha256':result['ledger_sha256'],'end_equity':result['end_equity'],'paid_capital':result['paid_capital'],'max_drawdown':result['max_drawdown']})
    payload={'schema_version':1,'kind':'BACKTEST_SCENARIO_MANIFEST','status':'PASS' if len(completed)==len(matrix['scenarios']) else 'FAIL','expected':len(matrix['scenarios']),'completed':len(completed),'selection_policy':'NONE','automatic_promotion':False,'automatic_trading_authorized':False,'runs':completed}
    payload['m2_generation_id']=generation_identity(payload)
    payload['publication_identity']=publication_identity(workbench)
    payload['generation_id']=payload['publication_identity']['generation_id']
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(payload,indent=2)+'\n')
    return payload

if __name__=='__main__': print(json.dumps(run_matrix(),indent=2))
