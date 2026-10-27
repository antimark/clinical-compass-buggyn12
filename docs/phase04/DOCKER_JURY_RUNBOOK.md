# Docker jury launch — Apple Silicon / local Qwen

Use Docker Desktop on this Mac and native loopback Ollama. The default `compose.yaml` uses a reviewed fixed host-gateway adapter sharing the application's loopback namespace. It does not publish Ollama. `LocalOllamaProvider` still permits loopback only. Security design: [review](DOCKER_LOCAL_MODEL_SECURITY_REVIEW.md).

From the source directory, with native Ollama running on `127.0.0.1:11434`:

```bash
# Existing model: no weights in the source/image. Pull only if absent.
ollama list
# If required: ollama pull qwen3:4b-instruct
python3 docker/warm_native_model.py
export CC_JURY_PORT=8768
# A NEW project name means a fresh isolated database volume; keep the same name to resume.
docker compose -p clinical-compass-jury config --quiet
docker compose -p clinical-compass-jury up --build -d
docker compose -p clinical-compass-jury ps
docker compose -p clinical-compass-jury exec -T app python docker/modelcheck.py
# Explicit synthetic operator setup: ordinary doctor/researcher/clinic-admin, no clinical grants.
docker compose -p clinical-compass-jury exec -T app python tests_e2e/prepare_actors.py --workspace /workspace
docker compose -p clinical-compass-jury exec -T app python -m cc_api.evaluation_launcher privacy-setup --workspace /workspace
docker compose -p clinical-compass-jury restart app
```

Open `http://127.0.0.1:8768/#/demo/journeys`. Use separate browser profiles for roles. Register a synthetic `.test` patient in the UI, then create a recipient-bound doctor invitation and accept its exact scopes explicitly. No relationship or patient identity consent is silently seeded.

Generated operator credentials are private in `/workspace/jury-actors.json`, mode 0600. To inspect them privately on this Mac (never attach or publish this file):

```bash
umask 077
QA_CLIENT="$(mktemp -d /private/tmp/clinical-compass-client.XXXXXX)"
docker compose -p clinical-compass-jury cp app:/workspace/jury-actors.json "$QA_CLIENT/jury-actors.json"
chmod 600 "$QA_CLIENT/jury-actors.json"
# Open this local private file with your editor; do not paste its contents into reports.
```

The tested project name is `ccjuryqa20261027`, port 8768. Its existing volume is a synthetic QA workspace; ordinary `up`/`restart` never resets it. Use the **same project name** for retained sessions, DB and keys. Stop safely with `docker compose -p clinical-compass-jury down`; **do not add `-v`**. For an intentional fresh demo choose a new project name. Deleting a volume is a separate explicit destructive operator action, not part of startup.

First boot applies Alembic migrations to a fresh volume; later boots upgrade without dropping state. Legacy unversioned databases are refused. UID/GID 10001 runs the app; workspace 0700, keys 0600, strict umask, no baked credentials. App WSGI binds inside the container; host publication stays `127.0.0.1`. Readiness of the web app and installation/response of the model are distinct checks.

Model pin: `qwen3:4b-instruct`, digest `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`. The warmup validates this digest, emits one harmless token, and requests a 30-minute keep-alive. Heavy inference is serialized; avoid overlapping benchmark/test runs with a live demo. NLP extraction uses explicit nonthinking structured output, context 4096, exact evidence validation and the existing 45-second budget. Timeout/fallback is shown honestly and never counts as successful Qwen.

## CPU sidecar alternative

`compose.cpu.yaml` retains an independent Linux Ollama volume, pinned server 0.40.11, context 4096 and no public model port. It does not inherit native Mac weights:

```bash
CC_JURY_PORT=8770 docker compose -f compose.cpu.yaml -p clinical-compass-cpu up --build -d
CC_JURY_PORT=8770 docker compose -f compose.cpu.yaml -p clinical-compass-cpu exec ollama ollama pull qwen3:4b-instruct
```

On this Mac the CPU sidecar model installed with the correct digest but the actual 180-second readiness generation timed out (model load alone 111.73 seconds). **This is a retained diagnostic alternative, not the accepted AI demo mode.** Native Mac Ollama uses Metal; the Docker web app reaches that native server via the restricted adapter. Do not compare CPU-sidecar timings with native/GPU-bridge results as if they were the same topology. Do not expose host Ollama on all interfaces or substitute a cloud model.

## Replay checks

Real browser tests run on the host against the container app, using the existing cc-m1/Chromium. Prepare private client actor files as above; new tests needing a second physician use `tests_e2e/prepare_handoff_actors.py` inside the volume, then privately copy its `jury-second-doctor.json`. Provisioning creates no patient grant. The tests register/consent through normal APIs/UI.

```bash
PATH=/Users/mark/miniforge3/envs/cc-m1/bin:$PATH \
PYTHONPATH=backend:. CC_QA_PHASE=3 CC_QA_CONTAINER=1 \
CC_QA_WORKSPACE="$QA_CLIENT" CC_E2E_BASE_URL=http://127.0.0.1:8768 \
/Users/mark/miniforge3/envs/cc-m1/bin/python -m pytest -q \
  tests_e2e/test_jury_live.py tests_e2e/test_roles_live.py tests_e2e/test_handoff_live.py
```

Do not repeatedly run a full suite to repair a single failed case. Raw evidence appends per case. Full traces and credentials remain private; only sanitized manifests/timelines are distributed. See the final report for commands actually executed, results and remaining limitations.
