"""One-and-only operator reviewed release path: static safety contracts, no AWS."""
from pathlib import Path
import subprocess

def test_final_release_shells_are_bash_valid_and_pinned():
    for filename in ("infra/aws/audit_staging_release.sh",
                     "infra/aws/release_staging_once.sh",
                     "infra/aws/enable_staging_paper_only.sh",
                     "infra/aws/enable_staging_signal_only.sh"):
        subprocess.run(["bash", "-n", filename], check=True)
    release=Path("infra/aws/release_staging_once.sh").read_text()
    assert "REQUIRE_EXACT_GREEN_CI_COMMIT_SHA_FOR_RELEASE" in release
    assert "ci_transfer_guard.py" in release
    assert "deploy_independent_staging.sh" in release
    assert "audit_staging_release.sh" in release
    assert release.index("REFUSE_NON_PINNED_RELEASE") < release.index(
        "deploy_independent_staging.sh")
    assert release.index("ci_transfer_guard.py") < release.index(
        "deploy_independent_staging.sh")
    for forbidden in ("aws events enable-rule", "aws cloudformation delete-stack",
                      "aws lambda update-function", "aws s3api put-object"):
        assert forbidden not in release


def test_postdeploy_audit_checks_actual_iam_alarm_budget_and_schedules():
    source=Path("infra/aws/audit_staging_release.sh").read_text()
    for required in (
        "eu-central-1", "CandidatePaperPreflightRole",
        "ReadOnlyStagingPaperPreflight", "s3:GetObject", "s3:ListBucket",
        "PREFLIGHT_POLICY_NOT_READONLY", "CandidateSignalOnlyRuleName",
        "CandidatePaperOnlyRuleName", "CandidateOrchestratorRuleName",
        "CandidateSessionWatchdogSchedule", "MissingOrLateScheduledSignalsAlarm",
        "WatchdogHeartbeatDeadmanAlarm", "CandidatePaperErrorsAlarm",
        "StockLens-Whole-Account-20USD", "STAGING_SNS_EMAIL_UNCONFIRMED",
        "STAGING_RELEASE_INFRA_AUDIT_PASS",
        "REAL_EMAIL_ALARM_DELIVERY_NOT_PROVEN",
        "SECOND_PROVIDER_PARITY_AND_PROSPECTIVE_PAPER_NOT_PROVEN",
    ):
        assert required in source, required
    for forbidden in ("aws events enable-rule", "aws s3api put-object",
                      "aws sns publish", "aws cloudformation deploy",
                      "aws lambda invoke", "aws cloudformation delete-stack"):
        assert forbidden not in source


def test_single_release_all_trading_eventbridge_rules_initially_disabled():
    import yaml
    class Loader(yaml.SafeLoader):
        pass
    Loader.add_multi_constructor(
        "!", lambda ld,suffix,node: suffix+":"+str(node.value))
    resources=yaml.load(
        Path("infra/aws/independent-staging.yaml").read_text(),
        Loader=Loader)["Resources"]
    for name in ("CandidateSignalOnlySchedule","CandidatePaperOnlySchedule",
                 "CandidateOrchestratorSchedule"):
        assert resources[name]["Properties"]["State"]=="DISABLED",name
    assert resources["CandidateSessionWatchdogSchedule"]["Properties"]["State"]=="ENABLED"


def test_system_completion_matrix_does_not_falsely_promote_external_gates():
    doc=Path("docs/STOCKLENS_SYSTEM_COMPLETION.md").read_text()
    for text in ("CODE READY","AWS VERIFIED","EXTERNAL NO-GO",
                 "second", "SNS", "20", "production", "no broker"):
        assert text.lower() in doc.lower()


def test_manual_first_paper_bootstrap_has_strict_dry_run_consent_and_postcommit_audit():
    path="infra/aws/bootstrap_staging_paper_once.sh"
    subprocess.run(["bash","-n",path],check=True)
    script=Path(path).read_text()
    assert "enable_staging_signal_only.sh check" in script
    assert "accept_independent_paper_preflight.sh" in script
    assert "CREATE_PROSPECTIVE_STAGING_PAPER_GENESIS" in script
    assert 'STAGING_PAPER_ONLY' in script
    assert '"bootstrap":true' in script
    assert 'STAGING_PAPER_SCHEDULE_READINESS' in script
    assert 'FIRST_PAPER_GENESIS_AND_FULL_CHAIN_VERIFIED' in script
    assert "PAPER_BOOTSTRAP_NOT_APPROVED_NO_WRITES" in script
    assert script.index("accept_independent_paper_preflight.sh") < script.index(
        '"bootstrap":true')
    assert script.index("CREATE_PROSPECTIVE_STAGING_PAPER_GENESIS") < script.index(
        '"bootstrap":true')
    for dangerous in ("aws events enable-rule","aws cloudformation deploy",
                      "aws iam attach-role-policy","aws s3api put-object",
                      "aws cloudformation delete-stack"):
        assert dangerous not in script
