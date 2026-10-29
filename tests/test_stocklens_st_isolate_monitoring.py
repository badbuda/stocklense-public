"""Regression and red-team tests for ST CloudWatch metric isolation deployment."""
import json
import pytest
from pathlib import Path
import subprocess

from infra.aws import stocklens_st_isolate_monitoring as m


def template_yaml():
    alarms=""
    for logical,metric in m.METRICS.items():
        alarms+=(
            f"  {logical}:\n"
            "    Type: AWS::CloudWatch::Alarm\n"
            "    Properties:\n"
            f"      Namespace: {m.ORIGINAL_NAMESPACE}\n"
            f"      MetricName: {metric}\n"
            "      Statistic: Maximum\n"
            "      AlarmActions: [!Ref CandidateAlerts]\n"
        )
    return (
        "AWSTemplateFormatVersion: '2010-09-09'\n"
        "Description: 'candidate'\n"
        "Resources:\n"
        "  CandidateSessionWatchdogLogs:\n"
        "    Type: AWS::Logs::LogGroup\n"
        "    Properties:\n"
        "      RetentionInDays: 14\n"
        "  CandidateLambda:\n"
        "    Type: AWS::Lambda::Function\n"
        "    Properties:\n"
        "      Handler: infra.aws.independent_pipeline.handler\n"
        +alarms+
        "Outputs:\n"
        "  CandidateAlertsTopic:\n"
        "    Value: !Ref CandidateAlerts\n"
    )


def json_template():
    r={"CandidateSessionWatchdogLogs":{"Type":"AWS::Logs::LogGroup"},
       "CandidateLambda":{"Type":"AWS::Lambda::Function",
                          "Properties":{"Handler":"frozen.original"}}}
    for logical,metric in m.METRICS.items():
        r[logical]={"Type":"AWS::CloudWatch::Alarm",
                    "Properties":{"Namespace":m.ORIGINAL_NAMESPACE,
                                  "MetricName":metric,
                                  "AlarmActions":[{"Ref":"CandidateAlerts"}],
                                  "Statistic":"Maximum"}}
    return {"AWSTemplateFormatVersion":"2010-09-09","Resources":r,
            "Outputs":{"KeepUnchanged":{"Value":True}}}


def test_script_compiles():
    subprocess.run(["python","-m","py_compile",
                    "infra/aws/stocklens_st_isolate_monitoring.py"],check=True)


def test_yml_patches_exactly_eight_alarms_and_eight_filters_without_mutating_lambda():
    original=template_yaml()
    updated=m.patch_template(original)
    assert updated.startswith("AWSTemplateFormatVersion:")
    assert updated.count("      Namespace: "+m.NEW_NAMESPACE+"\n")==8
    assert updated.count("    Type: AWS::Logs::MetricFilter")==8
    assert updated.count("    Type: AWS::CloudWatch::Alarm")==8
    assert "      Handler: infra.aws.independent_pipeline.handler\n" in updated
    assert updated.endswith("  CandidateAlertsTopic:\n    Value: !Ref CandidateAlerts\n")
    assert "      Namespace: "+m.ORIGINAL_NAMESPACE+"\n" not in updated
    for logical,metric in m.METRICS.items():
        assert updated.count("  "+logical+":\n")==1
        assert updated.count("  "+m.filter_id(metric)+":\n")==1
        assert f"      FilterPattern: '{{ $.metrics.{metric} = * }}'" in updated
        assert f"          MetricValue: '$.metrics.{metric}'" in updated
        assert "      DefaultValue: 0" not in updated
    with pytest.raises(RuntimeError,match="ALARM_YAML_SHAPE_CHANGED"):
        m.patch_template(updated)


def test_json_patches_only_expected_resources():
    original=json_template()
    patched=json.loads(m.patch_template(original))
    assert set(patched["Resources"])-set(original["Resources"]) == {
        m.filter_id(x) for x in m.METRICS.values()}
    assert patched["Resources"]["CandidateLambda"] == original["Resources"]["CandidateLambda"]
    assert patched["Outputs"]==original["Outputs"]
    for name,metric in m.METRICS.items():
        assert patched["Resources"][name]["Properties"]["Namespace"]==m.NEW_NAMESPACE
        f=patched["Resources"][m.filter_id(metric)]
        assert f["Properties"]["MetricTransformations"][0] == {
            "MetricName":metric,"MetricNamespace":m.NEW_NAMESPACE,
            "MetricValue":"$.metrics."+metric}
        assert "DefaultValue" not in f["Properties"]


def test_reject_missing_watchdog_log_group():
    t=template_yaml().replace("CandidateSessionWatchdogLogs:","UnexpectedLogs:")
    with pytest.raises(RuntimeError,match="WATCHDOG_LOG_GROUP_MISSING"):
        m.patch_template(t)


def test_reject_unknown_alarm_namespace_without_tolerance():
    t=template_yaml().replace(m.ORIGINAL_NAMESPACE,"StockLens/Unknown",1)
    with pytest.raises(RuntimeError,match="ALARM_YAML_SHAPE_CHANGED"):
        m.patch_template(t)


def test_reject_alarm_actions_removed():
    t=template_yaml().replace("AlarmActions: [!Ref CandidateAlerts]",
                              "AlarmActions: []",1)
    with pytest.raises(RuntimeError,match="ALARM_YAML_SHAPE_CHANGED"):
        m.patch_template(t)


def test_all_expected_changes_exactly_validated():
    changes=[{"ResourceChange":{
        "LogicalResourceId":logical,
        "Action":"Modify","ResourceType":"AWS::CloudWatch::Alarm",
        "Replacement":"False"}} for logical in m.METRICS]
    changes+=[{"ResourceChange":{
        "LogicalResourceId":m.filter_id(metric),
        "Action":"Add","ResourceType":"AWS::Logs::MetricFilter",
        "Replacement":"False"}} for metric in m.METRICS.values()]
    result={"Status":"CREATE_COMPLETE","ExecutionStatus":"AVAILABLE","Changes":changes}
    assert len(m.validate_changes(result))==16
    extra={**result,"Changes":[*changes,{"ResourceChange":{
        "LogicalResourceId":"CandidateLambda","Action":"Modify",
        "ResourceType":"AWS::Lambda::Function","Replacement":"False"}}]}
    with pytest.raises(RuntimeError,match="UNEXPECTED_CHANGE_SET_RESOURCE"):
        m.validate_changes(extra)
    replace=json.loads(json.dumps(result))
    replace["Changes"][0]["ResourceChange"]["Replacement"]="True"
    with pytest.raises(RuntimeError,match="UNSAFE_CHANGE_SET_ACTION"):
        m.validate_changes(replace)
    missing={**result,"Changes":changes[:-1]}
    with pytest.raises(RuntimeError,match="RESOURCE_COUNT"):
        m.validate_changes(missing)
    pages={**result,"NextToken":"next"}
    with pytest.raises(RuntimeError,match="NOT_READY"):
        m.validate_changes(pages)


def test_read_only_inspection_has_no_mutating_calls():
    text=Path("infra/aws/stocklens_st_isolate_monitoring.py").read_text()
    assert "if args.mode==\"inspect\":" in text
    assert "cf.create_change_set(" in text
    assert "cf.execute_change_set(" in text
    assert "CONSENT" in text
    # There is deliberately no trading, Signal, S3, IAM, Lambda or alarm
    # direct mutation in this operator script. Update is reviewed CF only.
    for forbidden in (
        "put_metric_alarm(", "disable_alarm_actions(",
        "update_function_code(", "update_function_configuration(",
        "put_object(", "enable_rule(", "put_item(",
        "create_stack(", "delete_stack(", "delete_change_set(",
    ):
        assert forbidden not in text
