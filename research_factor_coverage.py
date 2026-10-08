from __future__ import annotations
def factor_coverage(rows,factor,start=None,end=None):
    scoped=[r for r in rows if (not start or r.get("date","")>=start) and (not end or r.get("date","")<=end)]
    present=[r for r in scoped if r.get(factor) is not None]
    n=len(scoped);p=len(present);ratio=p/n if n else 0.0
    return {"factor":factor,"sessions":n,"available_sessions":p,"coverage_ratio":ratio,"first_available":present[0]["date"] if present else None,"last_available":present[-1]["date"] if present else None,"status":"SUFFICIENT" if ratio>=0.95 and n else "INSUFFICIENT"}
def validate_required_factors(rows,factors,start=None,end=None):
    reports=[factor_coverage(rows,f,start,end) for f in factors]
    return {"status":"PASS" if all(x["status"]=="SUFFICIENT" for x in reports) else "BLOCK","factors":reports,"rule":"Research factors require >=95% coverage in selected window."}
