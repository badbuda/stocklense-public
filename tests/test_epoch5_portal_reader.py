import io
import json
import hashlib
from datetime import datetime, timezone
from infra.aws import epoch5_portal_reader as r


class Missing(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


class Fake:
    def __init__(self):
        self.objects = {}
    def add(self, key, obj):
        raw = json.dumps(obj).encode()
        self.objects[key] = raw
        return hashlib.sha256(raw).hexdigest()
    def head_object(self, Bucket, Key, **kw):
        assert Bucket == r.BUCKET
        if Key not in self.objects:
            raise Missing()
        raw = self.objects[Key]
        return {"VersionId": "v1", "ContentLength": len(raw), "LastModified": datetime.now(timezone.utc),
                "Metadata": {"sha256": hashlib.sha256(raw).hexdigest()}}
    def get_object(self, Bucket, Key, VersionId):
        assert Bucket == r.BUCKET and VersionId == "v1"
        return {"VersionId": VersionId, "Body": io.BytesIO(self.objects[Key])}
    def list_objects_v2(self, Bucket, Prefix, MaxKeys):
        return {"IsTruncated": False, "Contents": [{"Key": k} for k in self.objects if k.startswith(Prefix)]}


def fixture():
    s = Fake()
    day, prior = r.FIRST, "2026-11-23"
    sk = "signals/" + prior + ".json"
    sha = s.add(sk, {"mode": r.MODE, "execution_plan": {"broker_actions_enabled": False},
                     "latest": {"asof_date": prior, "level": 1.25, "target_leverage": 1.25}})
    s.add(r.PREFIX + "genesis.json", {"book": r.BOOK, "first_session": day,
          "old_book_transferred": False, "broker_orders_authorized": False})
    pk = r.PREFIX + "sessions/" + day + ".json"
    psha = s.add(pk, {"book": r.BOOK, "session": day, "mode": r.MODE,
        "broker_orders_authorized": False, "broker_fills_observed": False,
        "state": {"last_mark_session": day}, "trades": [],
        "row": {"session_date": day, "signal_date": prior, "target_level": 1.25,
                "target_leverage": 1.25, "equity": 100000, "cash": 500,
                "qqq_shares": 30, "tqqq_shares": 10, "cumulative_fees": 0,
                "cumulative_slippage_cost": 0, "trade_count_session": 0},
        "market_evidence": {"schema": "sl63-yahoo-single-vendor-1m-quote-evidence-v1",
                "single_vendor": "YFINANCE_1M_RAW", "synthetic_quotes": False,
                "independent_second_vendor_verified": False},
        "signal": {"key": sk, "version_id": "v1", "sha256": sha}})
    ck = r.PREFIX + "continuity/" + day + ".json"
    s.add(ck, {"book": r.BOOK, "session": day, "status": r.CONT, "broker_orders": False,
               "broker_fills": False, "evidence": {"paper_key": pk, "paper_version_id": "v1", "paper_sha256": psha}})
    return s, ck


def test_pending_and_lag1_pair_are_separate():
    assert r.summarize(Fake(), [r.FIRST])["sessions"][0]["paper_status"] == "NO_RECEIPT"
    s, _ = fixture()
    result = r.summarize(s, ["2026-11-23", r.FIRST])
    assert result["full_chain_verified"] is False
    assert result["sessions"][0]["signal"]["level"] == 1.25
    day = result["sessions"][1]
    assert day["signal"] is None
    assert day["paper"]["execution_signal"]["session_date"] == "2026-11-23"
    assert day["paper"]["equity"] == 100000
    assert day["paper_status"] == "SHA_BOUND_SINGLE_VENDOR_MODELED"


def test_partial_or_bad_binding_never_exposes_equity():
    s, ck = fixture()
    cont = json.loads(s.objects[ck])
    cont["evidence"]["paper_sha256"] = "bad"
    s.add(ck, cont)
    row = r.summarize(s, [r.FIRST])["sessions"][0]
    assert row["paper"] is None and row["paper_status"] == "INVALID_OR_PARTIAL_EVIDENCE"
    del s.objects[ck]
    assert r.summarize(s, [r.FIRST])["sessions"][0]["paper"] is None


def test_direct_event_without_jwt_rejected():
    assert r.handler({"routeKey": "GET /v1/staging-epoch5"}, None)["statusCode"] == 403


def test_public_allowlist_fixed_demo_only():
    from infra.aws import epoch5_public_model as pub
    s, _ = fixture()
    g = r.PREFIX + "genesis.json"
    obj = json.loads(s.objects[g])
    obj.update(starting_cash_usd=100000, starting_shares={"QQQ": 0, "TQQQ": 0})
    s.add(g, obj)
    d = pub.project(s, ["2026-11-23", r.FIRST])
    assert d["sessions"][-1]["paper"]["equity"] == 100000
    assert d["sessions"][-1]["paper"]["trades"] == []
    raw = json.dumps(d)
    for prohibited in ("version_id", "sha256", "saved_at_utc", "signals/", "paper/epochs/"):
        assert prohibited not in raw
    obj["starting_cash_usd"] = 100001
    s.add(g, obj)
    assert pub.project(s, [r.FIRST])["sessions"][0]["paper"] is None
    assert pub.public_handler({"routeKey": "GET /v1/staging-epoch5"}, None)["statusCode"] == 404
