"""Calendar-aware watchdog: weekends, holidays, early close, DST, disabled scheduler,
record validation, chain integrity, durable (non-windowed) hole detection."""
from datetime import datetime, timedelta, timezone
import hashlib
from infra.aws.independent_session_watchdog import due_sessions, inspect
from infra.aws import session_continuity as sc

U = lambda *a: datetime(*a, tzinfo=timezone.utc)


GENESIS = {}   # bootstrap_session -> genesis object produced alongside the chain


def chain(sessions, statuses=None):
    """Valid, internally consistent hash chain starting at genesis.
    Times are realistic: the decision signal is archived 1h after the PRIOR session's
    close; the paper receipt is saved 1h after the session's own close (ON_TIME)."""
    recs, shas, times, prev = {}, {}, {}, None
    for s in sessions:
        st = (statuses or {}).get(s, sc.ON_TIME)
        close = sc.session_close_utc(s)
        sig = None if st == sc.MISSED else sc.session_close_utc(sc.previous_session(s)) + timedelta(hours=1)
        saved = close + timedelta(hours=1)
        rsha = None if st == sc.MISSED else hashlib.sha256(s.encode()).hexdigest()
        rec = sc.build_record(
            session=s, status=st, previous_record=prev,
            previous_record_sha256=None if prev is None else hashlib.sha256(sc.canonical(prev)).hexdigest(),
            processed_at=saved, signal_archived_at=sig, book=sc.BOOK,
            reason="bars unavailable" if st == sc.MISSED else None,
            evidence=None if rsha is None else {"paper_sha256": rsha})
        if prev is None:
            GENESIS[sessions[0]] = sc.build_genesis(book=sc.BOOK, first_record=rec)
        recs[s], shas[s], prev = rec, rsha, rec
        if rsha:
            times[f"paper/sessions/{s}.json"] = saved
        if sig:
            times[f"signals/{sc.previous_session(s)}.json"] = sig
    return recs, shas, times


def run(now, recs, shas=None, rule="ENABLED", expected="ENABLED", start="2026-10-01", times=None):
    return inspect(now=now, rule_state=rule, expected_rule_state=expected,
                   monitoring_start=start, read_record=lambda s: recs.get(s),
                   read_receipt_sha=lambda s: (shas or {}).get(s),
                   read_last_modified=None if times is None else times.get,
                   read_genesis=lambda: GENESIS.get(start))


def test_weekend_silence_is_not_a_failure_but_a_fixed_26h_deadman_would_fire():
    recs, shas, _ = chain(["2026-10-08", "2026-10-09"])
    r = run(U(2026, 10, 11, 18), recs, shas, start="2026-10-08")   # Sunday
    assert r["status"] == "PASS" and r["metrics"]["WatchdogFailClosed"] == 0


def test_missing_session_detected_after_its_deadline_only():
    recs, shas, _ = chain(["2026-10-08"])
    assert run(U(2026, 10, 12, 13, 29), recs, shas, start="2026-10-08")["missed_sessions"] == []
    r = run(U(2026, 10, 12, 13, 31), recs, shas, start="2026-10-08")   # Mon open 13:30Z
    assert r["missed_sessions"] == ["2026-10-09"] and r["metrics"]["WatchdogFailClosed"] == 1


def test_holidays_and_early_close():
    assert "2026-11-26" not in due_sessions(U(2026, 12, 1), "2026-11-20")
    assert "2026-11-27" not in due_sessions(U(2026, 11, 30, 14, 29), "2026-11-20")
    assert "2026-11-27" in due_sessions(U(2026, 11, 30, 14, 31), "2026-11-20")


def test_old_hole_keeps_alarming_beyond_any_sliding_window():
    days = [d for d in due_sessions(U(2026, 11, 20), "2026-10-01")]
    recs, shas, _ = chain(days)
    hole = days[2]
    del recs[hole]
    r = run(U(2026, 11, 20), recs, shas, start="2026-10-01")
    assert hole in r["missed_sessions"] and len(days) > 20


def test_scheduler_state_is_alarmed_but_never_disables_completeness_checks():
    # No book configured, scheduler intentionally disabled: nothing to check -> PASS.
    r = inspect(now=U(2026, 10, 14), rule_state="DISABLED", expected_rule_state="DISABLED",
                monitoring_start=None, read_record=lambda s: None)
    assert r["status"] == "PASS" and r["mode"] == "NOT_CONFIGURED_NO_BOOK_MONITORING"
    # Book configured, scheduler intentionally disabled (manual staging): still checked.
    recs, shas, times = chain(["2026-10-08", "2026-10-09"])
    r = run(U(2026, 10, 14), recs, shas, rule="DISABLED", expected="DISABLED",
            start="2026-10-08", times=times)
    assert r["mode"] == "CHECKING" and r["missed_sessions"] == ["2026-10-12"]
    # Unauthorized enable / accidental disable are alarmed either way.
    r = run(U(2026, 10, 14), {}, rule="ENABLED", expected="DISABLED", start=None)
    assert r["metrics"]["SchedulerStateMismatch"] == 1 and r["status"] == "FAIL_CLOSED"
    r = run(U(2026, 10, 14), {}, rule="DISABLED", expected="ENABLED", start=None)
    assert r["metrics"]["SchedulerStateMismatch"] == 1


def test_genesis_must_exist_match_start_and_bind_first_record():
    days = ["2026-10-08", "2026-10-09"]
    recs, shas, times = chain(days)
    base = dict(now=U(2026, 10, 12, 14), rule_state="ENABLED", expected_rule_state="ENABLED",
                monitoring_start="2026-10-08", read_record=recs.get,
                read_receipt_sha=shas.get, read_last_modified=times.get)
    assert inspect(**base, read_genesis=lambda: GENESIS["2026-10-08"])["status"] == "PASS"
    r = inspect(**base, read_genesis=lambda: None)
    assert "CONFIGURATION:GENESIS_UNVERIFIED" in r["failures"]
    other = dict(GENESIS["2026-10-08"], receipt_sha256="e" * 64)
    r = inspect(**base, read_genesis=lambda: other)
    assert "GENESIS_RECEIPT_MISMATCH" in r["invalid_records"]["2026-10-08"]
    later = dict(GENESIS["2026-10-08"], bootstrap_session="2026-10-09")
    r = inspect(**base, read_genesis=lambda: later)
    assert "CONFIGURATION:MONITORING_START_IS_NOT_BOOK_GENESIS" in r["failures"]


def test_halted_book_is_reported():
    recs, shas, _ = chain(["2026-10-08", "2026-10-09"], {"2026-10-09": sc.MISSED})
    r = run(U(2026, 10, 12, 14), recs, shas, start="2026-10-08")
    assert r["halted_sessions"] == ["2026-10-09"] and r["metrics"]["BookHalted"] == 1
    assert r["metrics"]["InvalidReceipts"] == 0


def test_chain_break_receipt_mismatch_and_wrong_book_are_invalid():
    days = ["2026-10-08", "2026-10-09", "2026-10-12"]
    recs, shas, _ = chain(days)
    recs["2026-10-09"] = dict(recs["2026-10-09"], epoch=1, qualified_streak_in_epoch=99)  # tamper
    shas["2026-10-12"] = "0" * 64
    r = run(U(2026, 10, 14), recs, shas, start="2026-10-08")
    assert "CHAIN_BROKEN" in r["invalid_records"]["2026-10-12"]
    assert "RECEIPT_SHA_MISMATCH" in r["invalid_records"]["2026-10-12"]
    recs2, shas2, _ = chain(days)
    r = inspect(now=U(2026, 10, 14), rule_state="ENABLED", expected_rule_state="ENABLED",
                monitoring_start="2026-10-08", read_record=recs2.get,
                read_receipt_sha=shas2.get, book="OTHER_BOOK")
    assert r["metrics"]["InvalidReceipts"] == 3


def test_missed_record_with_receipt_present_is_contradictory():
    recs, shas, _ = chain(["2026-10-08", "2026-10-09"], {"2026-10-09": sc.MISSED})
    shas["2026-10-09"] = "a" * 64
    r = run(U(2026, 10, 12, 14), recs, shas, start="2026-10-08")
    assert "MISSED_BUT_RECEIPT_EXISTS" in r["invalid_records"]["2026-10-09"]


def test_read_errors_are_configuration_failures_with_metric():
    def boom(s):
        raise PermissionError("AccessDenied")
    r = inspect(now=U(2026, 10, 14), rule_state="ENABLED", expected_rule_state="ENABLED",
                monitoring_start="2026-10-08", read_record=boom)
    assert r["status"] == "FAIL_CLOSED" and r["metrics"]["ConfigurationError"] >= 1


def test_genesis_anchored_chain_passes_with_genuine_s3_times():
    days = ["2026-10-08", "2026-10-09", "2026-10-12"]
    recs, shas, times = chain(days)
    r = run(U(2026, 10, 14), recs, shas, start="2026-10-08", times=times)
    assert r["status"] == "PASS", r["failures"]


def test_record_time_differing_from_s3_receipt_time_is_invalid():
    days = ["2026-10-08", "2026-10-09"]
    recs, shas, times = chain(days)
    times["paper/sessions/2026-10-09.json"] += timedelta(minutes=1)
    r = run(U(2026, 10, 14), recs, shas, start="2026-10-08", times=times)
    assert "PROCESSED_AT_NOT_S3_RECEIPT_TIME" in r["invalid_records"]["2026-10-09"]
    recs, shas, times = chain(days)
    times["signals/2026-10-08.json"] -= timedelta(hours=3)   # backdated claim vs S3
    r = run(U(2026, 10, 14), recs, shas, start="2026-10-08", times=times)
    assert "SIGNAL_TIME_NOT_S3_TIME" in r["invalid_records"]["2026-10-09"]


def test_monitoring_start_after_genesis_is_unanchored_and_fails_closed():
    recs, shas, times = chain(["2026-10-08", "2026-10-09", "2026-10-12"])
    r = run(U(2026, 10, 14), recs, shas, start="2026-10-09", times=times)
    assert "PREDECESSOR_UNVERIFIED" in r["invalid_records"]["2026-10-09"]
    assert r["status"] == "FAIL_CLOSED"
