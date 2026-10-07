from __future__ import annotations
import json
from pathlib import Path

REF=Path("governance/qc_724_order_golden_master.json")

def verify_reference():
    r=json.loads(REF.read_text())
    problems=[]
    if r["order_count"]!=345: problems.append("ORDER_COUNT")
    if r["canonical_sha256"]!="18c4a56de1959027d30cdd10fe5d3c270caf819f8809e09fae366d7a99d55267": problems.append("ORDER_SHA")
    if r["tag_counts"]!={"SL724_ADD_OPEN2":222,"SL724_REDUCE_OPEN1":123}: problems.append("TAG_COUNTS")
    if r["direction_counts"]!={"0":222,"1":123}: problems.append("DIRECTION_COUNTS")
    if r["status_counts"]!={"3":345}: problems.append("STATUS_COUNTS")
    if r["symbol_counts"]!={"TQQQ":251,"QQQ":87,"QLD":7}: problems.append("SYMBOL_COUNTS")
    if r["first_order"]["tag"]!="SL724_ADD_OPEN2" or r["last_order"]["id"]!=345: problems.append("BOUNDARY_ORDERS")
    if problems: raise SystemExit("QC_ORDER_GOLDEN_MASTER_FAIL:"+",".join(problems))
    return {"status":"PASS","order_count":345,"canonical_sha256":r["canonical_sha256"]}

if __name__=="__main__":
    print(json.dumps(verify_reference(),indent=2))
