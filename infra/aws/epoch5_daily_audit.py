"""Read-only accounting and continuity audit for the active modeled ST book."""
from datetime import datetime, timedelta, timezone
import math

from infra.aws import epoch5_portal_reader as reader
from market_calendar import calendar, latest_completed_contract

ALARMS = ("stocklens-st-epoch5-paper-errors", "stocklens-st-epoch5-continuity-missing")


def check(condition, label):
    if not condition:
        raise ValueError(label)


def money(actual, expected, label):
    check(math.isclose(actual, expected, abs_tol=0.00001, rel_tol=0), label)


def reconcile(paper):
    start, row, end = paper["start_state"], paper["row"], paper["state"]
    cash = start["cash"] + row["dividends_credited_session"]
    shares = dict(start["shares"])
    fees, slippage = start["cumulative_fees"], start["cumulative_slippage_cost"]
    for trade in paper["trades"]:
        side, symbol, qty = trade["side"], trade["symbol"], trade["qty"]
        check(symbol in ("QQQ", "TQQQ") and side in ("BUY", "SELL")
              and type(qty) is int and qty > 0, "TRADE_FIELDS")
        check(trade["execution_session"] == paper["session"] and trade["signal_date"] == row["signal_date"]
              and trade["time_et"] == ("09:31" if side == "SELL" else "09:32"), "TRADE_TIMING")
        sign = 1 if side == "BUY" else -1
        gross = qty * trade["modeled_fill_price"]
        money(trade["gross_notional"], gross, "TRADE_NOTIONAL")
        fee = gross * row["fee_bps"] / 10000
        money(trade["fee"], fee, "TRADE_FEE")
        cost = qty * abs(trade["modeled_fill_price"] - trade["reference_price"])
        money(trade["modeled_slippage_cost"], cost, "TRADE_SLIPPAGE")
        cash -= sign * gross + fee
        shares[symbol] += sign * qty
        fees += fee
        slippage += cost
    # Split ratios are not stored in these receipts. Any unexplained share move
    # needs raw corporate-action evidence and cannot be inferred from ending shares.
    check(shares == end["shares"] == {"QQQ": row["qqq_shares"], "TQQQ": row["tqqq_shares"]},
          "SHARES_REQUIRE_RECONCILIATION")
    money(cash, row["cash"], "CASH")
    money(cash, end["cash"], "END_CASH")
    money(fees, row["cumulative_fees"], "FEES")
    money(slippage, row["cumulative_slippage_cost"], "SLIPPAGE")
    nav = cash + shares["QQQ"] * row["qqq_close"] + shares["TQQQ"] * row["tqqq_close"]
    money(nav, row["equity"], "NAV")
    money(nav, end["last_equity"], "END_NAV")


def audit(s3, now):
    slot = now.replace(hour=22, minute=0, second=0, microsecond=0)
    if slot > now:
        slot -= timedelta(days=1)
    due = latest_completed_contract(slot)["session"]
    cal = calendar()
    sessions = [s.date().isoformat() for s in cal.sessions_in_range(reader.FIRST, due)[-3:]]
    check(bool(sessions), "NO_DUE_SESSION")
    prior_payload = prior_meta = prior_cont = None
    for day in sessions:
        prev = cal.previous_session(day).date().isoformat()
        if prior_payload is None and day != reader.FIRST:
            prior_payload, prior_meta = reader.read(s3, reader.PREFIX + "sessions/" + prev + ".json", receipt=True)
            _, prior_cont = reader.read(s3, reader.PREFIX + "continuity/" + prev + ".json", receipt=True)
        summary = reader.paper(s3, day)
        check(summary and summary["execution_signal"]["session_date"] == prev, "MISSING_PAIR_OR_PRIOR_SIGNAL:" + day)
        p, pm = reader.read(s3, summary["key"], receipt=True, version=summary["version_id"])
        c, cm = reader.read(s3, reader.PREFIX + "continuity/" + day + ".json", receipt=True,
                            version=summary["continuity_version_id"])
        check(p["prior_paper_sha256"] == (prior_meta and prior_meta["sha256"])
              and p["prior_continuity_sha256"] == c["previous_record_sha256"] == (prior_cont and prior_cont["sha256"]),
              "PREDECESSOR_HASH:" + day)
        if prior_payload is None:
            check(p["start_state"]["cash"] == 100000 and p["start_state"]["shares"] == {"QQQ": 0, "TQQQ": 0},
                  "DEMO_GENESIS")
        else:
            check(prior_payload["state"] == p["start_state"], "STATE_HANDOFF:" + day)
        reconcile(p)
        print(day, "MODELED_ACCOUNTING_AND_PREDECESSOR_VERIFIED")
        prior_payload, prior_meta, prior_cont = p, pm, cm


if __name__ == "__main__":
    import boto3
    aws = boto3.Session(region_name="eu-central-1")
    audit(aws.client("s3"), datetime.now(timezone.utc))
    alarms = aws.client("cloudwatch").describe_alarms(AlarmNames=list(ALARMS))["MetricAlarms"]
    states = {a["AlarmName"]: a["StateValue"] for a in alarms}
    print("Current Epoch5 alarms", states)
    check(states == dict.fromkeys(ALARMS, "OK"), "ACTIVE_ALARMS_MISSING_OR_NON_OK")
