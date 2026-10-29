"""Strict offline watchdog heartbeat diagnosis tests; never invoke or mutate AWS."""
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import subprocess

import pytest
from infra.aws import stocklens_st_heartbeat_readonly as a

NOW=datetime(2026,10,29,20,11,tzinfo=timezone.utc)
CREATED=datetime(2026,10,29,20,2,tzinfo=timezone.utc)

class Sts:
    def get_caller_identity(self):return {"Account":a.ACCOUNT}

class CF:
    def describe_stacks(self,StackName):
        assert StackName==a.STACK
        return {"Stacks":[{"StackStatus":"UPDATE_COMPLETE","Outputs":[
            {"OutputKey":"CandidateSessionWatchdogFunctionName","OutputValue":a.EXPECTED_FNC},
            {"OutputKey":"CandidatePaperOnlyRuleName","OutputValue":"st-paper"},
            {"OutputKey":"CandidateOrchestratorRuleName","OutputValue":"st-orch"},
            {"OutputKey":"CandidateSignalOnlyRuleName","OutputValue":"st-signal"}]}]}
    def describe_stack_resource(self,StackName,LogicalResourceId):
        assert StackName==a.STACK
        return {"StackResourceDetail":{"PhysicalResourceId":{
            a.LOG_ID:a.EXPECTED_LOG,a.RULE_ID:"st-watchdog-hourly",
            a.ALARM_ID:"st-heartbeat-alarm"
        }[LogicalResourceId]}}

class Events:
    def describe_rule(self,Name):
        return {"State":"DISABLED" if Name in ("st-paper","st-orch") else "ENABLED",
                "ScheduleExpression":"rate(1 hour)" if Name=="st-watchdog-hourly" else None}
    def list_targets_by_rule(self,Rule):
        assert Rule=="st-watchdog-hourly"
        return {"Targets":[{"Arn":"arn:aws:lambda:eu-central-1:634740393398:function:"+a.EXPECTED_FNC}]}

class Lambda:
    def get_function_configuration(self,FunctionName):
        assert FunctionName==a.EXPECTED_FNC
        return {"State":"Active","LastUpdateStatus":"Successful",
                "FunctionArn":"arn:aws:lambda:eu-central-1:634740393398:function:"+a.EXPECTED_FNC}

class Logs:
    def __init__(self,post_at=None):self.post_at=post_at
    def describe_metric_filters(self,**kw):
        assert kw["logGroupName"]==a.EXPECTED_LOG
        return {"metricFilters":[{
            "filterName":a.FILTER_NAME,"logGroupName":a.EXPECTED_LOG,
            "creationTime":int(CREATED.timestamp()*1000),
            "filterPattern":"{ $.metrics.WatchdogHeartbeat = * }",
            "metricTransformations":[{
                "metricName":a.METRIC,"metricNamespace":a.LOG_METRIC_NAMESPACE,
                "metricValue":"$.metrics.WatchdogHeartbeat"}]}]}
    def filter_log_events(self,**kw):
        assert kw["logGroupName"]==a.EXPECTED_LOG
        assert kw["filterPattern"]=="{ $.metrics.WatchdogHeartbeat = * }"
        if self.post_at is None: return {"events":[]}
        return {"events":[{
            "eventId":"e1",
            "timestamp":int(self.post_at.timestamp()*1000),
            "message":json.dumps({"metrics":{"WatchdogHeartbeat":1,
                "WatchdogFailClosed":0},"status":"PASS","failures":[]})
        }]}

class CW:
    def __init__(self,points=False,alarm="ALARM"):
        self.points=points;self.alarm=alarm
    def describe_alarms(self,AlarmNames):
        assert AlarmNames==["st-heartbeat-alarm"]
        return {"MetricAlarms":[{
            "Namespace":a.LOG_METRIC_NAMESPACE,"MetricName":a.METRIC,
            "TreatMissingData":"breaching","Period":3600,
            "EvaluationPeriods":3,"ActionsEnabled":True,
            "StateValue":self.alarm,"StateReason":"missing data"}]}
    def get_metric_statistics(self,**kw):
        assert kw["Namespace"]==a.LOG_METRIC_NAMESPACE
        assert kw["MetricName"]==a.METRIC
        return {"Datapoints":[{"Timestamp":NOW,"SampleCount":1.0,"Maximum":1.0}]
                if self.points else []}

def clients(*,post_at=None,points=False,alarm="ALARM"):
    return {"sts":Sts(),"cloudformation":CF(),"events":Events(),
            "lambda":Lambda(),"logs":Logs(post_at),
            "cloudwatch":CW(points,alarm)}

def test_python_compilation_and_no_write_methods():
    subprocess.run(["python","-m","py_compile",
                    "infra/aws/stocklens_st_heartbeat_readonly.py"],check=True)
    code=Path("infra/aws/stocklens_st_heartbeat_readonly.py").read_text()
    for op in (".invoke(", ".put_metric_data(", ".put_object(",
               ".put_metric_alarm(", ".set_alarm_state(", ".enable_rule(",
               ".update_stack(", ".execute_change_set(", ".create_change_set("):
        assert op not in code

def test_filter_is_fresh_no_new_log_yet_not_false_failure():
    report=a.inspect(clients(),NOW)
    assert report["verdict"]=="AWAITING_FIRST_POST_FILTER_HOURLY_WATCHDOG"
    assert report["watchdog_reports_last_6h"]==0
    assert report["metric_filter_created_utc"]==CREATED.isoformat()
    assert report["st_paper_orchestrator"]=="DISABLED"
    assert report["broker_actions"] is False

def test_missing_new_log_after_85_minutes_is_definite_blocker():
    report=a.inspect(clients(),CREATED+timedelta(minutes=90))
    assert report["verdict"]=="WATCHDOG_POST_FILTER_LOG_MISSING_INVESTIGATE"

def test_fresh_log_with_metric_and_recovered_alarm_is_verified():
    post=CREATED+timedelta(minutes=21)
    report=a.inspect(clients(post_at=post,points=True,alarm="OK"),
                     post+timedelta(minutes=3))
    assert report["verdict"]=="HEARTBEAT_LIVE_AND_ALARM_OK"
    assert report["watchdog_reports_last_6h"]==1
    assert report["last_post_filter_report"]["watchdog_status"]=="PASS"
    assert report["isolated_metric_datapoints_last_6h"][0]["samples"]==1.0

def test_log_after_filter_before_metric_publication():
    post=CREATED+timedelta(minutes=21)
    report=a.inspect(clients(post_at=post,points=False),post+timedelta(minutes=3))
    assert report["verdict"]=="LOG_PRESENT_METRIC_PUBLICATION_PENDING"

def test_new_log_but_no_metric_after_publication_grace_is_failure():
    post=CREATED+timedelta(minutes=21)
    report=a.inspect(clients(post_at=post),post+timedelta(minutes=32))
    assert report["verdict"]=="LOG_PRESENT_BUT_ISOLATED_METRIC_MISSING_INVESTIGATE"

def test_new_log_with_metric_but_alarm_still_evaluating():
    post=CREATED+timedelta(minutes=21)
    report=a.inspect(clients(post_at=post,points=True),post+timedelta(minutes=3))
    assert report["verdict"]=="HEARTBEAT_REPORTED_ALARM_STILL_EVALUATING"

def test_wrong_account_blocks_even_read_only():
    c=clients()
    c["sts"].get_caller_identity=lambda:{"Account":"000000000000"}
    with pytest.raises(RuntimeError,match="WRONG_ACCOUNT"):
        a.inspect(c,NOW)
