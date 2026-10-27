#!/usr/bin/env bash
# Export machine- and platform-specific Conda/Python locks from a working env.
# These files are for reproducibility only; NOT a cross-platform Conda lock.
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v conda >/dev/null 2>&1; then
  echo 'Conda is required; create the environment before exporting.' >&2
  exit 127
fi
CC_CONDA_ENV="${CC_CONDA_ENV:-clinical-compass}"
mkdir -p local_locks
conda list -n "$CC_CONDA_ENV" --explicit > local_locks/conda-explicit.txt
conda run --no-capture-output -n "$CC_CONDA_ENV" python -m pip freeze > local_locks/pip-freeze.txt
printf 'Saved machine-specific dependency snapshots in local_locks/\n'
