"""Independent feed can diagnose policy, but cannot self-authorize deployment."""
import csv, io
from datetime import date,timedelta
import pytest
from infra.aws.second_vendor_parity import audit,PROVIDER

def demo():
    d=date(2008,1,2);rows=[]
    while d<=date(2009,10,2):
        if d.weekday()<5:
            rows.append((d.isoformat(),100+len(rows)*0.03))
        d+=timedelta(days=1)
    buf=io.StringIO()
    w=csv.writer(buf,lineterminator="\n")
    w.writerow(["Date","Close"])
    w.writerows(rows)
    return buf.getvalue().encode(),rows[-1][0]

def verify(frozen,independent,last):
    return audit(frozen_csv=frozen,independent_csv=independent,
                 expected_session=last,vendor=PROVIDER,
                 adjustment="all",licensed_asof=last)

def test_exact_independent_source_still_does_not_authorize_live():
    data,last=demo()
    result=verify(data,data,last)
    assert result["status"]=="SECOND_VENDOR_POLICY_DIAGNOSTIC_MATCH"
    assert result["policy_disagreement_count"]==0
    assert result["second_provider_proven"] is False
    assert result["production_cutover_approved"] is False
    assert result["broker_actions"] is False
    assert result["source_adjustment_reconciled"] is False

def test_incompatible_semantics_and_corrupt_history_fail_closed():
    data,last=demo()
    with pytest.raises(ValueError,match="REQUIRE_INDEPENDENT"):
        audit(frozen_csv=data,independent_csv=data,expected_session=last,
              vendor="YAHOO_FINANCE",adjustment="all",licensed_asof=last)
    with pytest.raises(ValueError,match="INCOMPLETE"):
        verify(data,data.replace(last.encode(),b"2009-10-03"),last)

def test_independent_calendar_mismatch_is_not_waived():
    data,last=demo()
    damaged=data.replace(b"2008-01-03",b"2008-01-04")
    # A duplicate session should fail input integrity, never appear as parity.
    with pytest.raises(ValueError,match="DUPLICATE"):
        verify(data,damaged,last)
