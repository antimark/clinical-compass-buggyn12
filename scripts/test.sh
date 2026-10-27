#!/usr/bin/env bash
# Run all Python tests and every Node test file in the named Conda environment.
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v conda >/dev/null 2>&1; then
  echo 'ERROR: conda not found. Run conda env create -f environment.yml first.' >&2
  exit 127
fi
CC_CONDA_ENV="${CC_CONDA_ENV:-clinical-compass}"
export PYTHONPATH="$PWD/backend${PYTHONPATH:+:$PYTHONPATH}"
conda run --no-capture-output -n "$CC_CONDA_ENV" python -m compileall -q backend migrations
conda run --no-capture-output -n "$CC_CONDA_ENV" python -m pytest -q
# Shell glob expands to all present suites, including route smoke checks.
conda run --no-capture-output -n "$CC_CONDA_ENV" node --test frontend/dist/tests/*.cjs
conda run --no-capture-output -n "$CC_CONDA_ENV" node --check frontend/dist/assets/js/live_app.js
