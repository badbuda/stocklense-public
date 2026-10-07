from __future__ import annotations
import json
import statistics
from pathlib import Path
from backtest_contract import BacktestRequest,FrozenExposureReplayAdapter
from backtest_engine import run_backtest
from backtest_robustness import fixed_subperiods
from publication_identity import identity

def build(workbench='docs/workbench.json',out='docs/backtest_robustness.json'):
    w=json.loads(Path(workbench).read_text());rows=w.get('replay',{}).get('rows') or []
    if len(rows)<2: raise RuntimeError('ROBUSTNESS_REPLAY_MISSING')
    ws=fixed_subperiods(rows[0]['date'],rows[-1]['date']);results=[]
    for x in ws['windows']:
        q=BacktestRequest(strategy_id='STOCKLENS_8_FROZEN_REPLAY',initial_capital=100000,monthly_contribution=0,transaction_cost_bps=5,start=x['start'],end=x['end'])
        try:
            r=run_backtest(rows,q,FrozenExposureReplayAdapter())
        except ValueError:
            continue
        results.append({'window_id':x['window_id'],'selection_policy':x['selection_policy'],'start':r['start'],'end':r['end'],'sessions':r['sessions'],'end_equity':r['end_equity'],'replay_profit_loss':r['replay_profit_loss'],'max_drawdown':r['max_drawdown'],'cagr':r.get('analytics',{}).get('cagr_without_contribution_distortion'),'total_estimated_transaction_cost':r['total_estimated_transaction_cost'],'request_sha256':r['request_sha256'],'rows_sha256':r['rows_sha256'],'ledger_sha256':r['ledger_sha256']})
    cagrs=[x['cagr'] for x in results if x.get('cagr') is not None]
    pnls=[x['replay_profit_loss'] for x in results]
    dds=[x['max_drawdown'] for x in results]
    costs=[x['total_estimated_transaction_cost'] for x in results]
    positive=sorted([x for x in results if x['replay_profit_loss']>0],key=lambda x:x['replay_profit_loss'],reverse=True)
    positive_total=sum(x['replay_profit_loss'] for x in positive)
    top1=(positive[0]['replay_profit_loss']/positive_total) if positive_total>0 else None
    top3=(sum(x['replay_profit_loss'] for x in positive[:3])/positive_total) if positive_total>0 else None
    thirds=[x for x in results if x['window_id'].startswith('THIRD_')]
    thirds_positive=sorted([x for x in thirds if x['replay_profit_loss']>0],key=lambda x:x['replay_profit_loss'],reverse=True)
    thirds_positive_total=sum(x['replay_profit_loss'] for x in thirds_positive)
    nonoverlap={'window_count':len(thirds),'positive_pnl_windows':len(thirds_positive),'positive_pnl_total':thirds_positive_total,'top1_positive_pnl_share':(thirds_positive[0]['replay_profit_loss']/thirds_positive_total) if thirds_positive_total>0 else None,'top2_positive_pnl_share':(sum(x['replay_profit_loss'] for x in thirds_positive[:2])/thirds_positive_total) if thirds_positive_total>0 else None,'semantics':'Non-overlapping chronological thirds only; cleaner concentration diagnostic than overlapping rolling windows.'}
    summary={'window_count':len(results),'positive_pnl_windows':sum(1 for x in pnls if x>0),'positive_pnl_share':(sum(1 for x in pnls if x>0)/len(pnls) if pnls else None),'cagr_min':min(cagrs) if cagrs else None,'cagr_median':statistics.median(cagrs) if cagrs else None,'cagr_max':max(cagrs) if cagrs else None,'cagr_range':(max(cagrs)-min(cagrs)) if cagrs else None,'cagr_population_stdev':statistics.pstdev(cagrs) if len(cagrs)>1 else 0.0 if cagrs else None,'worst_max_drawdown':min(dds) if dds else None,'median_max_drawdown':statistics.median(dds) if dds else None,'total_estimated_transaction_cost_across_windows':sum(costs),'positive_pnl_total':positive_total,'top1_positive_pnl_share':top1,'top3_positive_pnl_share':top3,'positive_contributor_count':len(positive),'concentration_semantics':'Shares of summed positive window P&L; overlapping rolling windows are descriptive and not additive portfolio returns.','nonoverlapping_thirds_concentration':nonoverlap}
    payload={'schema_version':1,'kind':'BACKTEST_ROBUSTNESS_EVIDENCE','status':'PASS' if len(results)>=3 else 'BLOCKED','publication_identity':identity(),'evidence_class':'REPLAY_APPROXIMATION','window_policy':ws['selection_policy'],'window_count':len(results),'summary':summary,'windows':results,'automatic_promotion':False,'retuning_authorized':False,'interpretation':'Predefined time-window stability evidence only. No window is selected as a winner and no model parameter is retuned.'}
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(payload,indent=2)+'\n');return payload
if __name__=='__main__': print(json.dumps(build(),indent=2))
