"""Guard the CloudShell builder against the missing-Python-3.12 regression.

These tests require neither AWS credentials nor PyPI access and run on the
normal CI host. Wheel resolution itself remains a staging deployment gate.
"""
from pathlib import Path
import subprocess


SCRIPT = Path("infra/aws/deploy_independent_staging.sh")


def test_builder_is_valid_bash():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_builder_cross_targets_lambda_cp312_without_local_312():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'PYTHON_BUILD="${PYTHON_BUILD:-python3}"' in source
    assert 'command -v "$PY312"' not in source
    assert '--python-version 3.12 --implementation cp --abi cp312' in source
    assert '--only-binary=:all:' in source
    assert '--platform manylinux2014_x86_64' in source
    assert '--platform manylinux_2_34_x86_64' in source
    assert '--no-cache-dir' in source
    assert 'NON_CP312_NATIVE_WHEELS' in source
    assert '"infra/aws/independent_orchestrator.py"' in source
    assert '"infra/aws/independent_paper.py"' in source


def test_validation_and_local_package_precede_aws_resource_mutations():
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.index('aws cloudformation validate-template') < source.index(
        'aws s3api create-bucket'
    )
    assert source.index('Package contents:') < source.index('aws s3api create-bucket')
    assert 'stocklens-independent-staging' in source
    assert '--no-fail-on-empty-changeset' in source


def test_cloudformation_failure_prints_exact_stack_events_and_does_not_delete():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'show_staging_events()' in source
    assert 'describe-stack-events' in source
    assert 'contains(ResourceStatus' in source
    assert 'ROLLBACK_COMPLETE' in source
    assert 'if ! aws cloudformation deploy' in source
    assert 'show_staging_events\n  echo "STOP:' in source
    assert 'aws cloudformation delete-stack' not in source
    assert 'aws cloudformation continue-update-rollback' not in source

