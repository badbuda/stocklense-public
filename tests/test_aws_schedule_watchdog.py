"""Pure AWS watchdog tests; no live AWS calls or external packages."""
from datetime import datetime, timezone
import ast
from pathlib import Path

TEMPLATE = Path("infra/aws/paper-signal-journal.yaml").read_text()
SOURCE = Path("infra/aws/schedule-watchdog-handler.py").read_text()

def checker():
    tree = ast.parse(SOURCE)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "inspect")
    ns = {"timezone": timezone}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "schedule-watchdog", "exec"), ns)
    return ns["inspect"]

class Events:
    def __init__(self, state="ENABLED", arn="arn:expected"):
        self.state, self.arn = state, arn
    def describe_rule(self, *, Name):
        return {"State": self.state}
    def list_targets_by_rule(self, *, Rule):
        return {"Targets": [{"Arn": self.arn}]}

class Lambdas:
    def __init__(self, state="Active"): self.state = state
    def get_function_configuration(self, *, FunctionName):
        return {"State": self.state, "FunctionArn": "arn:expected"}

class Metrics:
    def __init__(self, counts=1): self.counts = counts
    def get_metric_statistics(self, **kw):
        return {"Datapoints": [{"Sum": self.counts}] if self.counts is not None else []}

PAIR = [("rule-1", "shadow"), ("rule-2", "paper")]

def check(at, events=None, lambdas=None, metrics=None):
    return checker()(datetime.fromisoformat(at), PAIR,
                     events or Events(), lambdas or Lambdas(), metrics or Metrics())

def test_configuration_ok_outside_invocation_check_window():
    result = check("2026-10-10T06:15:00+00:00")
    assert result["status"] == "PASS"
    assert result["invocation_check_due"] is False
    assert result["broker_execution_authorized"] is False

def test_both_missed_invocations_fail_closed_after_schedule():
    result = check("2026-10-10T12:15:00+00:00", metrics=Metrics(None))
    assert result["status"] == "FAIL_CLOSED"
    assert result["failures"].count("EXPECTED_INVOCATION_MISSING:shadow") == 1
    assert result["failures"].count("EXPECTED_INVOCATION_MISSING:paper") == 1

def test_observed_invocations_after_schedule_pass():
    result = check("2026-10-10T12:15:00+00:00")
    assert result["invocation_check_due"] and result["status"] == "PASS"

def test_disabled_eventbridge_rule_is_detected_even_on_sunday():
    result = check("2026-10-11T06:15:00+00:00", events=Events("DISABLED"))
    assert result["status"] == "FAIL_CLOSED"
    assert any(x.startswith("RULE_NOT_ENABLED") for x in result["failures"])

def test_wrong_eventbridge_lambda_target_is_detected():
    result = check("2026-10-11T06:15:00+00:00", events=Events(arn="arn:wrong"))
    assert result["status"] == "FAIL_CLOSED"
    assert any(x.startswith("EXPECTED_LAMBDA_NOT_TARGETED") for x in result["failures"])

def test_inactive_lambda_is_detected():
    result = check("2026-10-11T06:15:00+00:00", lambdas=Lambdas("Inactive"))
    assert result["status"] == "FAIL_CLOSED"
    assert any(x.startswith("ARCHIVE_LAMBDA_NOT_ACTIVE") for x in result["failures"])

def test_scheduled_invocation_expected_on_market_holidays_too():
    # The rules are configured Tue-Sat, including US holidays. This checks
    # expected EventBridge -> Lambda invocation, not archival on market closure.
    result = check("2026-12-26T12:15:00+00:00", metrics=Metrics(None))
    assert result["invocation_check_due"] is True
    assert any("EXPECTED_INVOCATION_MISSING" in x for x in result["failures"])

def test_auditor_does_not_require_invocation_on_sunday():
    result = check("2026-10-11T12:15:00+00:00", metrics=Metrics(None))
    assert result["invocation_check_due"] is False
    assert result["status"] == "PASS"

def test_read_only_monitor_template_uses_independent_watchdog_and_sns():
    assert TEMPLATE.count("Type: AWS::Lambda::Function") == 3
    assert "cron(15 0/6 * * ? *)" in TEMPLATE
    assert "WatchdogHeartbeatAlarm:" in TEMPLATE and "WatchdogErrorAlarm:" in TEMPLATE
    section = TEMPLATE.split("  WatchdogHeartbeatAlarm:")[1].split("  GitHubOIDC:")[0]
    assert "TreatMissingData: breaching" in section
    assert "DatapointsToAlarm: 2" in section
    assert "Period: 21600" in section
    assert "cloudwatch:GetMetricStatistics" in TEMPLATE
    assert "events:DescribeRule" in TEMPLATE and "events:ListTargetsByRule" in TEMPLATE
    assert "lambda:GetFunctionConfiguration" in TEMPLATE
    assert "sns:Publish" not in TEMPLATE
    assert "dynamodb:PutItem" not in TEMPLATE.split("  WatchdogRole:")[1].split("  WatchdogLambda:")[0]
    assert len(SOURCE) < 4096

def test_cloudformation_inline_handler_exactly_matches_separate_source():
    segment = TEMPLATE.split("  WatchdogLambda:", 1)[1].split("  WatchdogSchedule:", 1)[0]
    embedded = segment.split("ZipFile: |\n", 1)[1]
    embedded = "\n".join(x[10:] if x.startswith("          ") else x for x in embedded.splitlines()).strip()+"\n"
    assert embedded == SOURCE.strip()+"\n"
    ast.parse(embedded)
