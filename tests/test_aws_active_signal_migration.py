"""Static regression guards for active Staging migration; never call AWS."""
from pathlib import Path
import subprocess
import yaml

def test_migration_shell_is_bash_valid_pinned_and_opt_in():
    for name in ("infra/aws/migrate_active_staging_signal.sh",
                 "infra/aws/deploy_independent_staging.sh",
                 "infra/aws/smoke_independent_staging.sh"):
        subprocess.run(["bash","-n",name],check=True)
    script=Path("infra/aws/migrate_active_staging_signal.sh").read_text()
    assert "EXPECTED_STOCKLENS_RELEASE_COMMIT" in script
    assert "ci_transfer_guard.py" in script
    assert "MIGRATE_ACTIVE_STAGING_SIGNAL_ONLY" in script
    assert "enable_staging_signal_only.sh check" in script
    assert script.index("MIGRATE_ACTIVE_STAGING_SIGNAL_ONLY") < script.index(
        "STOCKLENS_ACTIVE_SIGNAL_MIGRATION=1 bash infra/aws/deploy_independent_staging.sh")
    for forbidden in ("aws events enable-rule","aws events disable-rule",
                      "aws cloudformation delete-stack","aws iam attach-role-policy"):
        assert forbidden not in script

def test_live_stack_release_guards_no_unauthorized_paper_or_anchor_reset():
    deploy=Path("infra/aws/deploy_independent_staging.sh").read_text()
    assert "STOCKLENS_ACTIVE_SIGNAL_MIGRATION" in deploy
    assert "MIGRATION_WRONG_AWS_ACCOUNT" in deploy
    assert "MIGRATION_WRONG_STACK_IDENTITY" in deploy
    assert "MIGRATION_SIGNAL_RULE_NOT_ENABLED" in deploy
    assert "MIGRATION_UNEXPECTED_OLD_SIGNAL_SCHEDULE" in deploy
    assert "MIGRATION_UNVERSIONED_SIGNAL_ANCHOR" in deploy
    assert "MIGRATION_PAPER_BOOK_EXISTS_NEEDS_SEPARATE_PROCEDURE" in deploy
    assert "REFUSE_REDEPLOY_ACTIVE_SCHEDULE" in deploy
    assert "REFUSE_REDEPLOY_ESTABLISHED_SIGNAL_MONITOR_ANCHOR" in deploy
    assert "CandidateSignalScheduleState=$SIGNAL_RULE_CF_STATE" in deploy
    assert "STOCKLENS_EXPECT_ENABLED_SIGNAL" in deploy

def test_signal_state_keeps_default_disarmed_but_allows_explicit_active_release():
    class L(yaml.SafeLoader): pass
    L.add_multi_constructor("!",lambda loader,suffix,node:suffix+":"+str(node.value))
    doc=yaml.load(Path("infra/aws/independent-staging.yaml").read_text(),Loader=L)
    param=doc["Parameters"]["CandidateSignalScheduleState"]
    assert param["Default"]=="DISABLED"
    assert param["AllowedValues"]==["DISABLED","ENABLED"]
    r=doc["Resources"]
    assert r["CandidateSignalOnlySchedule"]["Properties"]["State"] == "Ref:CandidateSignalScheduleState"
    assert r["CandidateSignalOnlySchedule"]["Properties"]["ScheduleExpression"]=="cron(30 2 ? * TUE-SAT *)"
    assert r["CandidatePaperOnlySchedule"]["Properties"]["State"]=="DISABLED"
    assert r["CandidateOrchestratorSchedule"]["Properties"]["State"]=="DISABLED"
    assert r["CandidatePaperOnlySchedule"]["Properties"]["ScheduleExpression"]=="cron(20 3 ? * TUE-SAT *)"

def test_authenticated_import_smoke_safeguards():
    smoke=Path("infra/aws/smoke_independent_staging.sh").read_text()
    assert "STOCKLENS_EXPECT_ENABLED_SIGNAL" in smoke
    assert "MIGRATION_ACTIVATION_ANCHOR_LOST" in smoke
    assert "MIGRATION_SIGNAL_SCHEDULE_NOT_UPDATED" in smoke
    assert '"mode":"STAGING_IMPORT_SMOKE"' in smoke
    assert "PAPER_ONLY_NOT_SAFE_BY_DEFAULT" in smoke
    assert "UNSAFE_SCHEDULE_STATE" in smoke
