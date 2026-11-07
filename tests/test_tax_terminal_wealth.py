"""Research-only after-tax net-worth views; no broker/AWS mutation."""
import pytest
from research.rebalance_tax_study import replay, compare


def session(day, level, action="REBALANCE_NEXT_SESSION", tqqq=100.0, fx=3.5):
    return {
        "date": day, "leverage": level, "action": action,
        "qqq_0931": 100.0, "qqq_0932": 100.0, "qqq_close": 100.0,
        "tqqq_0931": tqqq, "tqqq_0932": tqqq, "tqqq_close": tqqq,
        "fx_ils_per_usd": fx,
    }


def test_initial_purchase_has_no_realized_tax_but_final_sale_has_cost():
    result = replay([session("2026-10-30", 3)])
    terminal = result["terminal_liquidation_research"]
    assert result["estimated_tax_assessed_ils"] == "0"
    assert terminal["additional_liquidation_tax_ils"] == "0"
    assert terminal["additional_liquidation_cost_usd"] > 0
    assert terminal["estimated_after_tax_value_if_liquidated_usd"] < result["nav_usd"]
    assert result["ledger"][0]["estimated_cumulative_tax_assessed_ils"] == "0"
    assert terminal["actual_broker_cash_or_tax_withheld"] is False


def test_sell_profit_tax_reduces_reinvestable_cash():
    events = [session("2026-10-30",3), session("2026-11-02",0,"ENTER_CASH_NEXT_SESSION",tqqq=120)]
    gross = replay(events)
    immediate = replay(events, immediate_tax_withholding=True)
    terminal_gross = gross["terminal_liquidation_research"]
    terminal_immediate = immediate["terminal_liquidation_research"]
    assert float(gross["estimated_tax_assessed_ils"]) > 0
    assert gross["nav_usd"] > immediate["nav_usd"]
    assert terminal_gross["unpaid_past_assessed_tax_ils"] != "0"
    assert terminal_immediate["unpaid_past_assessed_tax_ils"] == "0"
    assert terminal_immediate["additional_liquidation_tax_ils"] == "0"
    assert terminal_immediate["estimated_after_tax_value_if_liquidated_usd"] == pytest.approx(immediate["nav_usd"],abs=1e-3)
    assert terminal_gross["estimated_after_tax_value_if_liquidated_usd"] == pytest.approx(immediate["nav_usd"], abs=1e-3)


def test_tax_lots_are_not_mutated_by_hypothetical_liquidation():
    result = replay([session("2026-10-30",3),session("2026-11-02",3,"NO_CHANGE",tqqq=101)])
    assert result["tax_book"]["holdings"]["TQQQ"] == result["ledger"][-1]["shares"]["TQQQ"]
    assert all(int(v) >= 0 for v in result["ledger"][-1]["shares"].values())
    assert result["terminal_liquidation_research"]["estimated_after_tax_value_if_liquidated_usd"] <= result["terminal_liquidation_research"]["pre_tax_value_if_liquidated_usd"]


def test_wrapper_comparison_is_explicitly_unverified_and_leaves_input_unchanged():
    events = [session("2026-10-30",3),session("2026-11-02",0,"ENTER_CASH_NEXT_SESSION",tqqq=120)]
    before = repr(events)
    result = compare(events)
    assert repr(events) == before
    wrap = result["tax_wrapper_illustrations"]
    assert wrap["ira_eligibility_or_tqqq_allowed_verified"] is False
    assert wrap["ira_fee_and_withdrawal_conditions_modeled"] is False
    assert wrap["ira_eligible_tax_exempt_if_liquidated_before_ira_fees_usd"] > wrap["brokerage_after_tax_if_liquidated_immediate_scenario_usd"]
