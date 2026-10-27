#!/usr/bin/env bash
# Start the synthetic-only Flask demo via a named Conda environment.
# Run `conda env create -f environment.yml` once from the repository root.
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v conda >/dev/null 2>&1; then
  echo 'ERROR: conda not found. Install Miniconda/Miniforge and initialize your shell.' >&2
  echo 'Then run: conda env create -f environment.yml' >&2
  exit 127
fi
CC_CONDA_ENV="${CC_CONDA_ENV:-clinical-compass}"
export CC_DEMO_MODE=1
export CC_APP_ENV="${CC_APP_ENV:-synthetic_dev}"
# Only the explicitly chosen synthetic development profile enables the already
# implemented clinical evaluation APIs; server still checks role/consent/CSRF.
if [ "$CC_APP_ENV" = "synthetic_dev" ]; then
  for flag in CI_API_V1 CI_REVIEW_V1 CI_PROPOSALS_V1 CI_REFERRALS_V1 CI_CHAT_V1 CI_SAFETY_V1; do
    key="CC_$flag"
    if [ -z "${!key+x}" ]; then export "$key=1"; fi
  done
fi
# For repeatable browser sessions across server restarts, set CC_SECRET_KEY yourself.
export CC_SECRET_KEY="${CC_SECRET_KEY:-$(conda run -n "$CC_CONDA_ENV" python -c 'import secrets; print(secrets.token_urlsafe(48))')}"
export CC_DB_PATH="${CC_DB_PATH:-$PWD/backend/data/dev.sqlite}"
export CC_PORT="${CC_PORT:-8000}"
export CC_PUBLIC_BASE_URL="${CC_PUBLIC_BASE_URL:-http://127.0.0.1:${CC_PORT}}"
export PYTHONPATH="$PWD/backend${PYTHONPATH:+:$PYTHONPATH}"
echo "Synthetic-only Clinical Compass demo; Conda environment: $CC_CONDA_ENV"
echo "Live UI: http://127.0.0.1:${CC_PORT}/"
echo 'Reference UX: /Clinical_Compass_v06_Interactive.html; API Lab: /api-lab.html'
exec conda run --no-capture-output -n "$CC_CONDA_ENV" python backend/run.py
