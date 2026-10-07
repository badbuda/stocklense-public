from backtest_contract import BacktestRequest,FrozenExposureReplayAdapter,stocklens_8_request
import pytest

def test_stocklens_adapter_preserves_prior_session_exposure_semantics():
 a=FrozenExposureReplayAdapter()
 rows=[{"date":"2026-01-01","close":100.0,"leverage":3.0},{"date":"2026-01-02","close":101.0,"leverage":2.0}]
 a.validate_rows(rows)
 assert a.target_exposure(rows[0],rows[1])==3.0
 assert a.strategy_id=="STOCKLENS_8_FROZEN_REPLAY"
 assert a.evidence_class=="REPLAY_APPROXIMATION"

def test_generic_request_is_strategy_addressable():
 r=BacktestRequest("OTHER_STRATEGY",1000,100,7)
 assert r.strategy_id=="OTHER_STRATEGY"
 s=stocklens_8_request(2000,250,10,"2020-01-01","2021-01-01")
 assert s.strategy_id=="STOCKLENS_8_FROZEN_REPLAY"
 assert s.initial_capital==2000
 assert s.monthly_contribution==250
 assert s.transaction_cost_bps==10

def test_adapter_fails_closed_on_invalid_rows():
 a=FrozenExposureReplayAdapter()
 with pytest.raises(ValueError,match="BACKTEST_REPLAY_TOO_SHORT"):
  a.validate_rows([])
 with pytest.raises(ValueError,match="BACKTEST_ROW_MISSING"):
  a.validate_rows([{"date":"a","close":1,"leverage":1},{"date":"b","close":2}])
