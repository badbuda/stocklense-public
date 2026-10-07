from backtest_stress_adapters import add_one_session_lag,add_session_lag,DelayedExposureReplayAdapter
def test_delay_uses_prior_prior_exposure_without_mutating_rows():
    rows=[{'date':'1','close':1,'leverage':1},{'date':'2','close':1,'leverage':2},{'date':'3','close':1,'leverage':3},{'date':'4','close':1,'leverage':4}]
    x=add_one_session_lag(rows);assert [r['lagged_leverage'] for r in x]==[1,1,2,3];assert 'lagged_leverage' not in rows[0]
    a=DelayedExposureReplayAdapter();assert a.target_exposure(x[1],x[2])==2
def test_multi_session_delay_ladder():
    rows=[{'date':str(i),'close':1,'leverage':i} for i in range(1,6)]
    assert [r['lagged_leverage'] for r in add_session_lag(rows,2)]==[1,1,1,2,3]
    assert [r['lagged_leverage'] for r in add_session_lag(rows,3)]==[1,1,1,1,2]
