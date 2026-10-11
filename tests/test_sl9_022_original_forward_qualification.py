import csv
import io
import math
import pytest
from sl9_022_original_forward_qualification import audit, FIELDS, EID


def samples(different=False):
    rows=[]
    for i in range(10):
        ds=["2026-09-28","2026-09-29","2026-09-30","2026-10-01",
            "2026-10-02","2026-10-05","2026-10-06","2026-10-07",
            "2026-10-08","2026-10-09"][i]
        rows.append(dict(zip(FIELDS,[ds,0.005+(0.01 if different and i==5 else 0),
            0.005,3.,3.])))
    b=io.StringIO()
    w=csv.DictWriter(b,fieldnames=list(FIELDS));w.writeheader();w.writerows(rows)
    reg={"candidates":[{"experiment_id":EID}],
         "last_ingestion_audit":[{"experiment_id":EID,
            "persisted_prospective_rows":10,
            "definition_matches_registration":True,
            "fingerprint_matches_registration":False}]}
    git={"experiment_id":EID,"independently_verified_first_seen":False,
         "snapshots":[{"dates":list(r["asof_date"] for r in rows[:8])},
                      {"dates":list(r["asof_date"] for r in rows[:9])},
                      {"dates":list(r["asof_date"] for r in rows)}]}
    return b.getvalue().encode(),reg,git,"x=qret*lev;baseline_return=x","strategy_return=q*candidate"


def test_legacy_proxy_never_qualifies_even_if_one_challenger_differs():
    args=samples(different=True)
    x=audit(*args)
    assert x["economically_distinguishing_sessions"]==1
    assert x["qualified_forward_paired_sessions"]==0
    assert x["return_basis"]=="PROXY_NOT_ETF"
    assert x["independently_verified_forward_observed_real_etf_sessions"]==0
    assert not x["live_broker_trading_authorized"]


def test_tiny_float_noise_not_distinguishing():
    args=list(samples())
    src=args[0].decode().replace("0.005,0.005,3.0,3.0",
                                 "0.0050000000000001,0.005,3.0,3.0",1)
    args[0]=src.encode()
    x=audit(*args)
    assert x["economically_distinguishing_sessions"]==0
    assert x["max_abs_return_difference"]<1e-12


def test_mutated_registration_fails_closed():
    args=list(samples())
    args[1]["last_ingestion_audit"][0]["definition_matches_registration"]=False
    with pytest.raises(ValueError,match="SL9_007_LINEAGE"):
        audit(*args)


def test_original_csv_change_fails_closed():
    args=list(samples())
    args[0]=args[0].replace(b"2026-10-09",b"2026-10-12")
    with pytest.raises(ValueError,match="SL9_007_COHORT_CALENDAR"):
        audit(*args)


def test_source_return_formula_mutation_requires_new_proof():
    args=list(samples())
    args[3]="actual_tqqq_adjusted_ohlc_not_qqq_approx"
    with pytest.raises(ValueError,match="SL9_007_RETURN_SOURCE_CHANGED"):
        audit(*args)
