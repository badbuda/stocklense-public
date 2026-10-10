from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from prospective_intraday_price_journal import collect, read_rows, verify

NY = ZoneInfo("America/New_York")
SESSION = "2026-10-08"
PRICES = {
    "QQQ": {SESSION: {"09:30": 800.0, "09:31": 801.0, "09:32": 802.0}},
    "TQQQ": {SESSION: {"09:30": 100.0, "09:31": 100.2, "09:32": 100.3}},
}


def test_collect_only_after_completed_session(tmp_path):
    journal = tmp_path / "journal.jsonl"
    before = collect(PRICES, now=datetime(2026, 10, 8, 17, 59, tzinfo=NY), journal=journal)
    assert before["status"] == "WAITING_FOR_COMPLETED_SESSION"
    assert not journal.exists()
    result = collect(PRICES, now=datetime(2026, 10, 8, 18, 1, tzinfo=NY), journal=journal)
    assert result["status"] == "CAPTURED_NEW_VERIFIED_SESSION"
    assert result["observed_completed_sessions"] == 1
    assert result["synthetic_quotes_used"] is False
    assert result["broker_fills_observed"] is False
    again = collect(PRICES, now=datetime(2026, 10, 8, 19, 0, tzinfo=NY), journal=journal)
    assert again["status"] == "ALREADY_CAPTURED_IMMUTABLE"
    assert len(read_rows(journal)) == 1


def test_no_synthetic_substitution_for_missing_tqqq(tmp_path):
    journal = tmp_path / "journal.jsonl"
    incomplete = {"QQQ": PRICES["QQQ"], "TQQQ": {}}
    result = collect(incomplete, now=datetime(2026, 10, 8, 18, 5, tzinfo=NY),
                     journal=journal)
    assert result["status"] == "SOURCE_MINUTE_PRICES_UNAVAILABLE_NO_BACKFILL"
    assert not journal.exists()


def test_does_not_backfill_later_sessions(tmp_path):
    journal = tmp_path / "journal.jsonl"
    future = {"QQQ": PRICES["QQQ"], "TQQQ": PRICES["TQQQ"]}
    result = collect(future, now=datetime(2026, 10, 9, 18, 5, tzinfo=NY),
                     journal=journal)
    assert result["observed_completed_sessions"] == 0
    assert not journal.exists()


def test_hash_tampering_is_rejected(tmp_path):
    journal = tmp_path / "journal.jsonl"
    collect(PRICES, now=datetime(2026, 10, 8, 18, 1, tzinfo=NY), journal=journal)
    assert len(read_rows(journal)) == 1
    content = journal.read_text()
    journal.write_text(content.replace("100.2", "999.2"))
    with pytest.raises(ValueError, match="ROW_INTEGRITY_MISMATCH"):
        read_rows(journal)


def test_session_sequence_and_chain(tmp_path):
    journal = tmp_path / "journal.jsonl"
    collect(PRICES, now=datetime(2026, 10, 8, 18, 1, tzinfo=NY), journal=journal)
    q = {"09:30": 805.0, "09:31": 806.0, "09:32": 807.0}
    t = {"09:30": 101.0, "09:31": 101.2, "09:32": 101.3}
    next_prices = {"QQQ": {"2026-10-09": q}, "TQQQ": {"2026-10-09": t}}
    collect(next_prices, now=datetime(2026, 10, 9, 18, 1, tzinfo=NY), journal=journal)
    rows = read_rows(journal)
    assert len(rows) == 2
    assert rows[1]["prior_row_sha256"] == rows[0]["row_sha256"]
    assert verify(rows) == rows[-1]["row_sha256"]


def test_new_rows_correctly_mark_minute_open_not_bid_ask(tmp_path):
    journal=tmp_path/"journal.jsonl"
    result=collect(PRICES, now=datetime(2026, 10, 8, 18, 1, tzinfo=NY), journal=journal)
    row=read_rows(journal)[0]
    assert set(row["minute_open_prices"])=={"QQQ","TQQQ"}
    assert row["price_semantics"]=="YAHOO_1MIN_BAR_OPEN_NOT_BID_ASK"
    assert "quotes" not in row
    assert result["bid_ask_quotes_observed"] is False
    assert result["legacy_quote_field_rows"]==0


def test_legacy_journal_sha_retained_then_new_row_chained(tmp_path):
    from pathlib import Path
    source=Path("research/prospective/observed_intraday_etf_journal.jsonl")
    old=read_rows(source)
    assert len(old)>=1
    assert "quotes" in old[0] and "minute_open_prices" not in old[0]
    journal=tmp_path/"journal.jsonl"
    journal.write_bytes(source.read_bytes())
    first_hash=old[-1]["row_sha256"]
    assert read_rows(journal)[-1]["row_sha256"]==first_hash
    last=old[-1]["session_date"]
    from datetime import date, timedelta
    next_day=(date.fromisoformat(last)+timedelta(days=1)).isoformat()
    data={s:{next_day:PRICES[s][SESSION]} for s in ("QQQ","TQQQ")}
    at=datetime.combine(date.fromisoformat(next_day),datetime.min.time(),tzinfo=NY).replace(hour=18,minute=1)
    result=collect(data,now=at,journal=journal)
    rows=read_rows(journal)
    assert result["status"]=="CAPTURED_NEW_VERIFIED_SESSION"
    assert rows[-1]["prior_row_sha256"]==first_hash
    assert "quotes" in rows[0] and "minute_open_prices" in rows[-1]
    assert verify(rows)==rows[-1]["row_sha256"]
