"""JWT-only read model for the new ST book. No S3 writes or broker actions."""
import datetime as dt
import hashlib
import json
import math
import re

BOOK = "NEW_AWS_INDEPENDENT_STAGING_BOOK_EPOCH5_20261124"
FIRST = "2026-11-24"
PREFIX = "paper/epochs/" + BOOK + "/"
BUCKET = "stocklens-st-candidatedata-6jj7i9fxjmfr"
MODE = "SHADOW_ONLY_NO_BROKER_ACTIONS"
CONT = "MODELLED_RECEIPT_NOT_INDEPENDENTLY_QUALIFIED"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(s3, key, *, receipt=False, version=None):
    try:
        h = s3.head_object(Bucket=BUCKET, Key=key, **({"VersionId": version} if version else {}))
    except Exception as e:
        code = str(getattr(e, "response", {}).get("Error", {}).get("Code", ""))
        if version is None and code in ("403", "404", "NoSuchKey", "NotFound", "AccessDenied"):
            listing = s3.list_objects_v2(Bucket=BUCKET, Prefix=key, MaxKeys=10)
            if listing.get("IsTruncated") is False and not any(x["Key"] == key for x in listing.get("Contents", [])):
                return None
        raise
    v = h.get("VersionId")
    n = h.get("ContentLength")
    require(isinstance(v, str) and v not in ("", "null") and (version is None or version == v), "VERSION")
    require(type(n) is int and 2 <= n <= 2_000_000, "SIZE")
    r = s3.get_object(Bucket=BUCKET, Key=key, VersionId=v)
    raw = r["Body"].read(2_000_001)
    sha = hashlib.sha256(raw).hexdigest()
    expected = h.get("Metadata", {}).get("sha256")
    require(r.get("VersionId") == v and len(raw) == n and
            (expected == sha if receipt else expected in (None, sha)), "HASH_OR_VERSION")
    obj = json.loads(raw)
    require(type(obj) is dict, "OBJECT")
    return obj, {"key": key, "version_id": v, "sha256": sha, "saved_at_utc": h["LastModified"].isoformat()}


def signal(s3, day, version=None):
    r = read(s3, "signals/" + day + ".json", version=version)
    if r is None:
        return None
    p, meta = r
    latest = p.get("latest", {})
    level, lev = latest.get("level"), latest.get("target_leverage")
    require(p.get("mode") == MODE and p.get("execution_plan", {}).get("broker_actions_enabled") is False
            and latest.get("asof_date") == day and type(level) in (int, float)
            and level in (0, 1, 1.25, 2, 3) and type(lev) in (int, float)
            and math.isfinite(lev) and 0 <= lev <= 3, "SIGNAL_INVALID")
    return {**meta, "session_date": day, "level": level, "target_leverage": lev, "action": p.get("action")}


def paper(s3, day):
    if day < FIRST:
        return None
    p = read(s3, PREFIX + "sessions/" + day + ".json", receipt=True)
    c = read(s3, PREFIX + "continuity/" + day + ".json", receipt=True)
    if p is None and c is None:
        return None
    require(p is not None and c is not None, "PARTIAL_PAIR")
    obj, pm = p
    cont, cm = c
    ev, row, market = cont.get("evidence", {}), obj.get("row", {}), obj.get("market_evidence") or {}
    require(obj.get("book") == BOOK and obj.get("session") == day and obj.get("mode") == MODE
            and obj.get("broker_orders_authorized") is False and obj.get("broker_fills_observed") is False
            and obj.get("state", {}).get("last_mark_session") == day and row.get("session_date") == day
            and cont.get("book") == BOOK and cont.get("session") == day and cont.get("status") == CONT
            and cont.get("broker_orders") is False and cont.get("broker_fills") is False
            and ev.get("paper_key") == pm["key"] and ev.get("paper_sha256") == pm["sha256"]
            and ev.get("paper_version_id") == pm["version_id"]
            and market.get("schema") == "sl63-yahoo-single-vendor-1m-quote-evidence-v1"
            and market.get("single_vendor") == "YFINANCE_1M_RAW" and market.get("synthetic_quotes") is False
            and market.get("independent_second_vendor_verified") is False, "PAIR_INVALID")
    g = read(s3, PREFIX + "genesis.json", receipt=True)
    require(g is not None and g[0].get("book") == BOOK and g[0].get("first_session") == FIRST
            and g[0].get("old_book_transferred") is False and g[0].get("broker_orders_authorized") is False,
            "GENESIS_INVALID")
    pin, prior = obj.get("signal") or {}, row.get("signal_date", "")
    require(isinstance(prior, str) and re.fullmatch(r"20\d\d-\d\d-\d\d", prior)
            and prior < day and pin.get("key") == "signals/" + prior + ".json"
            and isinstance(pin.get("version_id"), str) and pin["version_id"] not in ("", "null"), "SIGNAL_PIN")
    src = signal(s3, prior, pin["version_id"])
    require(src is not None and src["sha256"] == pin.get("sha256") and src["version_id"] == pin["version_id"]
            and src["level"] == row.get("target_level") and src["target_leverage"] == row.get("target_leverage"),
            "SIGNAL_MISMATCH")
    fields = ("equity", "cash", "qqq_shares", "tqqq_shares", "cumulative_fees", "cumulative_slippage_cost")
    require(all(type(row.get(k)) in (int, float) and math.isfinite(row[k]) and row[k] >= 0 for k in fields)
            and row["equity"] > 0, "ACCOUNTING_FIELDS")
    trades = obj.get("trades")
    require(type(trades) is list and len(trades) == row.get("trade_count_session"), "TRADE_COUNT")
    return {**pm, **{k: row[k] for k in fields}, "trade_count": len(trades),
            "paper_action": row.get("paper_action"), "execution_signal": src,
            "continuity_status": CONT, "continuity_sha256": cm["sha256"], "continuity_version_id": cm["version_id"]}


def summarize(s3, dates):
    rows = []
    for day in dates:
        entry = {"session_date": day, "signal": None, "paper": None,
                 "paper_status": "NOT_STARTED" if day < FIRST else "NO_RECEIPT"}
        try:
            entry["signal"] = signal(s3, day)
        except Exception:
            entry["signal_error"] = "INVALID_OR_UNREADABLE_SIGNAL"
        try:
            entry["paper"] = paper(s3, day)
            if entry["paper"]:
                entry["paper_status"] = "SHA_BOUND_SINGLE_VENDOR_MODELED"
        except Exception:
            entry["paper_status"] = "INVALID_OR_PARTIAL_EVIDENCE"
        rows.append(entry)
    return {"kind": "STOCKLENS_EPOCH5_READ_ONLY_V1", "book": BOOK, "first_session": FIRST,
            "broker_orders_authorized": False, "broker_fills_observed": False,
            "independent_second_vendor_verified": False, "full_chain_verified": False, "sessions": rows}


def handler(event, context):
    def response(code, body):
        return {"statusCode": code, "headers": {"content-type": "application/json", "cache-control": "no-store"},
                "body": json.dumps(body, allow_nan=False)}
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims") or {}
    if event.get("routeKey") != "GET /v1/staging-epoch5" or not claims.get("sub"):
        return response(403, {"error": "JWT_REQUIRED"})
    try:
        dates = (event.get("queryStringParameters") or {}).get("dates", "").split(",")
        today = dt.datetime.now(dt.timezone.utc).date()
        require(1 <= len(dates) <= 14 and dates == sorted(set(dates)), "DATE_COUNT_OR_ORDER")
        require(all(re.fullmatch(r"20\d\d-\d\d-\d\d", d) and
                    0 <= (today - dt.date.fromisoformat(d)).days <= 45 for d in dates), "DATE_RANGE")
    except (ValueError, TypeError):
        return response(400, {"error": "INVALID_DATES"})
    import boto3
    return response(200, summarize(boto3.client("s3", region_name="eu-central-1"), dates))
