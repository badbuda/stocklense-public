"""Public allowlist for fixed $100k ST demo only; no raw private evidence."""
import datetime as dt
import json
import math
import time
from infra.aws import epoch5_portal_reader as private

ROUTE = "GET /v1/public-model"
KIND = "STOCKLENS_PUBLIC_MODELED_EPOCH5_V1"
ACTIONS = {"NO_CHANGE", "REBALANCE_NEXT_SESSION", "ENTER_CASH_NEXT_SESSION",
           "EXIT_CASH_NEXT_SESSION", "BOOTSTRAP_TO_TARGET", "RECONCILE_ACTUAL_HOLDINGS"}
CACHE = None


def days(now):
    day = now.date()
    result = []
    while len(result) < 14:
        if day.weekday() < 5:
            result.append(day.isoformat())
        day -= dt.timedelta(days=1)
    return sorted(result)


def public_signal(s):
    if not s:
        return None
    return {"session_date": s["session_date"], "level": s["level"],
            "target_leverage": s["target_leverage"],
            "action": s.get("action") if s.get("action") in ACTIONS else None}


def project(s3, dates):
    rows = []
    for x in private.summarize(s3, dates)["sessions"]:
        day, p = x["session_date"], x.get("paper")
        row = {"session_date": day, "signal": public_signal(x.get("signal")),
               "paper_status": x["paper_status"], "paper": None}
        if x.get("signal_error"):
            row["signal_error"] = "UNAVAILABLE"
        if p is not None:
            try:
                g = private.read(s3, private.PREFIX + "genesis.json", receipt=True)
                private.require(g is not None and g[0].get("starting_cash_usd") == 100000
                                and g[0].get("starting_shares") == {"QQQ": 0, "TQQQ": 0}
                                and g[0].get("old_book_transferred") is False, "DEMO_ONLY")
                raw = private.read(s3, private.PREFIX + "sessions/" + day + ".json",
                                   receipt=True, version=p["version_id"])
                private.require(raw is not None and raw[1]["sha256"] == p["sha256"], "PIN")
                trades = []
                for t in raw[0]["trades"]:
                    private.require(t.get("symbol") in ("QQQ", "TQQQ") and t.get("side") in ("BUY", "SELL")
                                    and t.get("execution_session") == day and t.get("time_et") in ("09:31", "09:32")
                                    and type(t.get("qty")) is int and t["qty"] > 0
                                    and type(t.get("modeled_fill_price")) in (int, float)
                                    and math.isfinite(t["modeled_fill_price"]) and t["modeled_fill_price"] > 0,
                                    "TRADE")
                    trades.append({k: t[k] for k in ("symbol", "side", "qty", "modeled_fill_price", "time_et")})
                row["paper"] = {k: p[k] for k in ("equity", "cash", "qqq_shares", "tqqq_shares",
                    "cumulative_fees", "cumulative_slippage_cost", "trade_count", "continuity_status")}
                row["paper"]["execution_signal"] = public_signal(p["execution_signal"])
                row["paper"]["paper_action"] = p.get("paper_action") if p.get("paper_action") in ACTIONS else None
                row["paper"]["trades"] = trades
                row["paper"]["return_from_demo_start"] = p["equity"] / 100000 - 1
            except Exception:
                row["paper_status"] = "INVALID_OR_PARTIAL_EVIDENCE"
                row["paper"] = None
        rows.append(row)
    return {"kind": KIND, "book": private.BOOK, "first_session": private.FIRST,
            "starting_demo_usd": 100000, "broker_orders_authorized": False,
            "broker_fills_observed": False, "independent_second_vendor_verified": False,
            "full_chain_verified": False, "sessions": rows}


def public_handler(event, context):
    global CACHE
    if event.get("routeKey") != ROUTE:
        return {"statusCode": 404, "body": "{}"}
    now = dt.datetime.now(dt.timezone.utc)
    dates = days(now)
    if CACHE is None or CACHE[0] != dates or time.monotonic() - CACHE[1] > 60:
        import boto3
        result = project(boto3.client("s3", region_name="eu-central-1"), dates)
        result["generated_at_utc"] = now.isoformat()
        CACHE = (dates, time.monotonic(), json.dumps(result, allow_nan=False))
    return {"statusCode": 200, "headers": {"content-type": "application/json",
            "cache-control": "public, max-age=30"}, "body": CACHE[2]}
