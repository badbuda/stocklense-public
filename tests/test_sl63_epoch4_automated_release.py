"""Guarded operator ST release, CloudFormation-only; test with NO AWS access."""
from __future__ import annotations
from unittest.mock import Mock
import pytest
from infra.aws import sl63_epoch4_automated_release as r
from infra.aws import sl63_epoch4_stage_dark_deploy as previous
from infra.aws import sl63_epoch4_immutable_store as store


CFG={"Runtime":"python3.13","Architectures":["x86_64"],
     "MemorySize":1024,"Layers":[]}
SNS="arn:aws:sns:eu-central-1:634740393398:known-st-existing-topic"


def test_staged_template_only_adds_approved_readonly_monitoring_resources():
    original=previous.template("deployment/epoch4/dark/old.zip",CFG)
    new=r._new_template("deployment/epoch4/dark/new.zip",CFG,SNS,armed=False)
    assert new["Resources"]["DarkRole"]==original["Resources"]["DarkRole"]
    assert new["Resources"]["DarkLogGroup"]==original["Resources"]["DarkLogGroup"]
    assert new["Resources"]["DarkLambda"]["Properties"]["FunctionName"]==r.FUNCTION
    assert new["Resources"]["DarkLambda"]["Properties"]["Environment"][
        "Variables"]["STOCKLENS_EPOCH4_WRITE_ENABLED"]=="false"
    assert new["Resources"]["DarkLambda"]["Properties"][
        "ReservedConcurrentExecutions"]==1
    assert len(new["Resources"])==12
    assert all(new["Resources"][x]["Properties"]["State"]=="DISABLED"
               for x in ("PaperRule","WatchRule"))
    assert all(new["Resources"][x]["Properties"]["AlarmActions"]==[SNS]
               for x in ("PaperErrorsAlarm","WatchdogErrorsAlarm"))
    assert all(new["Resources"][x]["Properties"]["ActionsEnabled"] is True
               for x in ("PaperErrorsAlarm","WatchdogErrorsAlarm"))


def test_armed_rule_is_clock_driven_and_no_event_date_or_broker():
    t=r._new_template("deployment/epoch4/dark/release.zip",CFG,SNS,armed=True)
    assert t["Resources"]["DarkLambda"]["Properties"]["Environment"][
        "Variables"]["STOCKLENS_EPOCH4_WRITE_ENABLED"]=="true"
    assert t["Resources"]["DarkLambda"]["Properties"]["Environment"][
        "Variables"]["STOCKLENS_EPOCH4_APPROVAL_SHA256"]==r.APPROVAL_SHA
    paper=t["Resources"]["PaperRule"]["Properties"]
    watch=t["Resources"]["WatchRule"]["Properties"]
    assert paper["State"]==watch["State"]=="ENABLED"
    assert paper["ScheduleExpression"]=="cron(30,42,52 23 ? * MON-FRI *)"
    assert watch["ScheduleExpression"]=="cron(59 23 ? * MON-FRI *)"
    assert '"session"' not in paper["Targets"][0]["Input"]
    assert paper["Targets"][0]["RetryPolicy"]["MaximumRetryAttempts"]==0
    assert paper["Targets"][0]["RetryPolicy"]["MaximumEventAgeInSeconds"]==600
    assert t["Outputs"]["BrokerOrdersEnabled"]["Value"]=="false"
    assert t["Outputs"]["SingleVendorOnly"]["Value"]=="true"
    assert not any("prod" in x.lower() for x in t["Resources"])


def test_watchdog_iam_only_reads_new_epoch_cannot_put_any_s3():
    t=r._new_template("artifact",CFG,SNS,armed=True)
    policy=t["Resources"]["WatchdogRole"]["Properties"][
        "Policies"][0]["PolicyDocument"]["Statement"]
    assert all("s3:PutObject" not in x["Action"] for x in policy)
    s3=next(x for x in policy if "s3:GetObject" in x["Action"])
    assert all("/paper/epochs/"+store.EPOCH+"/" in arn for arn in s3["Resource"])
    assert all("/paper/sessions/" not in arn for arn in s3["Resource"])
    assert all(x["Properties"]["Principal"]=="events.amazonaws.com"
               for n,x in t["Resources"].items()
               if n.endswith("Permission"))


def test_existing_alarm_topic_requires_one_unambiguous_confirmed_st_arn():
    class CW:
        def __init__(self,targets):self.targets=targets
        def describe_alarms(self,**kwargs):
            return {"MetricAlarms":[{"AlarmActions":self.targets}],"NextToken":None}
    assert r.chosen_existing_alert_topic(CW([SNS]))==SNS
    with pytest.raises(RuntimeError,match="NO_UNAMBIGUOUS_EXISTING_ST_SNS"):
        r.chosen_existing_alert_topic(CW([]))
    with pytest.raises(RuntimeError,match="NO_UNAMBIGUOUS_EXISTING_ST_SNS"):
        r.chosen_existing_alert_topic(CW([SNS,
          "arn:aws:sns:eu-central-1:634740393398:another-topic"]))
    with pytest.raises(RuntimeError,match="NO_UNAMBIGUOUS_EXISTING_ST_SNS"):
        r.chosen_existing_alert_topic(CW([
          "arn:aws:sns:eu-central-1:000000000000:external"]))


def test_change_set_rejects_delete_or_iam_role_mutation_before_execution():
    class Wait:
        def wait(self,**kw):pass
    class CFN:
        def __init__(self,logical,action,replacement):
            self.logical,self.action,self.replacement=logical,action,replacement
            self.execute_count=0
        def create_change_set(self,**kw):pass
        def get_waiter(self,name):return Wait()
        def describe_change_set(self,**kw):
            return {"Status":"CREATE_COMPLETE","Changes":[
                {"ResourceChange":{"Action":self.action,
                 "LogicalResourceId":self.logical,
                 "Replacement":self.replacement}}]}
        def execute_change_set(self,**kw):self.execute_count+=1
    for logical,action,replacement in (
        ("DarkRole","Modify","False"),("DarkLambda","Remove","False"),
        ("DarkLambda","Modify","True"),("Unknown","Add","False")):
        cfn=CFN(logical,action,replacement)
        with pytest.raises(RuntimeError):
            r._change_set({"cloudformation":cfn},{}, "test",stage=True)
        assert cfn.execute_count==0


def test_unknown_error_no_write_before_server_mutation_and_no_broker_import():
    import inspect
    src=inspect.getsource(r)
    assert "broker.send" not in src
    assert "update_function_code" not in src
    assert "enable_rule" not in src
    assert "delete_stack" not in src
    assert "delete_object" not in src
    assert 'FIRST_SESSION_ALREADY_CLOSED_DO_NOT_BACKFILL' in src
    assert r.EXPECTED_DARK_SHA=="F3Wrv/yAY+A23ikG5IlfRq0QiZO2xfffeMOsMmkfefA="
