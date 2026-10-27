#!/usr/bin/env bash
# Existing Conda environment only. No install, reset, credentials or model download.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/backend${PYTHONPATH:+:$PYTHONPATH}"
if [[ -n "${CC_PYTHON:-}" ]]; then
  exec "$CC_PYTHON" -m cc_api.evaluation_launcher "$@"
fi
if ! command -v conda >/dev/null 2>&1; then
  echo 'Conda not found. Use the existing cc-m1 environment or set CC_PYTHON to its Python executable.' >&2
  exit 127
fi
exec conda run --no-capture-output -n "${CC_CONDA_ENV:-cc-m1}" python -m cc_api.evaluation_launcher "$@"
