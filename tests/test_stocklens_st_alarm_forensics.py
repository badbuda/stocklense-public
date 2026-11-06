"""Read-only ST CloudWatch forensics: alarm state, metrics and origin."""
from datetime import datetime, timezone
import subprocess
from pathlib import Path
from infra.aws import stocklens_st_alarm_forensics as f


class FakeCF:
    def describe_stack_resource(self,**kw):
        return {"StackResourceDetail":{"PhysicalResourceId":"ST-"+kw["LogicalResourceId"]}}


class FakeCW:
    def describe_alarms(self,AlarmNames):
        return {"MetricAlarms":[{
            "AlarmName":AlarmNames[0],
            "StateValue":"ALARM","StateReason":"Threshold Crossed: synthetic example",
            "StateUpdatedTimestamp":datetime(2026,10,29,19,0,tzinfo=timezone.utc),
            "Namespace":"StockLens/IndependentStaging","MetricName":"MissedSessions",
            "Dimensions":[],"ActionsEnabled":True}]}
    def describe_alarm_history(self,**kwargs):
        return {"AlarmHistoryItems":[]}
    def get_metric_statistics(self,**kwargs):
        return {"Datapoints":[{"Timestamp":datetime(2026,10,29,18,0,tzinfo=timezone.utc),
                                "Maximum":1.0,"SampleCount":3.0}]}


class FakeLogs:
    def __init__(self):self.calls=0
    def filter_log_events(self,**kwargs):
        self.calls+=1
        if self.calls==1:
            return {"events":[{"eventId":"a","timestamp":1793300000000,
                "message":'{"status":"FAIL_CLOSED","failures":["SESSION_WITHOUT_CONTINUITY_RECORD:2026-10-27"],"metrics":{"MissedSessions":1,"WatchdogFailClosed":1}}'}],
                    "nextToken":"second"}
        return {"events":[{"eventId":"a","timestamp":1793300000000,
                "message":'{"status":"FAIL_CLOSED","failures":[],"metrics":{}}'},
                {"eventId":"b","timestamp":1793300002000,
                 "message":'{"status":"PASS","failures":[],"metrics":{"MissedSessions":0}}'}]}


def test_compiles():
    subprocess.run(["python","-m","py_compile","infra/aws/stocklens_st_alarm_forensics.py"],
                   check=True)


def test_alarm_reveals_reason_metric_and_absent_dimensions():
    out=f.alarm_details(FakeCF(),FakeCW(),"MissedSessionsAlarm",
          now=datetime(2026,10,29,20,0,tzinfo=timezone.utc))
    assert out["state"]=="ALARM"
    assert out["namespace"]=="StockLens/IndependentStaging"
    assert out["dimensions"]==[]
    assert out["latest_metrics"][0]["max"]==1.0
    assert "Threshold Crossed" in out["reason"]


def test_watchdog_pagination_dedupe_and_structured_failures():
    logs=FakeLogs()
    out=f.watchdog_logs(logs,"stocklens-st-watchdog",
                        datetime(2026,10,29,20,0,tzinfo=timezone.utc))
    assert logs.calls==2
    assert out["reports_seen"]==2
    assert out["pagination_incomplete"] is False
    assert out["last_reports"][0]["status"]=="FAIL_CLOSED"
    assert "SESSION_WITHOUT_CONTINUITY_RECORD" in out["last_reports"][0]["failures"][0]
    assert out["last_reports"][-1]["status"]=="PASS"


def test_no_alarm_mutations_or_broker_methods():
    source=Path("infra/aws/stocklens_st_alarm_forensics.py").read_text()
    for forbidden in (".set_alarm_state(", ".put_metric_data(",
                      ".disable_alarm_actions(", ".enable_rule(",
                      ".put_object(", ".invoke(", ".update_stack("):
        assert forbidden not in source
    assert '"PROD","ALL_DISABLED"' not in source  # never proclaim production from unverified literal
    assert "POTENTIAL_CROSS_ENVIRONMENT_CONTAMINATION" in source


def test_guarded_st_paper_is_not_falsely_reported_disabled():
    source=Path("infra/aws/stocklens_st_alarm_forensics.py").read_text()
    assert '"CandidatePaperErrorsAlarm"' in source
    assert 'st_schedules[name]=state' in source
    assert 'st_schedules["CandidatePaperOnlyRuleName"]' in source
    assert '"UNSAFE_ST_ORCHESTRATOR_RULE"' in source
    assert '"UNSAFE_ST_PAPER_OR_ORCHESTRATOR_RULE"' not in source
    assert '"st_paper":"DISABLED"' not in source


def test_watchdog_bounded_recent_window_does_not_claim_old_pass_as_latest():
    now=datetime(2026,11,6,20,0,tzinfo=timezone.utc)
    class Pages:
        def __init__(self):
            self.calls=[]
        def filter_log_events(self,**kwargs):
            self.calls.append(kwargs)
            if kwargs["startTime"] < int((now.timestamp()-7*3600)*1000):
                return {"events":[{"eventId":"old-"+str(len(self.calls)),
                                   "timestamp":1793970000000,
                                   "message":'{"metrics":{"WatchdogFailClosed":0},"failures":[],"status":"PASS"}'}],
                        "nextToken":str(len(self.calls))}
            return {"events":[{"eventId":"recent","timestamp":1793995200000,
                               "message":'{"metrics":{"WatchdogFailClosed":1},"failures":["MISSING_RECEIPT"],"status":"FAIL_CLOSED"}'}]}
    client=Pages()
    out=f.watchdog_logs(client,"stocklens-st-watchdog",now)
    assert out["pagination_incomplete"] is False
    assert out["window_hours"] == 6
    assert out["last_reports"][-1]["status"] == "FAIL_CLOSED"
    assert "MISSING_RECEIPT" in out["last_reports"][-1]["failures"]
    assert len(client.calls)==9


def test_watchdog_all_windows_paginated_reports_unknown_not_old_pass():
    now=datetime(2026,11,6,20,0,tzinfo=timezone.utc)
    class AlwaysTruncated:
        calls=0
        def filter_log_events(self,**kwargs):
            self.calls+=1
            return {"events":[],"nextToken":str(self.calls)}
    client=AlwaysTruncated()
    out=f.watchdog_logs(client,"stocklens-st-watchdog",now)
    assert out["pagination_incomplete"] is True
    assert out["last_reports"] == []
    assert out["latest_structured_utc"] is None
    assert client.calls == 32


def test_st_metric_provenance_requires_isolated_log_group_and_namespace():
    class MetricFilters:
        def __init__(self,group=None):
            self.group=group
        def describe_metric_filters(self,**kwargs):
            assert kwargs["logGroupName"]=="/aws/lambda/stocklens-st-session-watchdog"
            expected=("MissedSessions","WatchdogFailClosed","WatchdogHeartbeat",
                      "MissingOrLateScheduledSignals","BookHalted",
                      "SchedulerStateMismatch","InvalidReceipts","ConfigurationError")
            group=self.group or kwargs["logGroupName"]
            return {"metricFilters":[{
                "logGroupName":group,
                "filterPattern":"{ $.metrics."+name+" = * }",
                "metricTransformations":[{
                    "metricName":name,"metricNamespace":"StockLens/IsolatedST",
                    "metricValue":"$.metrics."+name,
                }]
            } for name in expected]}
    good=f.isolated_metric_origins(MetricFilters(),"stocklens-st-session-watchdog")
    assert good["status"]=="ISOLATED_ST_FILTERS_VERIFIED"
    bad=f.isolated_metric_origins(MetricFilters("/aws/lambda/old-staging"),"stocklens-st-session-watchdog")
    assert bad["status"]=="ST_ISOLATION_INCOMPLETE_OR_UNVERIFIED"
