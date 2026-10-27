#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${CC_CONDA_ENV:=clinical-compass}"
command -v conda >/dev/null || { echo 'Conda is required' >&2; exit 2; }
exec conda run --no-capture-output -n "$CC_CONDA_ENV" python scripts/validate_full.py "$@"
