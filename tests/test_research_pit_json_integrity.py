"""SL9-032 synthetic untrusted-source integrity regressions."""
import json
import pytest
from research_pit_credit_gate import fred
from research_pit_event_gate import audit as events
from research_pit_quote_gate import audit as quotes

@pytest.mark.parametrize("gate,source", [
    (fred, '{"series_id":"BAMLH0A0HYM2","series_id":"T10Y3M"}'),
    (events, '[{"provider":"SEC_EDGAR","provider":"GDELT_2_0_GKG"}]'),
    (quotes, '[{"bid":25.01,"bid":25.02}]'),
])
def test_duplicate_keys(gate,source):
    with pytest.raises(ValueError,match="DUPLICATE_JSON_KEY"):
        gate(source.encode())

@pytest.mark.parametrize("gate,source", [
    (fred, '{"value":NaN}'),
    (events, '[{"value":Infinity}]'),
    (quotes, '[{"value":-Infinity}]'),
])
def test_nonfinite_constant(gate,source):
    with pytest.raises(ValueError,match="NONFINITE_JSON_CONSTANT"):
        gate(source.encode())

@pytest.mark.parametrize("gate,source", [
    (fred, '{"value":1e9999}'),
    (events, '[{"value":1e9999}]'),
    (quotes, '[{"value":1e9999}]'),
])
def test_float_overflow(gate,source):
    with pytest.raises(ValueError,match="NONFINITE_JSON_NUMBER"):
        gate(source.encode())
