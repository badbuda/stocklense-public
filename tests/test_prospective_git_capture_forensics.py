"""Illustrative fixtures are not historic investment results."""
import copy, pytest
from prospective_git_capture_forensics import evaluate,blob_sha

def fixture():
    csv="asof_date,strategy_return,baseline_return,strategy_exposure,baseline_exposure\n"
    d=["2026-10-07","2026-10-08","2026-10-09"];s=[]
    times=["2026-10-08T09:29:31Z","2026-10-09T04:36:29Z","2026-10-10T02:32:14Z"]
    for i,x in enumerate(d):
        csv+=f"{x},0.01,0.01,3,3\n"
        s.append({"commit_sha":f"{i+1:040x}","git_blob_sha":blob_sha(csv.encode()),
                  "author_date_utc":times[i],"dates":d[:i+1]})
    e={"schema_version":1,"experiment_id":"SL9-007-UPSHIFT-CONFIRMATION",
       "independently_verified_first_seen":False,"snapshots":s}
    r={"candidates":[{"experiment_id":"SL9-007-UPSHIFT-CONFIRMATION",
         "inception_date":"2026-09-26"}],
       "last_ingestion_audit":[{"experiment_id":"SL9-007-UPSHIFT-CONFIRMATION",
         "persisted_prospective_rows":3,"definition_matches_registration":True,
         "fingerprint_matches_registration":False}]}
    return csv.encode(),e,r

def run(x=None):
    a,e,r=fixture()
    return evaluate(a,e,r,"qret*lev","q*candidate")

def test_0_independent_but_three_plausible_git_author_dates():
    x=run()
    assert (x["original_modelled_rows_retained"],x["git_author_timing_plausible_rows_NOT_PROVEN"])==(3,3)
    assert x["independently_verified_forward_trading_rows"]==0
    assert x["real_tqqq_used_in_source_return_calculation"] is False

def test_late_authored_first_appearance():
    a,e,r=fixture()
    e["snapshots"][0]["author_date_utc"]="2026-10-08T22:00:00Z"
    assert evaluate(a,e,r,"qret*lev","q*candidate")["git_author_timing_late_rows"]==1

def test_modification_breaks_git_blob_parity():
    a,e,r=fixture()
    with pytest.raises(ValueError,match="GIT_LATEST_LEDGER_BLOB_MISMATCH"):
        evaluate(a.replace(b"0.01",b"0.02",1),e,r,"qret*lev","q*candidate")

def test_missing_last_day_cannot_promote():
    a,e,r=fixture();e["snapshots"][-1]["dates"].pop()
    with pytest.raises(ValueError,match="GIT_SOURCE_HISTORY_INVALID"):
        evaluate(a,e,r,"qret*lev","q*candidate")

def test_self_attested_capture_rejected():
    a,e,r=fixture();e["independently_verified_first_seen"]=True
    with pytest.raises(ValueError,match="GIT_METADATA_NOT_INDEPENDENT_CAPTURE"):
        evaluate(a,e,r,"qret*lev","q*candidate")

def test_approximation_source_change_rejected():
    a,e,r=fixture()
    with pytest.raises(ValueError,match="FORWARD_APPROXIMATE_QQQ_LEVERAGE_BASIS_CHANGED"):
        evaluate(a,e,r,"actual ETF fills","real 3x","yes")

def test_definition_drift_rejected():
    a,e,r=fixture();r["last_ingestion_audit"][0]["definition_matches_registration"]=False
    with pytest.raises(ValueError,match="FORWARD_REGISTRATION_LINEAGE_CHANGED"):
        evaluate(a,e,r,"qret*lev","q*candidate")
