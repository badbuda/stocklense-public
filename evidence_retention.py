from pathlib import Path

ROOTS=[Path("shadow_history"),Path("paper_portfolio"),Path("historical_replay")]
EXTRA=[Path("docs/data.json")]
MAX_FILE=5*1024*1024
MAX_TOTAL=20*1024*1024

def files():
    out=[]
    for root in ROOTS:
        if root.exists():
            out.extend(p for p in root.rglob("*") if p.is_file())
    out.extend(p for p in EXTRA if p.is_file())
    return out

def validate():
    fs=files()
    oversized=[(str(p),p.stat().st_size) for p in fs if p.stat().st_size>MAX_FILE]
    total=sum(p.stat().st_size for p in fs)
    if oversized:
        raise SystemExit("EVIDENCE_FILE_BUDGET_EXCEEDED:"+",".join(f"{p}:{n}" for p,n in oversized))
    if total>MAX_TOTAL:
        raise SystemExit(f"EVIDENCE_TOTAL_BUDGET_EXCEEDED:{total}>{MAX_TOTAL}")
    print(f"EVIDENCE_RETENTION=PASS files={len(fs)} bytes={total} max_file={MAX_FILE} max_total={MAX_TOTAL}")

if __name__=="__main__":
    validate()
