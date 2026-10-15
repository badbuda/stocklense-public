#!/usr/bin/env python3
"""Read-only, fail-closed AWS runtime dependency inventory.

Run from AWS CloudShell with boto3 and AWS_REGION=eu-central-1.
No Lambda invocation, no resource mutations, no secrets or source URLs printed.
Exit nonzero while GitHub runtime dependencies remain.
"""
import ast
import io
import os
import sys
import urllib.parse
import urllib.request
import zipfile

import boto3

FUNCTIONS = (
    "stocklens-paper-shadow",
    "stocklens-paper-paper-evidence",
    "stocklens-paper-watchdog",
)
GITHUB_HOSTS = ("raw.githubusercontent.com", "github.com", "api.github.com")


def scan_source(source: str):
    tree = ast.parse(source)
    hosts = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value
            if val.startswith(("https://", "http://")):
                host = urllib.parse.urlsplit(val).hostname
                if host:
                    hosts.add(host.lower())
    # Check dynamic URL construction as well, without printing any URLs.
    github_literal = any(host in source for host in GITHUB_HOSTS)
    return hosts, github_literal


def main():
    client = boto3.client("lambda", region_name=os.environ.get("AWS_REGION", "eu-central-1"))
    failed = False
    for function in FUNCTIONS:
        meta = client.get_function(FunctionName=function)
        config = meta["Configuration"]
        location = meta["Code"]["Location"]
        with urllib.request.urlopen(location, timeout=25) as response:
            data = response.read(30_000_001)
        if len(data) > 30_000_000:
            raise RuntimeError(f"{function}: ZIP too large")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            python_files = [p for p in archive.namelist() if p.endswith(".py")]
            all_hosts = set()
            github_found = False
            for path in python_files:
                hosts, has_github = scan_source(archive.read(path).decode("utf-8"))
                all_hosts |= hosts
                github_found |= has_github
        print(f"{function}: state={config['State']}; "
              f"code_sha256={config['CodeSha256']}; "
              f"python_files={len(python_files)}; "
              f"static_hosts={','.join(sorted(all_hosts)) or '(none)'}; "
              f"github_literal={'YES' if github_found else 'NO'}")
        if github_found:
            failed = True
    if failed:
        print("BLOCKED: at least one deployed Lambda still references GitHub at runtime.")
        return 2
    print("PASS_STATIC_ONLY: no GitHub host literal in deployed Python; "
          "this does NOT prove runtime or upstream producer independence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
