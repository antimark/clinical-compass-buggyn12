#!/bin/sh
set -eu
umask 077
# Validate/create only the explicit isolated workspace. No reset or global seed.
python -c 'import os; from cc_api.evaluation_launcher import workspace_config; workspace_config(os.environ.get("CC_WORKSPACE","/workspace"))'
exec "$@"
