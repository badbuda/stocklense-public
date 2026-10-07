from __future__ import annotations
from dataclasses import asdict
from backtest_contract import stocklens_8_request

def canonical_scenario_set(start: str, end: str) -> dict:
    specs=[('BASE_100K_3500_5',100000,3500,5),('NO_CONTRIBUTIONS',100000,0,5),('LOWER_MONTHLY_1000',100000,1000,5),('HIGHER_MONTHLY_5000',100000,5000,5),('ZERO_COST',100000,3500,0),('HIGH_COST_10BPS',100000,3500,10),('STRESS_COST_25BPS',100000,3500,25)]
    scenarios=[]
    for sid,initial,monthly,cost in specs:
        q=stocklens_8_request(initial,monthly,cost,start,end)
        scenarios.append({'scenario_id':sid,'request':asdict(q)})
    return {'schema_version':1,'kind':'BACKTEST_SCENARIO_SET','status':'PASS','selection_policy':'NONE','automatic_promotion':False,'automatic_trading_authorized':False,'scenarios':scenarios,'semantics':'Fixed descriptive scenario matrix. Side-by-side comparison only; no ranking or model retuning.'}
