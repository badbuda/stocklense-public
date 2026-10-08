import csv
import json
import pytest
from dashboard_research_curves import build


def test_research_curves_model_and_qqq_are_separate(tmp_path):
    source = tmp_path / "daily.csv"
    with source.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["date", "qqq_return", "baseline_return"])
        writer.writeheader()
        writer.writerows([
            {"date": "2026-01-02", "qqq_return": "0.01", "baseline_return": "0.02"},
            {"date": "2026-01-05", "qqq_return": "-0.01", "baseline_return": "-0.02"},
        ])
    dest = tmp_path / "curves.json"
    result = build(str(source), str(dest))
    assert result["source_rows"] == 2
    assert result["series"]["QQQ"][-1]["nav"] == pytest.approx(99.99)
    assert result["series"]["SL8_RESEARCH_APPROX"][-1]["nav"] == pytest.approx(99.96)
    assert result["full_lean_execution_parity"] is False
    assert json.loads(dest.read_text())["automatic_promotion"] is False


def test_missing_research_source_fails_closed(tmp_path):
    with pytest.raises(RuntimeError, match="SOURCE_MISSING"):
        build(str(tmp_path / "missing.csv"), str(tmp_path / "out.json"))


def test_out_of_order_dates_fail_closed(tmp_path):
    source = tmp_path / "daily.csv"
    source.write_text("date,qqq_return,baseline_return\n2026-01-05,0.01,0.02\n2026-01-02,0.01,0.02\n")
    with pytest.raises(RuntimeError, match="DATE_SEQUENCE_INVALID"):
        build(str(source), str(tmp_path / "curves.json"))
