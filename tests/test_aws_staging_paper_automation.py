"""Strict staging Paper-only schedule: signal producer separated, no auto bootstrap."""
from datetime import datetime, timezone
import pytest

from infra.aws.independent_paper import (
    run_scheduled_paper, audit_paper_schedule_readiness, BOOK,
)
from infra.aws import session_continuity as sc
from infra.aws.independent_session_watchdog import (
    inspect, resolve_paper_monitoring_start,
)
from test_aws_session_continuity import S3, _bootstrap

U = lambda y, m, d, h, mi=0: datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_scheduled_paper_rejects_missing_genesis_before_market_or_s3_write():
    s3 = S3()
    keys_before = dict(s3.data)
    with pytest.raises(RuntimeError, match="AUTOMATED_PAPER_FORBIDDEN_WITHOUT_VERIFIED_GENESIS"):
        run_scheduled_paper(
            now=U(2026, 10, 14, 1, 20), s3=s3, bucket="candidate",
            market_fetch=lambda *a: pytest.fail("NEVER_FETCH_BEFORE_GENESIS"),
        )
    assert s3.data == keys_before


def test_holiday_or_weekend_auto_paper_is_read_only_skip():
    s3 = S3()
    response = run_scheduled_paper(
        now=U(2026, 10, 19, 1, 20), s3=s3, bucket="candidate",
        market_fetch=lambda *args: pytest.fail("NO_MARKET_ON_NONSESSION"),
    )
    assert response == {
        "status": "SKIPPED_XNYS_NONTRADING_DAY",
        "broker_actions": False, "broker_orders": False,
        "broker_fills": False, "paper_data_written": False,
    }
    assert not s3.data


def test_scheduled_paper_first_book_session_idempotent_and_broker_free():
    s3 = _bootstrap()  # durable first book on Friday Oct 09
    snapshot = dict(s3.data)
    out = run_scheduled_paper(
        now=U(2026, 10, 10, 1, 20), s3=s3, bucket="candidate",
        market_fetch=lambda *a: pytest.fail("ALREADY_STORED_BOOTSTRAP_SESSION"),
    )
    assert out["status"] == "STAGED_PAPER_CATCHUP_COMPLETED"
    assert out["idempotent_noop"] is True
    assert out["broker_actions"] is False
    assert s3.data == snapshot


def test_readiness_proves_durable_genesis_chain_and_has_no_write():
    s3 = _bootstrap()
    before = dict(s3.data)
    r = audit_paper_schedule_readiness(
        session="2026-10-09", now=U(2026,10,10,1,20),
        s3=s3, bucket="candidate",
    )
    assert r["status"] == "STAGING_PAPER_SCHEDULE_READINESS_PASS_READ_ONLY"
    assert r["chain_sessions"] == 1
    assert r["continuity_status"] == sc.ON_TIME
    assert r["broker_actions"] is False
    assert r["paper_automation_authorized"] is False
    assert r["cross_vendor_parity_proven"] is False
    assert s3.data == before


def test_readiness_missing_genesis_fails_closed():
    with pytest.raises(RuntimeError, match="READINESS_GENESIS_MISSING"):
        audit_paper_schedule_readiness(
            session="2026-10-09", now=U(2026,10,10,1,20),
            s3=S3(), bucket="candidate",
        )


def test_watchdog_derives_monitored_book_start_from_immutable_genesis():
    g = {"schema":sc.GENESIS_SCHEMA,"book":sc.BOOK,
         "bootstrap_session":"2026-10-09"}
    assert resolve_paper_monitoring_start(None, g) == "2026-10-09"
    assert resolve_paper_monitoring_start("", None) is None
    assert resolve_paper_monitoring_start("2026-10-08", g) == "2026-10-08"
    assert resolve_paper_monitoring_start(None, {"schema":"BAD"}) == "INVALID_DURABLE_GENESIS"
    r = inspect(
        now=U(2026,10,10,1,20), rule_state="DISABLED",
        expected_rule_state="DISABLED", monitoring_start=None,
        read_record=lambda day: None, paper_rule_state="ENABLED",
    )
    assert "CONFIGURATION:AUTOMATED_PAPER_ENABLED_WITHOUT_GENESIS" in r["failures"]


def test_template_has_separate_delayed_disabled_paper_schedule():
    import yaml
    from pathlib import Path
    class Loader(yaml.SafeLoader): pass
    Loader.add_multi_constructor("!", lambda loader, suffix, node: suffix+":"+str(node.value))
    doc = yaml.load(Path("infra/aws/independent-staging.yaml").read_text(),Loader=Loader)
    r=doc["Resources"]
    signal=r["CandidateSignalOnlySchedule"]["Properties"]
    paper=r["CandidatePaperOnlySchedule"]["Properties"]
    assert signal["State"] == paper["State"] == "DISABLED"
    assert signal["ScheduleExpression"] == "cron(30 2 ? * TUE-SAT *)"
    assert paper["ScheduleExpression"] == "cron(20 3 ? * TUE-SAT *)"
    assert signal["Targets"][0]["Arn"] == "GetAtt:CandidateLambda.Arn"
    assert paper["Targets"][0]["Arn"] == "GetAtt:CandidatePaperLambda.Arn"
    assert paper["Targets"][0]["Input"] == '{"mode":"STAGING_PAPER_SCHEDULED","bootstrap":false}'
    assert r["CandidateOrchestratorSchedule"]["Properties"]["State"] == "DISABLED"
    watchdog = r["CandidateSessionWatchdogLambda"]["Properties"]["Environment"]["Variables"]
    assert watchdog["PAPER_ONLY_RULE"] == "Ref:CandidatePaperOnlySchedule"
    desc=[x for x in r["CandidateSessionWatchdogRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"] if x["Action"]=="events:DescribeRule"]
    assert "GetAtt:CandidatePaperOnlySchedule.Arn" in desc[0]["Resource"]
    assert doc["Outputs"]["CandidatePaperOnlyRuleName"]["Value"] == "Ref:CandidatePaperOnlySchedule"


def test_staging_deploy_prevents_replacing_active_daily_schedules():
    from pathlib import Path
    script=Path("infra/aws/deploy_independent_staging.sh").read_text()
    for name in ("CandidateSignalOnlyRuleName","CandidatePaperOnlyRuleName",
                 "CandidateOrchestratorRuleName"):
        assert name in script
    assert "REFUSE_REDEPLOY_ACTIVE_SCHEDULE" in script
    assert "REFUSE_REDEPLOY_ESTABLISHED_SIGNAL_MONITOR_ANCHOR" in script
    assert script.index("REFUSE_REDEPLOY_ACTIVE_SCHEDULE") < script.index(
        'aws s3api create-bucket')
    smoke=Path("infra/aws/smoke_independent_staging.sh").read_text()
    assert "PAPER_ONLY_NOT_SAFE_BY_DEFAULT" in smoke


def test_scheduled_paper_missing_current_signal_is_retryable_no_halt():
    s3=_bootstrap()
    before=dict(s3.data)
    with pytest.raises(RuntimeError,match="AUTOMATED_PAPER_SIGNALS_NOT_READY_RETRYABLE"):
        run_scheduled_paper(
            now=U(2026,10,13,1,20),s3=s3,bucket="candidate",
            market_fetch=lambda *args: pytest.fail("NEVER_FETCH_WITHOUT_SIGNAL"),
        )
    assert s3.data==before
    assert "paper/continuity/2026-10-12.json" not in s3.data


def test_scheduled_paper_current_session_missing_1m_bars_is_retryable():
    from test_aws_session_continuity import seed
    from infra.aws.independent_paper import ProviderUnavailable
    s3=_bootstrap()
    seed(s3,"2026-10-12","2026-10-12T22:30:00+00:00",U(2026,10,12,22,31))
    before=dict(s3.data)
    def no_bars(*args):
        raise ProviderUnavailable("just after close, vendor bar not published")
    with pytest.raises(RuntimeError,match="AUTOMATED_PAPER_1M_BARS_NOT_READY_RETRYABLE"):
        run_scheduled_paper(
            now=U(2026,10,13,1,20),s3=s3,bucket="candidate",
            market_fetch=no_bars,
        )
    assert s3.data==before
    assert "paper/continuity/2026-10-12.json" not in s3.data


def test_paper_activation_is_explicit_budgeted_and_requires_frozen_signal():
    from pathlib import Path
    import subprocess
    path="infra/aws/enable_staging_paper_only.sh"
    text=Path(path).read_text()
    subprocess.run(["bash","-n",path],check=True)
    for token in ("enable_staging_signal_only.sh check",
                  "STAGING_PAPER_SCHEDULE_READINESS",
                  "REQUIRE_AUTOMATED_SIGNAL_ENABLED_FIRST",
                  "REVIEWED_STAGING_PAPER_RISK_AND_EMAIL_ALERTS",
                  "CandidateOrchestratorRuleName",
                  "CandidatePaperOnlyRuleName",
                  "cross_vendor_parity_proven"):
        assert token in text
    assert text.count("aws events enable-rule")==1
    assert "aws cloudformation deploy" not in text
    assert "STAGING_PAPER_ONLY_SCHEDULE_ENABLED" in text
