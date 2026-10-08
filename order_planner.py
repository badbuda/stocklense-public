from __future__ import annotations
from broker_adapter import OrderIntent
def desired_orders(current:dict[str,int],target:dict[str,int],session:str,target_leverage:float):
 orders=[]
 for symbol in sorted(set(current)|set(target)):
  delta=int(target.get(symbol,0))-int(current.get(symbol,0))
  if delta:
   orders.append(OrderIntent(session,symbol,"BUY" if delta>0 else "SELL",abs(delta),"TARGET_REBALANCE",target_leverage))
 return sorted(orders,key=lambda x:(0 if x.side=="SELL" else 1,x.symbol))
