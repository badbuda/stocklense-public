#!/usr/bin/env bash
# Run from an operator AWS session. Without the flag, only inspect the source.
set -euo pipefail
cd "$(dirname "$0")/../.."
venv_dir="${STOCKLENS_ST_VENV:-$HOME/.stocklens-st-console-qa/venv}"
if [[ ! -x "$venv_dir/bin/python" ]]; then
  python3 -m venv "$venv_dir"
fi
"$venv_dir/bin/python" -m pip install --quiet -r requirements.txt boto3
exec "$venv_dir/bin/python" -m infra.aws.sl64_epoch5_start "$@"
