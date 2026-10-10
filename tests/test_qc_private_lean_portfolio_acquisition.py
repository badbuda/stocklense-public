"""Adversarial private P1 LEAN portfolio source: no synthetic fill claims.

These synthetic three-session data are ONLY test fixtures. The production
importer requires the original locked 3774-session source via extract().
"""
import json
from datetime import datetime,timezone
from copy import deepcopy

import pytest
import qc_private_lean_portfolio_acquisition as m


def ts(s):
    return int(datetime.fromisoformat(s+"T20:01:00+00:00").timestamp())


@pytest.fixture
def case(tmp_path,monkeypatch):
    dates=("2009-09-01","2009-10-01","2009-10-02")
    fake_original=[{"date":d,"timestamp_utc":datetime.fromtimestamp(ts(d),timezone.utc).isoformat().replace("+00:00","Z"),
                    "nav_multiple":1.0} for d in dates]
    monkeypatch.setattr(m,"extract",lambda path:(fake_original,{"source_sha256":"synthetic-unit-fixture-not-original"}))
    monkeypatch.setattr(m,"compare_original_rerun_invariants",lambda a,b:{
        "native_execution_behavior_unchanged":True,
        "frozen_reference_order_count":345,
        "native_lean_closed_trades":301,
        "original_run_source_code_hash_attested":False,
        "independent_broker_quotes_proven":False})
    monkeypatch.setattr(m,"EXPECTED_DEPOSITS",1)
    monkeypatch.setattr(m,"EXPECTED_CONTRIBUTED",103500.)
    source={"statistics":{"End Equity":"103500.00"},
            "runtimeStatistics":{"Holdings":"$100,500.00"},
            "algorithmConfiguration":{"endDate":"2009-10-03T23:59:59Z"}}
    original=tmp_path/"original.json";original.write_text(json.dumps(source))
    rows={
        "equity":[100000.,103500.,103500.],
        "cash":[100000.,103500.,3000.],
        "qqq_quantity":[0.,0.,1005.],
        "qld_quantity":[0.,0.,0.],
        "tqqq_quantity":[0.,0.,0.],
        "units":[100000.,103500.,103500.],
        "contributed":[100000.,103500.,103500.],
    }
    chart={"charts":{m.CHART:{"series":{
        k:{"values":[[ts(d),v] for d,v in zip(dates,values)]}
        for k,values in rows.items()}}}}
    rerun=tmp_path/"observer.json";rerun.write_text(json.dumps(chart))
    return original,rerun,chart


def test_seven_complete_daily_accounts_cashflow_and_nav_prove_only_observed_chart(case,tmp_path):
    original,rerun,_=case
    csv_path=tmp_path/"portfolio.csv";aud=tmp_path/"audit.json"
    report=m.export_private(original,rerun,csv_path,aud)
    assert report["status"]=="ORIGINAL_LEAN_P1_OBSERVED_CHART_RECONCILED"
    assert report["rows"]==3
    assert report["contribution_count"]==1
    assert report["endpoint_reconciliation"]["ending_inferred_cash_from_original_runtime"]==3000.
    assert report["endpoint_reconciliation"]["observational_cash_plus_holdings_reconciled"] is True
    assert report["full_portfolio_path_PARITY_proven"] is False
    assert report["independently_reconstructed_Python_same_start_portfolio_path"] is False
    assert report["native_plot_values_bit_exact_unrounded"] is False
    assert report["actual_broker_fills_proven"] is False
    assert report["capital_deployment_authorized"] is False
    assert len(csv_path.read_text().splitlines())==4
    assert json.loads(aud.read_text())==report
    assert report["private_portfolio_csv_sha256"]


@pytest.mark.parametrize("mutation,error",[
    (lambda z:z["charts"][m.CHART]["series"]["cash"]["values"].pop(),"LEAN_P1_INCOMPLETE_EXACT_DAILY_SERIES"),
    (lambda z:z["charts"][m.CHART]["series"]["cash"]["values"][1].__setitem__(0,ts("2009-09-30")),"LEAN_P1_TIMESTAMP_NOT_IDENTICAL_TO_ORIGINAL"),
    (lambda z:z["charts"][m.CHART]["series"]["contributed"]["values"][1].__setitem__(1,103400.),"LEAN_P1_NONMONTHLY_CASHFLOW_AMOUNT"),
    (lambda z:z["charts"][m.CHART]["series"]["units"]["values"][1].__setitem__(1,103000.),"LEAN_P1_NAV_UNITS_DO_NOT_RECONCILE"),
    (lambda z:z["charts"][m.CHART]["series"]["equity"]["values"][-1].__setitem__(1,104000.),"LEAN_P1_NAV_UNITS_DO_NOT_RECONCILE"),
    (lambda z:z["charts"][m.CHART]["series"]["cash"]["values"][-1].__setitem__(1,-100000.),"LEAN_P1_NEGATIVE_CASH_WITHOUT_MARGIN"),
    (lambda z:z["charts"][m.CHART]["series"]["qqq_quantity"]["values"][-1].__setitem__(1,-2.),"LEAN_P1_NEGATIVE_HOLDINGS_QUANTITY"),
])
def test_reject_corruption_or_incomplete_chart(case,mutation,error):
    original,rerun,chart=case
    mutated=deepcopy(chart)
    mutation(mutated)
    rerun.write_text(json.dumps(mutated))
    with pytest.raises(ValueError,match=error):
        m.project(original,rerun)


def test_missing_native_chart_or_any_of_seven_fields_fails(case):
    original,rerun,chart=case
    chart["charts"].pop(m.CHART)
    rerun.write_text(json.dumps(chart))
    with pytest.raises(ValueError,match="LEAN_P1_PORTFOLIO_OBSERVER_CHART_MISSING"):
        m.project(original,rerun)


def test_original_execution_changed_would_block_all_portfolio_provenance(case,monkeypatch):
    original,rerun,_=case
    def fail(*_):
        raise ValueError("LEAN_DIAGNOSTIC_CHANGED_ORIGINAL_RUN")
    monkeypatch.setattr(m,"compare_original_rerun_invariants",fail)
    with pytest.raises(ValueError,match="LEAN_DIAGNOSTIC_CHANGED_ORIGINAL_RUN"):
        m.project(original,rerun)


def test_trailing_portfolio_observation_never_silently_truncated(case):
    original,rerun,chart=case
    for field in m.RAW_PLOTS:
        chart["charts"][m.CHART]["series"][field]["values"].append([ts("2009-10-05"),1.])
    rerun.write_text(json.dumps(chart))
    with pytest.raises(ValueError,match="LEAN_P1_INCOMPLETE_EXACT_DAILY_SERIES"):
        m.project(original,rerun)


def test_run_end_30_aug_is_not_original_29_aug_chart_terminal_claim(case):
    original,rerun,_=case
    source=json.loads(original.read_text())
    # Mock the real QC phenomenon: original chart last Fri? Here original
    # last Fri 2009-10-02, but QC full run includes MON 2009-10-05.
    source["algorithmConfiguration"]["endDate"]="2009-10-05T23:59:59Z"
    # An endpoint return belonging to Monday must NOT be compared to Friday.
    source["statistics"]["End Equity"]="130000.00"
    source["runtimeStatistics"]["Holdings"]="$124,000.00"
    original.write_text(json.dumps(source))
    rows,audit=m.project(original,rerun)
    assert len(rows)==3
    ep=audit["endpoint_reconciliation"]
    assert ep["status"]=="BLOCKED_CHART_END_BEFORE_RUN_END"
    assert ep["run_end_last_XNYS_session"]=="2009-10-05"
    assert ep["original_chart_last_session"]=="2009-10-02"
    assert ep["end_of_run_equity_match_proven"] is False
    assert audit["native_p1_chart_sessions"]==3
    assert audit["excluded_one_trailing_session"] is None


def test_exactly_one_next_XNYS_portfolio_trailing_session_reconciles_terminal(case):
    original,rerun,chart=case
    source=json.loads(original.read_text())
    source["algorithmConfiguration"]["endDate"]="2009-10-05T23:59:59Z"
    source["statistics"]["End Equity"]="130000.00"
    source["runtimeStatistics"]["Holdings"]="$125,000.00"
    original.write_text(json.dumps(source))
    from qc_private_lean_portfolio_acquisition import RAW_PLOTS
    end={"equity":130000.,"cash":5000.,"qqq_quantity":1200.,
         "qld_quantity":0.,"tqqq_quantity":0.,
         "units":103500.,"contributed":103500.}
    for field in RAW_PLOTS:
        chart["charts"][m.CHART]["series"][field]["values"].append(
            [ts("2009-10-05"),end[field]])
    rerun.write_text(json.dumps(chart))
    rows,audit=m.project(original,rerun)
    assert len(rows)==3  # original chart never silently lengthened
    assert audit["native_p1_chart_sessions"]==4
    assert audit["excluded_one_trailing_session"]=="2009-10-05"
    assert audit["endpoint_reconciliation"]["status"]=="MATCHED_RUN_END_NATIVE_CHART_WITH_QUANTIZATION_TOLERANCE"
    assert audit["endpoint_reconciliation"]["end_of_run_equity_match_proven"] is True
    assert audit["endpoint_reconciliation"]["end_of_run_holdings_match_proven"] is True


def test_trailing_wrong_or_unsynced_day_fails_closed(case):
    original,rerun,chart=case
    for field in m.RAW_PLOTS:
        chart["charts"][m.CHART]["series"][field]["values"].append(
            [ts("2009-10-06"),1.])
    rerun.write_text(json.dumps(chart))
    with pytest.raises(ValueError,match="LEAN_P1_UNEXPECTED_TRAILING_SESSION"):
        m.project(original,rerun)


def test_missing_native_run_end_metadata_fails_instead_of_claiming_match(case):
    original,rerun,_=case
    src=json.loads(original.read_text())
    del src["algorithmConfiguration"]
    original.write_text(json.dumps(src))
    with pytest.raises(ValueError,match="LEAN_P1_RUN_END_DATE_UNAVAILABLE"):
        m.project(original,rerun)
