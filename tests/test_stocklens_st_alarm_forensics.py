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
