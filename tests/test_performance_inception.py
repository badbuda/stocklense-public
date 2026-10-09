import csv
import json

import pytest

from performance_analytics import build_performance


def fixture_paths(tmp_path, *, initial=100000.0, equity=97427.96316081587, reported=None):
    ledger = tmp_path / "ledger.csv"
    state = tmp_path / "state.json"
    out = tmp_path / "performance.json"
    state.write_text(json.dumps({"initial_equity": initial}))
    row = {
        "session_date": "2026-10-08",
        "equity": equity,
        "cumulative_return": equity / initial - 1 if reported is None else reported,
        "drawdown": equity / initial - 1,
        "cumulative_fees": 19.715132633546446,
        "cumulative_slippage_cost": 98.47718598174681,
        "trade_count_session": 1,
    }
    with ledger.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=row)
        writer.writeheader()
        writer.writerow(row)
    return ledger, state, out


def test_first_paper_session_includes_inception_loss(tmp_path):
    ledger, state, out = fixture_paths(tmp_path)
    result = build_performance(str(out), str(ledger), str(state))
    assert result["sessions"] == 1
    assert result["start_equity"] == 100000
    assert result["cumulative_return"] == pytest.approx(-0.02572036839184133)
    assert result["total_return_pct"] == pytest.approx(-2.572036839184133)
    assert result["fee_drag_pct"] == pytest.approx(19.715132633546446 / 100000 * 100)
    assert result["return_basis"] == "PAPER_STATE_INITIAL_EQUITY"
    assert json.loads(out.read_text()) == result


def test_mismatch_fails_closed_without_publishing(tmp_path):
    ledger, state, out = fixture_paths(tmp_path, reported=0.0)
    with pytest.raises(ValueError, match="PAPER_LEDGER_INCEPTION_RETURN_MISMATCH"):
        build_performance(str(out), str(ledger), str(state))
    assert not out.exists()


def test_missing_state_fails_closed(tmp_path):
    ledger, state, out = fixture_paths(tmp_path)
    state.unlink()
    with pytest.raises(ValueError, match="PAPER_INITIAL_EQUITY_STATE_MISSING"):
        build_performance(str(out), str(ledger), str(state))
    assert not out.exists()


def test_empty_ledger_waits_without_requiring_state(tmp_path):
    out = tmp_path / "performance.json"
    result = build_performance(str(out), str(tmp_path / "nonexistent.csv"), str(tmp_path / "nonexistent.json"))
    assert result == {"status": "WAITING_FOR_PROSPECTIVE_DATA", "sessions": 0}
