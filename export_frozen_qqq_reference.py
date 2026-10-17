"""Export the EXACT frozen StockLens yfinance-auto-adjusted QQQ reference.

No positions or orders. Side-by-side comparison with independent Alpaca feed
requires identical historical calendar; no substitutions if Yahoo is stale.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,os
from pathlib import Path

def reference_csv(frame,audit,session):
    if audit.get("source")!="YFINANCE_QQQ_AUTO_ADJUSTED":
        raise ValueError("FROZEN_YFINANCE_SOURCE_NOT_PROVEN")
    dates=[v.date().isoformat() for v in frame["Date"]]
    close=[float(v) for v in frame["Close"]]
    if not dates or dates[0]>"2008-01-10" or dates[-1]!=session or dates!=sorted(set(dates)):
        raise ValueError("FROZEN_REFERENCE_CALENDAR_NOT_COMPLETE")
    if any(not math.isfinite(x) or x<=0 for x in close):
        raise ValueError("FROZEN_REFERENCE_INVALID_CLOSE")
    w=io.StringIO(newline="")
    writer=csv.writer(w,lineterminator="\n")
    writer.writerow(["Date","Close"])
    for d,x in zip(dates,close):writer.writerow([d,format(x,".17g")])
    data=w.getvalue().encode("utf-8")
    return data,{"source":"FROZEN_YFINANCE_AUTO_ADJUSTED_QQQ",
                 "last_session":session,"rows":len(dates),
                 "sha256":hashlib.sha256(data).hexdigest(),
                 "independent_vendor_proven":False,"broker_actions":False}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    from stocklens.data import load_qqq_history
    frame,audit=load_qqq_history()
    data,report=reference_csv(frame,audit,args.session)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    flags=os.O_WRONLY|os.O_EXCL|os.O_CREAT
    if hasattr(os,"O_NOFOLLOW"):flags|=os.O_NOFOLLOW
    descriptor=os.open(args.output,flags,0o600)
    with os.fdopen(descriptor,"wb") as handle:handle.write(data)
    print(json.dumps({**report,"output":str(args.output)},sort_keys=True))

if __name__=="__main__":
    main()
