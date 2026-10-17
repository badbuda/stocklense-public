from datetime import date,timedelta
import csv,io
import pytest
from independent_alpaca_evidence import collect,DATA_URL

END="2009-10-02"
def samples():
    d=date(2008,1,2)
    out=[]
    while d.isoformat()<=END:
        if d.weekday()<5:
            out.append({"t":d.isoformat()+"T14:30:00Z","c":100.0+len(out)*0.01})
        d+=timedelta(days=1)
    return out

def loader(*, barlist=None, badpage=None):
    bars=barlist if barlist is not None else samples()
    def load(params):
        if badpage is not None:return badpage
        n=int(params.get("page_token", "0"))
        assert params["adjustment"]=="all"
        assert params["timeframe"]=="1Day"
        assert params["feed"] in ("sip","iex")
        assert params["start"]=="2008-01-01"
        assert params["limit"]==10000
        return {"bars":bars[n:n+200],
                "next_page_token":str(n+200) if n+200<len(bars) else None}
    return load

def test_really_paginates_and_outputs_canonical_vendor_csv():
    payload,manifest=collect(session=END,feed="sip",load_page=loader())
    records=list(csv.DictReader(io.StringIO(payload.decode())))
    assert len(records)>300
    assert records[-1]["Date"]==END
    assert records[0]["Date"]=="2008-01-02"
    assert manifest["page_count"]>=2
    assert manifest["full_policy_parity_verified"] is False
    assert manifest["cutover_authorized"] is False
    assert manifest["broker_actions"] is False
    assert DATA_URL.startswith("https://data.alpaca.markets/")
    assert b"Date,Close" in payload
    assert "adjustment" not in records[0]

def test_vendor_truncation_missing_last_or_warmup_fails_closed():
    rows=samples()
    for bars in (rows[:-1],rows[-150:]):
        with pytest.raises(ValueError,match="INCOMPLETE|WARMUP"):
            collect(session=END,feed="sip",load_page=loader(barlist=bars))

def test_vendor_duplicate_or_unadjusted_bad_prices_never_patched():
    rows=samples()
    with pytest.raises(ValueError,match="DUPLICATE"):
        collect(session=END,feed="sip",load_page=loader(barlist=rows+[rows[-1]]))
    rows[3]["c"]=float("nan")
    with pytest.raises(ValueError,match="INVALID_ADJUSTED_CLOSE"):
        collect(session=END,feed="sip",load_page=loader(barlist=rows))

def test_unknown_feed_and_malformed_pages_are_blocked():
    with pytest.raises(ValueError,match="EXPLICIT_FEED"):
        collect(session=END,feed="yahoo",load_page=loader())
    with pytest.raises(ValueError,match="NOT_HISTORICAL_DAILY"):
        collect(session=END,feed="sip",load_page=loader(badpage={"bars":None}))

def test_repeated_pagination_token_is_refused():
    def same(params):
        return {"bars":[],"next_page_token":"same"}
    with pytest.raises(ValueError,match="PAGINATION"):
        collect(session=END,feed="sip",load_page=same)
