"""Toy historical EFFR dates test clock, no synthetic trading alpha claims."""
import copy
import pytest

from research_actual_effr_cash_sensitivity import normalize, rate_schedule


def data():
    return {"schema_version":1,"series":"EFFR",
      "source_url":"https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2024-03-01",
      "not_broker_deposit_yield":True,
      "publication_clock_available_in_api":False,
      "asof_tradability_verified":False,
      "observations":[
        {"effective_date":"2024-03-15","rate_percent":5.33,
         "provider_publication_timestamp_verified":False},
        {"effective_date":"2024-03-18","rate_percent":5.32,
         "provider_publication_timestamp_verified":False},
        {"effective_date":"2024-03-19","rate_percent":5.31,
         "provider_publication_timestamp_verified":False},
      ]}


def test_benchmark_clock_delayed_by_two_completed_sessions():
    ds=["2024-03-18","2024-03-19","2024-03-20","2024-03-21"]
    rates,joins=rate_schedule(ds,data())
    assert rates==pytest.approx([0.,0.,.0533,.0532])
    assert joins[0]["selected_effective_date"]=="2024-03-15"
    assert joins[1]["selected_effective_date"]=="2024-03-18"


def test_future_effective_date_and_outcome_do_not_affect_old_rates():
    ds=["2024-03-18","2024-03-19","2024-03-20","2024-03-21"]
    initial,_=rate_schedule(ds,data())
    altered=copy.deepcopy(data())
    altered["observations"].append(
      {"effective_date":"2024-03-22","rate_percent":25.,
       "provider_publication_timestamp_verified":False})
    updated,_=rate_schedule(ds,altered)
    assert initial==updated


def test_publication_clock_self_claim_never_accepted_as_attestation():
    x=data()
    x["asof_tradability_verified"]=True
    with pytest.raises(ValueError,match="EFFR_CANNOT_SELF_ASSERT"):
        normalize(x)
    x=data()
    x["observations"][0]["provider_publication_timestamp_verified"]=True
    with pytest.raises(ValueError,match="EFFR_NOT_INDEPENDENT"):
        normalize(x)


def test_stale_and_missing_effective_date_fail_closed():
    x=data()
    dates=["2024-03-18","2024-03-19","2024-04-08"]
    with pytest.raises(ValueError,match="EFFR_SOURCE_STALE"):
        rate_schedule(dates,x)
    y=data()
    y["observations"]=[]
    with pytest.raises(ValueError,match="EFFR_OBSERVATIONS_MISSING"):
        normalize(y)


def test_percent_units_and_duplicate_history_rejected():
    x=data()
    x["observations"][1]["rate_percent"]=531.
    with pytest.raises(ValueError,match="EFFR_PERCENT_UNITS_INVALID"):
        normalize(x)
    x=data()
    x["observations"].append(dict(x["observations"][0]))
    with pytest.raises(ValueError,match="EFFR_DUPLICATE"):
        normalize(x)
