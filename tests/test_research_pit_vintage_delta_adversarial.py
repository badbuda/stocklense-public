import pytest
from research_pit_vintage_delta import compare_vintages
from test_research_pit_vintage_delta import snap

A=[("2026-10-09","0.10"),("2026-10-12",".")]
B=[("2026-10-09","0.11"),("2026-10-12","0.20"),("2026-10-13","0.15")]

def run(a=A,b=B,early="2026-10-13",late="2026-10-14"):
    return compare_vintages(snap(early,a),snap(late,b),
        series_id="T10Y3M",decision_session="2026-10-15")

def test_history_removal_rejected():
    with pytest.raises(ValueError,match="TRUNCATED"):
        run(b=B[1:])

def test_reverse_vintage_rejected():
    with pytest.raises(ValueError,match="VINTAGES_NOT_STRICTLY_ORDERED"):
        run(early="2026-10-14",late="2026-10-13")

def test_future_vintage_rejected():
    with pytest.raises(ValueError,match="future or multi-day"):
        run(late="2026-10-15")

def test_decimal_equivalent_not_revision():
    r=run(a=[("2026-10-09","0.100")],b=[("2026-10-09","0.1")])
    assert r["changed_overlap_values"]==0
