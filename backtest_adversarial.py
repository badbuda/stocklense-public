from __future__ import annotations
import json
from pathlib import Path
from backtest_contract import BacktestRequest,FrozenExposureReplayAdapter
from backtest_engine import run_backtest
from backtest_stress_adapters import DelayedExposureReplayAdapter,add_session_lag

def run(rows,adapter,cost):
    q=BacktestRequest(strategy_id=adapter.strategy_id,initial_capital=100000,monthly_contribution=0,transaction_cost_bps=cost,start=rows[0]['date'],end=rows[-1]['date'])
    return run_backtest(rows,q,adapter)
def build(workbench='docs/workbench.json',out='docs/backtest_adversarial.json'):
    w=json.loads(Path(workbench).read_text());rows=w.get('replay',{}).get('rows') or []
    if len(rows)<20:raise RuntimeError('ADVERSARIAL_REPLAY_MISSING')
    base=run(rows,FrozenExposureReplayAdapter(),5)
    stresses=[]
    for cost in (10,25,50,100,150,200):
        r=run(rows,FrozenExposureReplayAdapter(),cost);stresses.append({'id':f'COST_{cost}BPS','cost_bps':cost,'end_equity':r['end_equity'],'cagr':r['analytics']['cagr_without_contribution_distortion'],'max_drawdown':r['max_drawdown'],'delta_end_equity_vs_base':r['end_equity']-base['end_equity']})
    for sessions in (2,3,4):
        lagrows=add_session_lag(rows,sessions);lag=run(lagrows,DelayedExposureReplayAdapter(),5);stresses.append({'id':f'{sessions-1}_EXTRA_SESSION_EXECUTION_DELAY','extra_delay_sessions':sessions-1,'effective_signal_age_sessions':sessions,'cost_bps':5,'end_equity':lag['end_equity'],'cagr':lag['analytics']['cagr_without_contribution_distortion'],'max_drawdown':lag['max_drawdown'],'delta_end_equity_vs_base':lag['end_equity']-base['end_equity']})
    x={'schema_version':1,'status':'PASS','baseline':{'end_equity':base['end_equity'],'cagr':base['analytics']['cagr_without_contribution_distortion'],'max_drawdown':base['max_drawdown']},'stresses':stresses,'interpretation':'Adversarial sensitivity only. Frozen baseline already uses the prior completed-session exposure. Delay stresses add 1/2/3 EXTRA sessions beyond that baseline timing. No stress result retunes or promotes the frozen model.','automatic_promotion':False}
    Path(out).write_text(json.dumps(x,indent=2)+'\n');return x
if __name__=='__main__':print(json.dumps(build(),indent=2))
