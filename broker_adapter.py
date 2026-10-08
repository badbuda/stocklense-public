from __future__ import annotations
from dataclasses import dataclass,asdict
from enum import Enum
from hashlib import sha256
import json
from typing import Protocol,Any

class BrokerMode(str,Enum):
 DISABLED="DISABLED";READ_ONLY="READ_ONLY";PAPER="PAPER";LIVE="LIVE"

@dataclass(frozen=True)
class OrderIntent:
 session:str;symbol:str;side:str;quantity:int;reason:str;target_leverage:float
 @property
 def idempotency_key(self)->str:
  raw=f"{self.session}|{self.symbol}|{self.side}|{self.quantity}|{self.target_leverage:.8f}"
  return sha256(raw.encode()).hexdigest()

class BrokerAdapter(Protocol):
 mode:BrokerMode
 def account_snapshot(self)->dict[str,Any]: ...
 def positions(self)->list[dict[str,Any]]: ...
 def preview(self,intent:OrderIntent)->dict[str,Any]: ...
 def submit(self,intent:OrderIntent)->dict[str,Any]: ...

class DisabledBroker:
 mode=BrokerMode.DISABLED
 def account_snapshot(self): return {"mode":self.mode,"status":"DISABLED"}
 def positions(self): return []
 def preview(self,intent): return {"allowed":False,"mode":self.mode,"intent":asdict(intent),"idempotency_key":intent.idempotency_key}
 def submit(self,intent): raise RuntimeError("LIVE_ORDER_BLOCKED:BROKER_DISABLED")

class ReadOnlyBroker(DisabledBroker):
 mode=BrokerMode.READ_ONLY
 def submit(self,intent): raise RuntimeError("LIVE_ORDER_BLOCKED:READ_ONLY")

def assert_live_gate(mode:BrokerMode,explicit_live_enabled:bool,reconciled:bool)->None:
 if mode is not BrokerMode.LIVE: raise RuntimeError("LIVE_ORDER_BLOCKED:MODE")
 if not explicit_live_enabled: raise RuntimeError("LIVE_ORDER_BLOCKED:EXPLICIT_GATE")
 if not reconciled: raise RuntimeError("LIVE_ORDER_BLOCKED:ACCOUNT_NOT_RECONCILED")

def serialize_intent(intent:OrderIntent)->str:
 return json.dumps({**asdict(intent),"idempotency_key":intent.idempotency_key},sort_keys=True)
