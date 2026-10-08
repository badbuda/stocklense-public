from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class Position:
 symbol:str;quantity:int
def reconcile(expected:list[Position],actual:list[Position]):
 e={x.symbol:x.quantity for x in expected};a={x.symbol:x.quantity for x in actual};symbols=sorted(set(e)|set(a))
 diffs=[{"symbol":s,"expected":e.get(s,0),"actual":a.get(s,0),"delta":a.get(s,0)-e.get(s,0)} for s in symbols if e.get(s,0)!=a.get(s,0)]
 return {"status":"MATCH" if not diffs else "MISMATCH","differences":diffs,"live_gate_eligible":not diffs}
