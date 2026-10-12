"""Continuity journal: on-time / late / reconstructed / missed, epochs, halting."""
from datetime import datetime, timezone
import io, json
import pytest

from infra.aws import session_continuity as sc
from infra.aws.independent_paper import run_paper, run_paper_catchup
from stocklens.paper import SessionMarket, PaperIntegrityError


def signal(day, stamp):
    return {"version": "8.0.2-shadow-completed-session-guard",
            "mode": "SHADOW_ONLY_NO_BROKER_ACTIONS",
            "signal_source": "QQQ_ADJUSTED_DAILY_CLOSE", "generated_at_utc": stamp,
            "latest": {"asof_date": day, "level": 3, "defense_active": False,
                       "target_leverage": 3.0, "qqq_weight": 0.0, "tqqq_weight": 0.985},
            "action": "NO_CHANGE", "execution_plan": {"broker_actions_enabled": False}}


def observed_market(day):
    return SessionMarket(session_date=day, prices_0931={"QQQ": 100.0, "TQQQ": 80.0},
                         prices_0932={"QQQ": 101.0, "TQQQ": 81.0},
                         closes={"QQQ": 102.0, "TQQQ": 82.0},
                         dividends={"QQQ": 0.0, "TQQQ": 0.0},
                         split_ratios={"QQQ": 0.0, "TQQQ": 0.0}, source="YFINANCE_1M_RAW")

U = lambda *a: datetime(*a, tzinfo=timezone.utc)


class Missing(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


class Precondition(Exception):
    # Real S3 conditional-write failure shape (HTTP 412), as _immutable_put expects.
    response = {"Error": {"Code": "PreconditionFailed"},
                "ResponseMetadata": {"HTTPStatusCode": 412}}


class S3:
    """Versioned fake with server-side LastModified (settable per put clock)."""
    def __init__(self):
        self.data, self.mtime, self.clock = {}, {}, U(2026, 10, 9, 23, 0)

    def put(self, key, body, at):
        self.data[key], self.mtime[key] = body, at

    def get_object(self, **kw):
        k = kw["Key"]
        if k not in self.data:
            raise Missing()
        return {"Body": io.BytesIO(self.data[k]), "VersionId": "v1", "LastModified": self.mtime[k]}

    def put_object(self, **kw):
        if kw["Key"] in self.data:
            raise Precondition()
        self.put(kw["Key"], kw["Body"], self.clock)
        return {"VersionId": "v1"}


def seed(s3, day, gen, archived):
    s3.put(f"signals/{day}.json", json.dumps(signal(day, gen)).encode(), archived)


def fetch(prior, session):
    return observed_market(session)


# ---------- pure classification ----------
def test_classification_uses_s3_server_time_not_self_reported():
    kw = dict(session="2026-10-12", accounting_completed=True)
    assert sc.classify(signal_archived_at=U(2026, 10, 9, 23), processed_at=U(2026, 10, 12, 23), **kw) == sc.ON_TIME
    # processed after next open (Tue 13:30Z) -> late but decision-timing proven
    assert sc.classify(signal_archived_at=U(2026, 10, 9, 23), processed_at=U(2026, 10, 13, 20), **kw) == sc.LATE
    # archived after the 13:30Z open (EDT) -> never forward evidence
    assert sc.classify(signal_archived_at=U(2026, 10, 12, 13, 31), processed_at=U(2026, 10, 12, 23), **kw) == sc.RECONSTRUCTED
    assert sc.classify(signal_archived_at=None, processed_at=U(2026, 10, 12, 23), **kw) == sc.RECONSTRUCTED
    assert sc.classify(signal_archived_at=None, processed_at=None, session="2026-10-12",
                       accounting_completed=False) == sc.MISSED


def test_early_close_and_dst_deadlines():
    # Day after Thanksgiving 2026 closes 13:00 NY (18:00Z, EST)
    assert sc.session_close_utc("2026-11-27") == U(2026, 11, 27, 18, 0)
    # Deadline for Fri 2026-10-30 (EDT) is Mon 2026-11-02 open, now EST: 14:30Z
    assert sc.accounting_deadline_utc("2026-10-30") == U(2026, 11, 2, 14, 30)


def test_catchup_plan_skips_holidays_and_is_bounded():
    assert sc.plan_catchup(last_recorded_session="2026-12-23",
                           target_session="2026-12-28") == ["2026-12-24", "2026-12-28"]
    with pytest.raises(RuntimeError, match="CATCHUP_HORIZON_EXCEEDED"):
        sc.plan_catchup(last_recorded_session="2026-10-01", target_session="2026-10-13")


def _rec(session, status, prev=None, ticket=None):
    sha = None if prev is None else __import__("hashlib").sha256(sc.canonical(prev)).hexdigest()
    return sc.build_record(session=session, status=status, previous_record=prev,
                           previous_record_sha256=sha, processed_at=U(2026, 10, 14),
                           signal_archived_at=None, book="B",
                           reason="x" if status == sc.MISSED else None,
                           evidence={"human_resume_ticket": ticket} if ticket else None)


def test_epochs_never_upgrade_retroactively_and_gaps_cannot_be_skipped():
    a = _rec("2026-10-08", sc.ON_TIME)
    b = _rec("2026-10-09", sc.ON_TIME, a)
    assert (b["epoch"], b["qualified_streak_in_epoch"]) == (1, 2)
    c = _rec("2026-10-12", sc.RECONSTRUCTED, b)
    assert (c["epoch"], c["qualified_streak_in_epoch"], c["forward_evidence"]) == (1, 0, False)
    d = _rec("2026-10-13", sc.LATE, c)
    assert (d["epoch"], d["qualified_streak_in_epoch"]) == (2, 1)   # new epoch, not 3
    assert d["totals"][sc.RECONSTRUCTED] == 1 and d["operational_sla_met"] is False
    with pytest.raises(ValueError, match="CONTINUITY_GAP_NOT_RECORDED"):
        _rec("2026-10-15", sc.ON_TIME, d)                           # 10-14 skipped
    m = _rec("2026-10-14", sc.MISSED, d)
    with pytest.raises(ValueError, match="HUMAN_RESUME_REQUIRED"):
        _rec("2026-10-15", sc.ON_TIME, m)


# ---------- end-to-end over fake S3 ----------
def _bootstrap():
    s3 = S3()
    seed(s3, "2026-10-08", "2026-10-08T23:00:00+00:00", U(2026, 10, 8, 23, 1))
    seed(s3, "2026-10-09", "2026-10-09T23:00:00+00:00", U(2026, 10, 9, 23, 1))
    s3.clock = U(2026, 10, 9, 23, 30)
    run_paper(session="2026-10-09", now=U(2026, 10, 9, 23, 30), s3=s3, bucket="b",
              bootstrap=True, market_fetch=fetch)
    return s3


def test_one_failed_night_is_recovered_as_late_not_as_reset():
    """Reproduces the original defect: Monday's paper run never happened.
    Before: Tuesday fails forever (MISSING_PAPER_PREVIOUS_SESSION). After: catch-up."""
    s3 = _bootstrap()
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00", U(2026, 10, 12, 23, 1))  # signal ran
    seed(s3, "2026-10-13", "2026-10-13T23:00:00+00:00", U(2026, 10, 13, 23, 1))
    with pytest.raises(RuntimeError, match="MISSING_PREVIOUS_CONTINUITY_RECORD|MISSING_PAPER_PREVIOUS_SESSION"):
        run_paper(session="2026-10-13", now=U(2026, 10, 13, 23, 30), s3=s3, bucket="b",
                  market_fetch=fetch)
    s3.clock = U(2026, 10, 13, 23, 30)
    out = run_paper_catchup(target_session="2026-10-13", now=U(2026, 10, 13, 23, 30),
                            s3=s3, bucket="b", market_fetch=fetch)
    assert out["status"] == "STAGED_PAPER_CATCHUP_COMPLETED"
    assert [x["continuity_status"] for x in out["sessions"]] == [sc.LATE, sc.ON_TIME]
    tue = json.loads(s3.data["paper/continuity/2026-10-13.json"])
    assert tue["epoch"] == 1 and tue["qualified_streak_in_epoch"] == 3
    rcpt = json.loads(s3.data["paper/sessions/2026-10-13.json"])
    assert rcpt["bootstrap_start"] == "2026-10-09"          # same book, no silent reset
    assert out["broker_orders"] is False and out["broker_fills"] is False


def test_backdated_signal_is_reconstructed_and_breaks_epoch():
    s3 = _bootstrap()
    # generated_at claims Friday evening, but S3 only received it Monday 14:00Z (after open)
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00", U(2026, 10, 12, 23, 1))
    s3.mtime["signals/2026-10-09.json"] = U(2026, 10, 12, 14, 0)
    s3.clock = U(2026, 10, 12, 23, 30)
    out = run_paper_catchup(target_session="2026-10-12", now=U(2026, 10, 12, 23, 30),
                            s3=s3, bucket="b", market_fetch=fetch)
    assert out["sessions"][0]["continuity_status"] == sc.RECONSTRUCTED
    rec = json.loads(s3.data["paper/continuity/2026-10-12.json"])
    assert rec["forward_evidence"] is False and rec["qualified_streak_in_epoch"] == 0


def test_missing_bars_records_missed_and_halts_without_fake_receipt():
    s3 = _bootstrap()
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00", U(2026, 10, 12, 23, 1))

    def no_bars(prior, session):
        raise PaperIntegrityError("MISSING_0931_BAR:TQQQ:2026-10-12")
    s3.clock = U(2026, 10, 12, 23, 30)
    out = run_paper_catchup(target_session="2026-10-12", now=U(2026, 10, 12, 23, 30),
                            s3=s3, bucket="b", market_fetch=no_bars)
    assert out["status"] == "STAGED_PAPER_HALTED"
    assert "paper/sessions/2026-10-12.json" not in s3.data          # no invented fills
    rec = json.loads(s3.data["paper/continuity/2026-10-12.json"])
    assert rec["status"] == sc.MISSED and rec["book_halted"] and "MISSING_0931_BAR" in rec["reason"]
    seed(s3, "2026-10-13", "2026-10-13T23:00:00+00:00", U(2026, 10, 13, 23, 1))
    with pytest.raises(RuntimeError, match="BOOK_HALTED"):
        run_paper_catchup(target_session="2026-10-13", now=U(2026, 10, 13, 23, 30),
                          s3=s3, bucket="b", market_fetch=fetch)


def test_integrity_bugs_are_not_reclassified_as_missed():
    s3 = _bootstrap()
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00", U(2026, 10, 12, 23, 1))
    bad = observed_market("2026-10-12")
    bad.closes["TQQQ"] = float("nan")
    s3.clock = U(2026, 10, 12, 23, 30)
    with pytest.raises(ValueError, match="INVALID_OBSERVED_MARKET"):
        run_paper_catchup(target_session="2026-10-12", now=U(2026, 10, 12, 23, 30),
                          s3=s3, bucket="b", market_fetch=lambda p, s: bad)
    assert "paper/continuity/2026-10-12.json" not in s3.data


# ---------- each guard proven individually (mutation-killing) ----------
def test_genesis_blocks_rebootstrap_even_without_nearby_continuity():
    """Far-later bootstrap: no continuity record on its prior day, only genesis can stop it."""
    s3 = _bootstrap()
    seed(s3, "2026-10-19", "2026-10-19T23:00:00+00:00", U(2026, 10, 19, 23, 1))
    seed(s3, "2026-10-20", "2026-10-20T23:00:00+00:00", U(2026, 10, 20, 23, 1))
    s3.clock = U(2026, 10, 20, 23, 30)
    with pytest.raises(RuntimeError, match="REBOOTSTRAP_NOT_ALLOWED_BOOK_EXISTS"):
        run_paper(session="2026-10-20", now=U(2026, 10, 20, 23, 30), s3=s3, bucket="b",
                  bootstrap=True, market_fetch=fetch)
    assert "paper/sessions/2026-10-20.json" not in s3.data


def test_missed_session_refused_before_any_receipt_write():
    s3 = _bootstrap()
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00", U(2026, 10, 12, 23, 1))
    s3.clock = U(2026, 10, 12, 23, 30)

    def no_bars(prior, session):
        raise PaperIntegrityError("MISSING_0931_BAR:TQQQ:2026-10-12")
    run_paper_catchup(target_session="2026-10-12", now=U(2026, 10, 12, 23, 30),
                      s3=s3, bucket="b", market_fetch=no_bars)
    before = set(s3.data)
    with pytest.raises(RuntimeError, match="SESSION_CLASSIFIED_MISSED_CONFLICT"):
        run_paper(session="2026-10-12", now=U(2026, 10, 12, 23, 40), s3=s3, bucket="b",
                  market_fetch=fetch)
    assert set(s3.data) == before          # nothing written, no contradictory receipt


def test_existing_continuity_with_different_evidence_is_a_conflict():
    s3 = _bootstrap()
    key = "paper/continuity/2026-10-09.json"
    rec = json.loads(s3.data[key])
    rec["evidence"]["paper_sha256"] = "f" * 64
    s3.data[key] = sc.canonical(rec)
    with pytest.raises(RuntimeError, match="CONTINUITY_CONFLICT"):
        run_paper(session="2026-10-09", now=U(2026, 10, 9, 23, 30), s3=s3, bucket="b",
                  bootstrap=True, market_fetch=fetch)


def test_idempotent_rerun_keeps_original_save_time_classification():
    """Rerun after the deadline must not downgrade (or upgrade) an on-time session:
    completion is the ORIGINAL S3 save time of the identical receipt."""
    s3 = _bootstrap()
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00", U(2026, 10, 12, 23, 1))
    s3.clock = U(2026, 10, 12, 23, 31)
    first = run_paper(session="2026-10-12", now=U(2026, 10, 12, 23, 30), s3=s3, bucket="b",
                      market_fetch=fetch)
    s3.clock = U(2026, 10, 14, 15, 0)       # well after the 10-13 open
    again = run_paper(session="2026-10-12", now=U(2026, 10, 12, 23, 30), s3=s3, bucket="b",
                      market_fetch=fetch)
    assert first["continuity_status"] == again["continuity_status"] == sc.ON_TIME
    assert first["paper_sha256"] == again["paper_sha256"]


def test_halted_book_reports_halt_reason_and_writes_nothing():
    s3 = _bootstrap()
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00", U(2026, 10, 12, 23, 1))
    seed(s3, "2026-10-13", "2026-10-13T23:00:00+00:00", U(2026, 10, 13, 23, 1))
    s3.clock = U(2026, 10, 12, 23, 30)

    def no_bars(prior, session):
        raise PaperIntegrityError("MISSING_0931_BAR:TQQQ:2026-10-12")
    run_paper_catchup(target_session="2026-10-12", now=U(2026, 10, 12, 23, 30),
                      s3=s3, bucket="b", market_fetch=no_bars)
    before = set(s3.data)
    with pytest.raises(RuntimeError, match="BOOK_HALTED_AFTER_MISSED_SESSION_HUMAN_RESUME_REQUIRED"):
        run_paper(session="2026-10-13", now=U(2026, 10, 13, 23, 30), s3=s3, bucket="b",
                  market_fetch=fetch)
    assert set(s3.data) == before


# ---------- v2 review: recovery, typed unavailability, end-to-end validation ----------
from stocklens.paper import PaperIntegrityError
from infra.aws.independent_session_watchdog import inspect as watchdog_inspect


def test_interrupted_commit_recovers_with_original_save_time():
    """Receipt persisted, continuity write lost (crash). Rerun later must complete the
    chain with the ORIGINAL receipt time -- not reclassify by the recovery time."""
    s3 = _bootstrap()
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00", U(2026, 10, 12, 23, 1))
    s3.clock = U(2026, 10, 12, 23, 31)
    run_paper(session="2026-10-12", now=U(2026, 10, 12, 23, 30), s3=s3, bucket="b",
              market_fetch=fetch)
    del s3.data["paper/continuity/2026-10-12.json"]           # simulated crash
    s3.clock = U(2026, 10, 14, 15, 0)                        # recovery after deadline
    out = run_paper(session="2026-10-12", now=U(2026, 10, 12, 23, 30), s3=s3, bucket="b",
                    market_fetch=fetch)
    rec = json.loads(s3.data["paper/continuity/2026-10-12.json"])
    assert out["continuity_status"] == sc.ON_TIME
    assert rec["processed_at_utc"] == U(2026, 10, 12, 23, 31).isoformat()


def test_interrupted_commit_with_changed_vendor_data_fails_closed():
    s3 = _bootstrap()
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00", U(2026, 10, 12, 23, 1))
    s3.clock = U(2026, 10, 12, 23, 31)
    run_paper(session="2026-10-12", now=U(2026, 10, 12, 23, 30), s3=s3, bucket="b",
              market_fetch=fetch)
    del s3.data["paper/continuity/2026-10-12.json"]
    revised = observed_market("2026-10-12")
    revised.closes["QQQ"] = 102.5                            # vendor revised the bar
    with pytest.raises(RuntimeError, match="DIVERGENT_IMMUTABLE_S3_OBJECT"):
        run_paper(session="2026-10-12", now=U(2026, 10, 12, 23, 30), s3=s3, bucket="b",
                  market_fetch=lambda p, x: revised)
    assert "paper/continuity/2026-10-12.json" not in s3.data


@pytest.mark.parametrize("exc,missed", [
    (PaperIntegrityError("MISSING_0931_BAR:TQQQ:2026-10-12"), True),
    (PaperIntegrityError("MISSING_NEAR_SESSION_CLOSE:QQQ:2026-10-12"), True),
    (PaperIntegrityError("NO_COMMON_EXECUTION_SESSION"), True),
    # Transient network failures propagate (alarm + next-night retry), never MISSED.
    (TimeoutError("read timed out"), False),
    (ConnectionResetError("reset by peer"), False),
    (PaperIntegrityError("DUPLICATE_MINUTE_BARS:QQQ:2026-10-12"), False),
    (PaperIntegrityError("INVALID_EXEC_PRICE:QQQ:2026-10-12:0931"), False),
    (PaperIntegrityError("ACTION_FETCH_FAILED:QQQ:boom"), False),
    (KeyError("indicators"), False),
    (TypeError("NoneType is not subscriptable"), False),
])
def test_only_enumerated_absence_becomes_missed(exc, missed):
    s3 = _bootstrap()
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00", U(2026, 10, 12, 23, 1))
    s3.clock = U(2026, 10, 12, 23, 30)

    def fetcher(prior, session):
        raise exc
    if missed:
        out = run_paper_catchup(target_session="2026-10-12", now=U(2026, 10, 12, 23, 30),
                                s3=s3, bucket="b", market_fetch=fetcher)
        assert out["status"] == "STAGED_PAPER_HALTED"
    else:
        with pytest.raises(type(exc)):
            run_paper_catchup(target_session="2026-10-12", now=U(2026, 10, 12, 23, 30),
                              s3=s3, bucket="b", market_fetch=fetcher)
        assert "paper/continuity/2026-10-12.json" not in s3.data


def _readers(s3):
    def rec(day):
        raw = s3.data.get(f"paper/continuity/{day}.json")
        return None if raw is None else json.loads(raw)

    def sha(day):
        raw = s3.data.get(f"paper/sessions/{day}.json")
        return None if raw is None else __import__("hashlib").sha256(raw).hexdigest()
    return rec, sha, s3.mtime.get


def test_records_produced_by_the_real_pipeline_validate_end_to_end():
    """No hand-built fixtures: run the pipeline, then verify with the watchdog,
    including genuine (fake-S3) server times, and with summarize()."""
    s3 = _bootstrap()
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00", U(2026, 10, 12, 23, 1))
    seed(s3, "2026-10-13", "2026-10-13T23:00:00+00:00", U(2026, 10, 13, 23, 1))
    s3.clock = U(2026, 10, 13, 23, 30)                       # Monday processed late
    run_paper_catchup(target_session="2026-10-13", now=U(2026, 10, 13, 23, 30),
                      s3=s3, bucket="b", market_fetch=fetch)
    rec, sha, mtime = _readers(s3)
    r = watchdog_inspect(now=U(2026, 10, 15), rule_state="ENABLED",
                         expected_rule_state="ENABLED", monitoring_start="2026-10-09",
                         read_record=rec, read_receipt_sha=sha, read_last_modified=mtime,
                         read_genesis=lambda: json.loads(
                             s3.data["paper/book/NEW_AWS_INDEPENDENT_STAGING_BOOK/genesis.json"]))
    assert r["status"] == "PASS", r["failures"]
    chain = [rec(d) for d in ("2026-10-09", "2026-10-12", "2026-10-13")]
    summary = sc.summarize(chain)
    assert summary["qualified_streak_in_current_epoch"] == 3
    assert summary["totals"][sc.LATE] == 1
    forged = [dict(c) for c in chain]
    forged[-1]["qualified_streak_in_epoch"] = 252
    with pytest.raises(ValueError, match="UNVERIFIED_CHAIN"):
        sc.summarize(forged)


def test_skipped_session_forgery_consistent_in_everything_but_adjacency():
    """Forger skips Mon 10-12: Tue 10-13 chained directly to Fri 10-09 with correct
    hash, recomputed counters and realistic times. Only adjacency can reject it."""
    import hashlib
    from datetime import timedelta
    def t(day, h=1):
        return sc.session_close_utc(day) + timedelta(hours=h)
    a = sc.build_record(session="2026-10-09", status=sc.ON_TIME, previous_record=None,
                        previous_record_sha256=None, processed_at=t("2026-10-09"),
                        signal_archived_at=t("2026-10-08"), book=sc.BOOK,
                        evidence={"paper_sha256": "a" * 64})
    epoch, streak, totals = sc.derive_counters(a, sc.ON_TIME)
    forged = dict(a, session="2026-10-13", epoch=epoch, qualified_streak_in_epoch=streak,
                  totals=totals, previous_record_sha256=hashlib.sha256(sc.canonical(a)).hexdigest(),
                  processed_at_utc=t("2026-10-13").isoformat(),
                  signal_archived_at_utc=t("2026-10-12").isoformat(),
                  evidence={"paper_sha256": "c" * 64})
    errs = sc.validate_record(forged, session="2026-10-13", previous=a, receipt_sha256="c" * 64)
    assert errs == ["NONADJACENT_PREDECESSOR"]


def test_transient_timeout_fails_run_without_any_record_then_retry_succeeds():
    s3 = _bootstrap()
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00", U(2026, 10, 12, 23, 1))
    seed(s3, "2026-10-13", "2026-10-13T23:00:00+00:00", U(2026, 10, 13, 23, 1))
    s3.clock = U(2026, 10, 12, 23, 30)

    def flaky(prior, session):
        raise TimeoutError("read timed out")
    with pytest.raises(TimeoutError):
        run_paper_catchup(target_session="2026-10-12", now=U(2026, 10, 12, 23, 30),
                          s3=s3, bucket="b", market_fetch=flaky)
    assert "paper/continuity/2026-10-12.json" not in s3.data       # no MISSED, no halt
    s3.clock = U(2026, 10, 13, 23, 30)                            # next night
    out = run_paper_catchup(target_session="2026-10-13", now=U(2026, 10, 13, 23, 30),
                            s3=s3, bucket="b", market_fetch=fetch)
    assert [x["continuity_status"] for x in out["sessions"]] == [sc.LATE, sc.ON_TIME]


def test_summary_separates_decision_timing_from_execution_evidence():
    s3 = _bootstrap()
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00", U(2026, 10, 12, 23, 1))
    seed(s3, "2026-10-13", "2026-10-13T23:00:00+00:00", U(2026, 10, 13, 23, 1))
    s3.clock = U(2026, 10, 13, 23, 30)
    run_paper_catchup(target_session="2026-10-13", now=U(2026, 10, 13, 23, 30),
                      s3=s3, bucket="b", market_fetch=fetch)
    chain = [json.loads(s3.data[f"paper/continuity/{d}.json"])
             for d in ("2026-10-09", "2026-10-12", "2026-10-13")]
    summ = sc.summarize(chain)
    assert summ["decision_timing_streak_in_current_epoch"] == 3   # ON_TIME, LATE, ON_TIME
    assert summ["on_time_streak"] == 1                             # LATE broke it
    assert summ["execution_qualified_sessions"] == 0
    assert summ["execution_qualification"] == "BLOCKED_NO_INDEPENDENT_EXECUTION_SOURCE"


def test_bootstrap_crash_before_genesis_is_completed_by_identical_rerun():
    s3 = S3()
    seed(s3, "2026-10-08", "2026-10-08T23:00:00+00:00", U(2026, 10, 8, 23, 1))
    seed(s3, "2026-10-09", "2026-10-09T23:00:00+00:00", U(2026, 10, 9, 23, 1))
    s3.clock = U(2026, 10, 9, 23, 30)
    from infra.aws.independent_paper import GENESIS_KEY
    run_paper(session="2026-10-09", now=U(2026, 10, 9, 23, 30), s3=s3, bucket="b",
              bootstrap=True, market_fetch=fetch)
    del s3.data[GENESIS_KEY]                                    # crash before commit
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00", U(2026, 10, 12, 23, 1))
    with pytest.raises(RuntimeError, match="BOOK_GENESIS_MISSING"):
        run_paper(session="2026-10-12", now=U(2026, 10, 12, 23, 30), s3=s3, bucket="b",
                  market_fetch=fetch)                          # unanchored: refused
    run_paper(session="2026-10-09", now=U(2026, 10, 9, 23, 30), s3=s3, bucket="b",
              bootstrap=True, market_fetch=fetch)              # idempotent completion
    g = json.loads(s3.data[GENESIS_KEY])
    assert sc.validate_genesis(g, json.loads(s3.data["paper/continuity/2026-10-09.json"])) == []
    s3.clock = U(2026, 10, 12, 23, 30)
    out = run_paper(session="2026-10-12", now=U(2026, 10, 12, 23, 30), s3=s3, bucket="b",
                    market_fetch=fetch)
    assert out["continuity_status"] == sc.ON_TIME


def test_receipt_sha_from_s3_checksum_metadata_matches_content_hash():
    import base64, hashlib
    from infra.aws.independent_paper import s3_object_sha256_and_time
    body = b'{"receipt":1}'
    at = U(2026, 10, 12, 21)

    class Head(S3):
        def head_object(self, **kw):
            assert kw.get("ChecksumMode") == "ENABLED"
            if kw["Key"] not in self.data:
                raise Missing()
            return {"ChecksumSHA256": base64.b64encode(hashlib.sha256(self.data[kw["Key"]]).digest()).decode(),
                    "LastModified": self.mtime[kw["Key"]]}

        def get_object(self, **kw):
            raise AssertionError("must not download when checksum metadata exists")
    s3 = Head()
    s3.put("paper/sessions/x.json", body, at)
    assert s3_object_sha256_and_time(s3, "b", "paper/sessions/x.json") == (hashlib.sha256(body).hexdigest(), at)
    assert s3_object_sha256_and_time(s3, "b", "paper/sessions/missing.json") == (None, None)

    class Multipart(Head):
        def head_object(self, **kw):
            return {"ChecksumSHA256": "abc=-3", "LastModified": at}

        def get_object(self, **kw):
            return {"Body": io.BytesIO(body), "VersionId": "v1", "LastModified": at}
    # composite (multipart) checksum is not a content hash -> fall back to hashing
    assert s3_object_sha256_and_time(Multipart(), "b", "k")[0] == hashlib.sha256(body).hexdigest()
