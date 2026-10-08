from __future__ import annotations
import csv,json
from pathlib import Path
from json_artifacts import write_json_atomic
def _f(x):
    try:return float(x)
    except:return None
def build_forward_path(ledger="paper_portfolio/ledger.csv",out="shadow_history/forward_path.json"):
    p=Path(ledger);rows=list(csv.DictReader(p.open())) if p.exists() else [];points=[];prev_eq=prev_q=None;sl=ql=1.0;sp=qp=1.0;smax=qmax=1.0;smdd=qmdd=0.0
    for r in rows:
        eq,q=_f(r.get("equity")),_f(r.get("qqq_close"))
        sr=eq/prev_eq-1 if eq is not None and prev_eq not in (None,0) else None
        qr=q/prev_q-1 if q is not None and prev_q not in (None,0) else None
        if sr is not None:sp*=1+sr;smax=max(smax,sp);smdd=min(smdd,sp/smax-1)
        if qr is not None:qp*=1+qr;qmax=max(qmax,qp);qmdd=min(qmdd,qp/qmax-1)
        points.append({"session_date":r.get("session_date"),"stocklens_daily_return":sr,"qqq_daily_return":qr,"daily_excess_return":sr-qr if sr is not None and qr is not None else None,"stocklens_index":sp,"qqq_index":qp})
        if eq is not None:prev_eq=eq
        if q is not None:prev_q=q
    result={"status":"ACTIVE" if len(rows)>=2 else "WAITING_FOR_RETURN_PATH","sessions":len(rows),"stocklens_return":sp-1 if len(rows)>=2 else None,"qqq_price_return":qp-1 if len(rows)>=2 else None,"excess_return":sp-qp if len(rows)>=2 else None,"stocklens_max_drawdown":smdd if len(rows)>=2 else None,"qqq_max_drawdown":qmdd if len(rows)>=2 else None,"points":points[-252:],"benchmark_note":"QQQ close-to-close price return from the paper ledger; dividends are not included."}
    write_json_atomic(out,result);return result
if __name__=="__main__":print(json.dumps(build_forward_path(),indent=2))
