"""P1 native ledger tests; fixture prices/fills are invented ONLY for tests."""
from copy import deepcopy
import pytest
from qc_p1_native_order_ledger_audit import reconcile

def fixture():
    rows=[
      {"date":"2020-03-02","equity":100000.,"cash":89998.,
       "contributed":100000.,"qqq_quantity":100.,"qld_quantity":0.,
       "tqqq_quantity":0.},
      {"date":"2020-03-03","equity":104000.,"cash":93498.,
       "contributed":103500.,"qqq_quantity":100.,"qld_quantity":0.,
       "tqqq_quantity":0.},
      {"date":"2020-03-04","equity":103545.99,"cash":103545.99,
       "contributed":103500.,"qqq_quantity":0.,"qld_quantity":0.,
       "tqqq_quantity":0.}]
    def o(oid,when,qty,fill):
        return {"id":oid,"time":when+"T14:32:00Z","status":3,
                "symbol":{"value":"QQQ"},"quantity":float(qty),
                "price":float(fill),"value":float(qty*fill)}
    orders={"1":o(1,"2020-03-02",100,100.),
            "2":o(2,"2020-03-04",-100,100.5)}
    stats={"Total Fees":"$4.01"}
    return rows,orders,stats


def test_native_ledger_deterministic_crosscheck_and_fee_inference():
    r,o,s=fixture()
    proof=reconcile(r,o,s,lock_original_counts=False)
    assert proof["status"]=="ORIGINAL_LEAN_P1_NATIVE_ORDER_AND_CHART_LEDGER_RECONCILED"
    assert proof["verified_native_plot_sessions"]==3
    assert proof["native_filled_orders"]==2
    assert proof["checked_daily_etf_share_states"]==9
    assert proof["maximum_share_difference"]==0
    assert proof["days_without_fills"]==1
    assert proof["deposits"]==1
    assert proof["cumulative_external_capital"]==103500.
    assert proof["fee_total_reconciliation_absolute_USD"]<1e-8
    assert proof["all_days_without_orders_have_no_unexplained_cash_delta"]
    assert proof["original_2024_08_30_end_account_chart_confirmed"] is False
    assert proof["independent_same_start_python_portfolio_parity_proven"] is False
    assert proof["actual_broker_fills_observed"] is False
    assert proof["capital_deployment_authorized"] is False
    assert "orders" not in proof  # never export private order objects


@pytest.mark.parametrize("change,expected",[
  (lambda r,o,s:r[1].update(qqq_quantity=99.),"P1_NATIVE_SHARE_LEDGER_MISMATCH"),
  (lambda r,o,s:r[1].update(cash=93470.),"P1_UNEXPLAINED_NONTRADE_CASH_MOVEMENT"),
  (lambda r,o,s:r[2].update(cash=103550.),"P1_NEGATIVE_FEE_DURING_ORDER_SESSION"),
  (lambda r,o,s:r[2].update(contributed=103650.),"P1_BAD_MONTHLY_CONTRIBUTION"),
  (lambda r,o,s:o["2"].update(value=-10051.),"P1_NATIVE_ORDER_NOTIONAL_NOT_QUANTITY_TIMES_FILL"),
  (lambda r,o,s:o["2"].update(quantity=-99.),"P1_NATIVE_ORDER_NOTIONAL_NOT_QUANTITY_TIMES_FILL"),
  (lambda r,o,s:o["2"].update(status=1),"P1_NATIVE_ORDER_NOT_FILLED"),
  (lambda r,o,s:o["2"].update(time="2020-03-05T14:32:00Z"),"P1_ORDER_OUTSIDE_ORIGINAL_CHART_RANGE"),
  (lambda r,o,s:s.update({"Total Fees":"$7.00"}),"P1_NATIVE_TOTAL_FEE_CASH_RECONCILIATION_FAILED"),
  (lambda r,o,s:o["1"]["symbol"].update(value="SPY"),"P1_UNEXPECTED_NATIVE_ORDER_SYMBOL"),
])
def test_fail_closed_if_positions_cash_fees_original_orders_drift(change,expected):
    a,b,c=fixture()
    change(a,b,c)
    with pytest.raises(ValueError,match=expected):
        reconcile(a,b,c,lock_original_counts=False)


def test_all_native_order_ids_must_be_correct_and_account_dates_unique():
    a,b,c=fixture()
    b["2"]["id"]=3
    with pytest.raises(ValueError,match="P1_NATIVE_ORDER_ID_INVALID"):
        reconcile(a,b,c,lock_original_counts=False)
    a,b,c=fixture()
    a[2]["date"]=a[1]["date"]
    with pytest.raises(ValueError,match="P1_DUPLICATE_ACCOUNT_SESSION"):
        reconcile(a,b,c,lock_original_counts=False)


def test_unseen_order_sessions_and_empty_data_are_never_backfilled():
    a,b,c=fixture()
    with pytest.raises(ValueError,match="P1_ORIGINAL_SESSION_OR_ORDER_COUNT_DRIFT"):
        reconcile(a,b,c,lock_original_counts=True)
    with pytest.raises(ValueError,match="P1_MISSING_NATIVE_ACCOUNT_ROWS"):
        reconcile([],b,c,lock_original_counts=False)
