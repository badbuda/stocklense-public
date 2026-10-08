from __future__ import annotations
from dataclasses import dataclass,asdict
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from json_artifacts import write_json_atomic

class OrderStatus(str,Enum):
 PLANNED="PLANNED";AUTHORIZED="AUTHORIZED";SUBMITTED="SUBMITTED";ACKNOWLEDGED="ACKNOWLEDGED";PARTIAL="PARTIAL";FILLED="FILLED";REJECTED="REJECTED";CANCELLED="CANCELLED"
ALLOWED={
 OrderStatus.PLANNED:{OrderStatus.AUTHORIZED,OrderStatus.CANCELLED},
 OrderStatus.AUTHORIZED:{OrderStatus.SUBMITTED,OrderStatus.CANCELLED},
 OrderStatus.SUBMITTED:{OrderStatus.ACKNOWLEDGED,OrderStatus.REJECTED},
 OrderStatus.ACKNOWLEDGED:{OrderStatus.PARTIAL,OrderStatus.FILLED,OrderStatus.REJECTED,OrderStatus.CANCELLED},
 OrderStatus.PARTIAL:{OrderStatus.PARTIAL,OrderStatus.FILLED,OrderStatus.CANCELLED},
 OrderStatus.FILLED:set(),OrderStatus.REJECTED:set(),OrderStatus.CANCELLED:set()}
@dataclass(frozen=True)
class OrderRecord:
 order_id:str;idempotency_key:str;session:str;symbol:str;side:str;quantity:int;status:str;broker_order_id:str|None=None;filled_quantity:int=0
def make_order(session,symbol,side,quantity,idempotency_key):
 oid=sha256(f"{session}|{idempotency_key}".encode()).hexdigest()[:20]
 return OrderRecord(oid,idempotency_key,session,symbol,side,int(quantity),OrderStatus.PLANNED.value)
def transition(record:OrderRecord,new_status:OrderStatus,broker_order_id=None,filled_quantity=None):
 old=OrderStatus(record.status)
 if new_status not in ALLOWED[old]:raise ValueError(f"INVALID_ORDER_TRANSITION:{old.value}->{new_status.value}")
 fq=record.filled_quantity if filled_quantity is None else int(filled_quantity)
 if fq<0 or fq>record.quantity:raise ValueError("INVALID_FILLED_QUANTITY")
 return OrderRecord(**{**asdict(record),"status":new_status.value,"broker_order_id":broker_order_id or record.broker_order_id,"filled_quantity":fq})
def save(records,out="shadow_history/order_state.json"):
 keys=[r.idempotency_key for r in records]
 if len(keys)!=len(set(keys)):raise ValueError("DUPLICATE_ORDER_INTENT")
 payload={"schema_version":1,"status":"ACTIVE" if records else "NO_ORDERS","live_submission_authorized":False,"orders":[asdict(r) for r in records]}
 write_json_atomic(out,payload);return payload
