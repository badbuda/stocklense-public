from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping,Any
from backtest_contract import FrozenExposureReplayAdapter

@dataclass(frozen=True)
class DelayedExposureReplayAdapter(FrozenExposureReplayAdapter):
    strategy_id:str='STOCKLENS_8_DELAYED_1_SESSION'
    evidence_class:str='EXECUTION_DELAY_STRESS'
    def target_exposure(self,previous,current):
        # Engine baseline applies previous-row leverage. lagged_leverage on current is therefore exactly N sessions behind current, so N=1 reproduces baseline timing and larger N adds N-1 extra sessions of delay. Never mutates frozen baseline.
        return float(current.get('lagged_leverage',previous['leverage']))

def add_session_lag(rows,sessions=1):
    if sessions<1: raise ValueError('LAG_MUST_BE_POSITIVE')
    out=[]
    for i,r in enumerate(rows):
        x=dict(r);x['lagged_leverage']=float(rows[max(0,i-sessions)]['leverage']);out.append(x)
    return out

def add_one_session_lag(rows):
    return add_session_lag(rows,1)
