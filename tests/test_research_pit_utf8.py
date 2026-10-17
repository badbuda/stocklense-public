import pytest
from research_pit_event_gate import audit

def test_invalid_utf8_rejected_before_provenance_parsing():
    with pytest.raises(ValueError, match="INVALID_JSON_ENCODING_OR_SYNTAX"):
        audit(bytes([255]))
