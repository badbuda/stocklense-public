"""StockLens research-only TQQQ cash-secured put quote/ledger primitives.

Not a complete options strategy or real-trade claim. Provides strict ingestion
for licensed historical Cboe 15:45 options quotes and deterministic position
accounting, including short puts, cash collateral, assignment, rolling and
separately funded long protective puts. Test fixtures are SYNTHETIC unit tests.

The source signal must be available before quote_time; no fills from a quote
recorded after the strategy's decision timestamp. No live order adapter,
automatic strategy promotion or broker integration exists here.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Optional
import csv
import json
import re
import sys

D = lambda v: Decimal(str(v))
ALLOWED_TYPES = {"P", "C"}

def canonical_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())

def _field(row: dict, *alternatives: str) -> str:
    for n in alternatives:
        v = row.get(canonical_header(n))
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    raise ValueError("MISSING_MANDATORY_OPTION_FIELD:" + "/".join(alternatives))

@dataclass(frozen=True)
class Quote:
    underlying: str
    quote_date: str
    expiration: str
    strike: Decimal
    right: str
    bid: Decimal
    ask: Decimal
    bid_size: int
    ask_size: int
    open_interest: int
    multiplier: int = 100
    quote_clock: str = "15:45:00"
    contract_adjustment_verified: bool = False
    source: str = "CBOE_EOD_1545"
    root: str = "TQQQ"

    @property
    def key(self):
        return (self.root, self.expiration, self.strike, self.right, self.multiplier)

    def validate(self):
        if self.underlying != "TQQQ" or self.root != "TQQQ":
            raise ValueError("WRONG_UNDERLYING_OR_ADJUSTED_ROOT")
        qday = date.fromisoformat(self.quote_date)
        xday = date.fromisoformat(self.expiration)
        if xday <= qday:
            raise ValueError("EXPIRED_OPTION_QUOTE")
        if self.right not in ALLOWED_TYPES:
            raise ValueError("BAD_OPTION_TYPE")
        if self.strike <= 0 or self.bid < 0 or self.ask < self.bid or self.ask == 0:
            raise ValueError("CROSSED_OR_INVALID_NBBO")
        if self.bid_size <= 0 or self.ask_size <= 0 or self.open_interest < 1:
            raise ValueError("UNTRADEABLE_OR_NO_LIQUIDITY")
        if self.multiplier != 100 or not self.contract_adjustment_verified:
            raise ValueError("UNVERIFIED_OPTION_DELIVERABLE_OR_MULTIPLIER")
        time.fromisoformat(self.quote_clock)
        if self.quote_clock != "15:45:00" or self.source != "CBOE_EOD_1545":
            raise ValueError("UNAPPROVED_QUOTE_SNAPSHOT_OR_SOURCE")

def import_cboe_csv(path: str, *, adjustment_verified: bool = False):
    """Do not set adjustment_verified=True without independently verifying
    dated TQQQ splits, OCC contract adjustments and option root deliverables.
    """
    rows = []
    with Path(path).open(newline="", encoding="utf-8-sig") as file:
        reader=csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError("EMPTY_OPTION_CHAIN")
        for index, raw in enumerate(reader):
            if not any(raw.values()):
                continue
            row={canonical_header(k):v for k,v in raw.items() if k is not None}
            if _field(row, "Underlying Symbol") != "TQQQ":
                continue
            option_type=_field(row, "Option Type").upper()
            right={"PUT":"P","CALL":"C","P":"P","C":"C"}.get(option_type)
            if not right:
                raise ValueError("UNKNOWN_OPTION_RIGHT")
            root=_field(row,"Root")
            quote=Quote(
                underlying="TQQQ",
                root=root,
                quote_date=_field(row,"Quote Date"),
                expiration=_field(row,"Expiration"),
                strike=D(_field(row,"Strike")),
                right=right,
                bid=D(_field(row,"Bid 1545")),
                ask=D(_field(row,"Ask 1545")),
                bid_size=int(_field(row,"Bid Size 1545")),
                ask_size=int(_field(row,"Ask Size 1545")),
                open_interest=int(_field(row,"Open Interest")),
                contract_adjustment_verified=adjustment_verified
            )
            quote.validate()
            rows.append(quote)
    if not rows:
        raise ValueError("NO_VERIFIED_TQQQ_CONTRACTS")
    signature=set()
    for q in rows:
        key=(q.quote_date,q.key)
        if key in signature:
            raise ValueError("DUPLICATE_QUOTE_SERIES")
        signature.add(key)
    return rows

@dataclass
class CashSecuredPutLedger:
    cash: Decimal
    max_reserved_fraction: Decimal = field(default_factory=lambda:D(".15"))
    fee_per_contract: Decimal = field(default_factory=lambda:D("0"))
    minimum_order_fee: Decimal = field(default_factory=lambda:D("0"))
    shares: int = 0
    short_puts: dict = field(default_factory=dict)
    protective_puts: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    last_date: Optional[str] = None

    def __post_init__(self):
        self.cash=D(self.cash);self.max_reserved_fraction=D(self.max_reserved_fraction)
        self.fee_per_contract=D(self.fee_per_contract)
        self.minimum_order_fee=D(self.minimum_order_fee)
        if self.cash<=0 or not 0<self.max_reserved_fraction<=1:
            raise ValueError("INVALID_CAPITAL_OR_CSP_SLEEVE")
        if self.fee_per_contract<0 or self.minimum_order_fee<0:
            raise ValueError("BAD_BROKER_FEE_SCHEDULE")

    def _ticket_fee(self,n:int):
        return max(self.minimum_order_fee,self.fee_per_contract*n) if n>0 else D(0)

    def _check(self, q: Quote):
        q.validate()
        if self.last_date is not None and q.quote_date<self.last_date:
            raise ValueError("BACKDATED_ORDER")

    def locked_cash(self):
        return sum((k[2]*k[4]*n for k,n in self.short_puts.items()),D(0))

    def free_cash(self):
        return self.cash-self.locked_cash()

    def _record(self,operation,q,n,amount,event_date=None):
        when=event_date or q.quote_date
        if self.last_date is not None and when<self.last_date:
            raise ValueError("BACKDATED_RECORD")
        self.last_date=when
        self.events.append({"date":when,"operation":operation,
                            "contract":str(q.key),"contracts":n,
                            "cash_delta":str(amount),"cash":str(self.cash),
                            "reserved_cash":str(self.locked_cash())})

    def sell_put(self,q: Quote,n: int,*,stocklens_target: float,
                 mark_underlying: Decimal):
        self._check(q)
        if q.right!="P" or not isinstance(n,int) or n<=0:
            raise ValueError("PUT_SELL_INVALID")
        if stocklens_target not in (0, 1.25, 2, 3):
            raise ValueError("UNRECOGNIZED_STOCKLENS_EXPOSURE")
        if stocklens_target==0:
            raise ValueError("STOCKLENS_CASH_REGIME_PUT_SELL_BLOCKED")
        # A short-put sleeve uses capital *already held in this ledger*,
        # never implicitly creates leverage on top of frozen risk-on equity.
        reserve=q.strike*q.multiplier*n
        if reserve>self.free_cash():
            raise ValueError("INSUFFICIENT_COLLATERAL")
        if reserve+self.locked_cash()>D(mark_underlying)*self.shares*self.max_reserved_fraction + self.cash*self.max_reserved_fraction:
            raise ValueError("MAX_CASH_SLEEVE_LIMIT")
        # Conservative assumption: sale at observed bid (not at mid).
        # Configurable per-ticket fees: default zero means UNIT TEST ONLY.
        # For real results a verified broker fee schedule is mandatory.
        credit=q.bid*q.multiplier*n-self._ticket_fee(n)
        if credit<=0:
            raise ValueError("NET_PREMIUM_AFTER_FEES_NONPOSITIVE")
        self.cash+=credit
        self.short_puts[q.key]=self.short_puts.get(q.key,0)+n
        self._record("SELL_PUT_AT_BID",q,n,credit)
        return credit

    def buy_to_close_put(self,q:Quote,n:int):
        self._check(q)
        held=self.short_puts.get(q.key,0)
        if q.right!="P" or not isinstance(n,int) or n<=0 or n>held:
            raise ValueError("SHORT_PUT_NOT_HELD")
        debit=q.ask*q.multiplier*n+self._ticket_fee(n)
        if debit>self.cash:
            raise ValueError("INSUFFICIENT_CASH_FOR_ASK_CLOSE")
        self.cash-=debit
        if n==held:self.short_puts.pop(q.key)
        else:self.short_puts[q.key]=held-n
        self._record("BUY_TO_CLOSE_AT_ASK",q,n,-debit)
        return debit

    def roll_down_out(self,q_close:Quote,q_open:Quote,n:int,
                      *,stocklens_target:float,mark_underlying:Decimal):
        import copy
        if q_close.quote_date!=q_open.quote_date or q_open.expiration<=q_close.expiration:
            raise ValueError("ROLL_REQUIRES_SAME_DATE_AND_LATER_EXPIRY")
        if q_open.strike>q_close.strike:
            raise ValueError("ROLL_DOWN_OUT_MUST_NOT_RAISE_STRIKE")
        copy_book=copy.deepcopy(self)
        paid=copy_book.buy_to_close_put(q_close,n)
        collected=copy_book.sell_put(q_open,n,stocklens_target=stocklens_target,mark_underlying=mark_underlying)
        # Explicit real net CREDIT OR DEBIT; a roll never erases closed losses.
        self.__dict__.update(copy_book.__dict__)
        return {"close_at_ask":paid,"new_sale_at_bid":collected,
                "net_cash_credit":collected-paid}

    def buy_protection(self,q:Quote,n:int):
        self._check(q)
        if q.right!="P" or not isinstance(n,int) or n<=0:
            raise ValueError("LONG_PUT_INVALID")
        debit=q.ask*q.multiplier*n+self._ticket_fee(n)
        if debit>self.free_cash():
            raise ValueError("PROTECTIVE_PUT_UNFUNDED")
        self.cash-=debit
        self.protective_puts[q.key]=self.protective_puts.get(q.key,0)+n
        self._record("BUY_LONG_PUT_AT_ASK",q,n,-debit)
        return debit

    def expire_short_put_at_close(self,q:Quote,underlying_close:Decimal,n:int,settlement_date:str):
        """Simplified expiry assignment only (NOT early American assignment)."""
        q.validate()
        if settlement_date != q.expiration or (self.last_date and settlement_date < self.last_date):
            raise ValueError("EXPLICIT_EXPIRY_DATE_REQUIRED")
        if self.short_puts.get(q.key,0)<n or n<=0:
            raise ValueError("NO_SUCH_SHORT_PUT")
        if D(underlying_close)<q.strike:
            assignment=q.strike*q.multiplier*n
            if self.cash<assignment:
                raise ValueError("ASSIGNMENT_CASH_SHORTFALL")
            self.cash-=assignment
            self.shares+=q.multiplier*n
            event="ASSIGNED_100_SHARES_PER_CONTRACT"
            cash_change=-assignment
        else:
            cash_change=D(0);event="EXPIRED_OUT_OF_MONEY"
        self.short_puts[q.key]-=n
        if self.short_puts[q.key]==0:self.short_puts.pop(q.key)
        self._record(event,q,n,cash_change,event_date=settlement_date)

    def mark_equity(self,underlying,option_quotes,asof_date):
        if self.last_date and asof_date < self.last_date:
            raise ValueError("BACKDATED_MARK")
        price=D(underlying)
        if price<=0:
            raise ValueError("BAD_MARK_UNDERLYING")
        eq=self.cash+self.shares*price
        for key,n in self.short_puts.items():
            if key not in option_quotes:
                raise ValueError("MISSING_SHORT_POSITION_MARK_QUOTE")
            q=option_quotes[key];q.validate()
            if q.quote_date != asof_date:
                raise ValueError("STALE_SHORT_OPTION_MARK")
            eq-=q.ask*q.multiplier*n  # conservative liability, avoid mid
        for key,n in self.protective_puts.items():
            if key not in option_quotes:
                raise ValueError("MISSING_LONG_HEDGE_MARK_QUOTE")
            q=option_quotes[key];q.validate()
            if q.quote_date != asof_date:
                raise ValueError("STALE_LONG_OPTION_MARK")
            eq+=q.bid*q.multiplier*n
        return eq

if __name__=="__main__":
    print(json.dumps({
        "status":"RESEARCH_ONLY_CONTRACT_ENGINE_READY",
        "historical_option_data_loaded":False,
        "historical_option_returns_computed":False,
        "automatic_promotion":False,
        "requires":"Licensed historical NBBO plus split-reviewed OCC contracts and complete time series.",
        "hard_safety_limits":["no stocklens 0x short puts","15% max cash sleeve default",
         "strict cash collateral","executable bid sale/ask close","configurable ticket fees","long puts funded",
         "missing marks fail closed","expiry assignment not early assignment"]
    },indent=2))
