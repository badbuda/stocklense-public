"""F-05 regression: shared frozen paper/cockpit math, no live broker calls."""
import pytest

from paper_rebalance_math import target_shares, weight_gap, within_band


@pytest.mark.parametrize("weights", [
    {"QQQ": 0., "TQQQ": .985},
    {"QQQ": .50, "TQQQ": .485},
    {"QQQ": .985, "TQQQ": 0.},
    {"QQQ": 0., "TQQQ": 0.},
])
def test_whole_share_floor_matches_paper_equation(weights):
    prices = {"QQQ": 751.23, "TQQQ": 81.28}
    equity = 98_696.78023845259
    expected = {s: int((equity * w) // prices[s]) for s, w in weights.items()}
    assert target_shares(weights, equity, prices) == expected


def test_actual_two_day_paper_holdings_inside_band():
    holdings = {"QQQ": 0, "TQQQ": 1197}
    prices = {"QQQ": 751.24, "TQQQ": 81.28}
    equity = 98696.78023845259
    weights = {"QQQ": 0, "TQQQ": .985}
    # Published ledger gap was computed at 09:32, not at this EOD close.
    # Do not compare values at different observation timestamps exactly.
    assert 0 < weight_gap(holdings, weights, prices, equity) < .005
    assert within_band(holdings, weights, prices, equity)


def test_out_of_band_stale_position_must_not_silently_hold():
    holdings = {"QQQ": 900, "TQQQ": 0}
    prices = {"QQQ": 100., "TQQQ": 50.}
    weights = {"QQQ": 0., "TQQQ": .985}
    assert not within_band(holdings, weights, prices, 100000)


@pytest.mark.parametrize("weights,prices,equity", [
    ({"QQQ": .8, "TQQQ": .6}, {"QQQ": 100, "TQQQ": 50}, 100000),
    ({"QQQ": -.1, "TQQQ": .9}, {"QQQ": 100, "TQQQ": 50}, 100000),
    ({"QQQ": 0, "TQQQ": .985}, {"QQQ": 0, "TQQQ": 50}, 100000),
    ({"QQQ": 0, "TQQQ": .985}, {"QQQ": 100, "TQQQ": 50}, 0),
])
def test_invalid_prices_weights_or_equity_fail_closed(weights, prices, equity):
    with pytest.raises(ValueError):
        target_shares(weights, equity, prices)


def test_actual_paper_and_cockpit_import_same_functions():
    from stocklens import paper
    import execution_cockpit
    assert paper.target_shares is execution_cockpit.target_shares
    assert paper.within_band is execution_cockpit.within_band
    assert paper.weight_gap is execution_cockpit.weight_gap
