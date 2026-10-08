from paper_execution_contract import as_dict, fingerprint
from stocklens.paper import FEE_BPS, SLIPPAGE_BPS


def test_execution_contract_matches_paper_model():
    policy = as_dict()
    assert policy["mode"] == "PROSPECTIVE_PAPER"
    assert policy["fee_bps"] == FEE_BPS
    assert policy["slippage_bps"] == SLIPPAGE_BPS
    assert policy["broker_orders_authorized"] is False
    assert policy["live_trading_authorized"] is False


def test_execution_contract_fingerprint_is_deterministic():
    assert fingerprint() == fingerprint()
    assert len(fingerprint()) == 64
