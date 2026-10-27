# Active execution plan — Clinical Compass jury release

Coordinator owns architecture/migrations/shared scripts/tests/integration/packaging. Subagents used **0/4**. Existing clinical/privacy/source/tenant/consent/CSRF/version gates stay mandatory.

User amendment: preserve every implemented function through Phases 2/3. Never remove, hide, disable or replace a working feature with a static stub to improve the demo. Fix or revert regressions. Retain original reports and successful measurements; resume unfinished cases. Full parity registry: reports/phase2/FEATURE_PARITY.csv, currently 1,871 rows. Original archive has 102 UI routes and **249 API operations** (refined from 232 to include GET+PUT declared through app.route); all retained.

- Phase 0 core native gate PASS, breadth PARTIAL: 618 source PASS / 5 XFAIL / 0 FAIL; 99 guest/catalog/server-negative checks and all eight role scenarios individually passed after necessary repairs. Route read inventory 83 PASS / 5 PARTIAL / 14 NOT_RUN. No blanket E2E claim. Evidence reports/phase0/TEST_REPORT.md, BUGS.csv and raw logs.
- Phase 1 MEASURED: run 20261027T151022Z, 335 ordinary HTTP samples / 0 unexpected errors; nine successful scripted tasks, one retained harness race; real app Qwen chat PASS, n=1, 10.279s wall. Bounded load 1/3/5 virtual users, global 2 RPS; no mutation/parallel AI load. Raw data and failures retained. Reports: reports/phase1/.
- Phase 2 IN_PROGRESS: two full automated native rehearsals (fresh and restarted workspace), coherent fixture through normal server authority, feature-parity comparison and Phase 0 regression; preserve guarded legacy-study/OIDC functions with explicit limitations and alternate working paths.
- Phase 3 NOT_RUN: only after Phase 2 regression, safe loopback Docker/Ollama design and actual container journey/durability proof, native fallback retained. Never equate image build to readiness.

Backup: /private/tmp/ClinicalCompass-working-source-20261027T145052Z.zip; checksum/file list in reports/phase0/raw/source-backup-manifest.json. Original archive identity in raw/feature-parity-baseline.json. Local Git initialized after backup; tested source checkpoint **eb64d3f**. Private native sandbox /private/tmp/clinical-compass-jury-20261027 (8766); all passwords/keys/cookies/DB outside source, not tracked.

Next actions: fresh Phase 2 rehearsal on a new private workspace/8767, restart replay, full source regression, then Phase 3. Refresh both .agent files every five scenarios/ten minutes, append/fsync raw per completed task. Overall jury verdict remains NOT_READY until all gates reviewed.

<!-- live-evidence-phase2:start -->
Latest completed: `backend/tests/test_contract.py::test_session_required` (PASS).

Append-only observations (includes baseline failures and reruns; not unique acceptance counts):

- live Chromium accessibility spotcheck: PASS 2
- live Chromium keyboard spotcheck: FAIL 1
- live Chromium keyboard spotcheck: PASS 1
- live Flask + SQLite + Chromium: PASS 231
- real authenticated HTTP; explicit synthetic fixture: PASS 8
- source pytest; not live E2E: PASS 615
- source pytest; not live E2E: SKIP 5

Raw: `reports/phase2/raw/scenarios.jsonl`. This automated observation summary does not set the phase gate.
<!-- live-evidence-phase2:end -->

Phase 2 completed for core native candidate with disclosed action breadth limits; source and browser regressions PASS. Actual API inventory refinement now 249, matching original archive and Flask URL map. Phase 3 IN_PROGRESS: inspect only local Docker context, pin runtime/images, preserve loopback-only provider via shared namespace, verify full container journeys and volume durability; keep native launch. Do not claim READY based on build. Evidence and next command in CHECKPOINT.md. No function removal authorized.
Phase 3 partial: image build PASS (raw/docker-build.log, image 5fd50cc...), not acceptance. Native photo regression 19 PASS after adding isolated Linux decoder; container codec tests pending. Exact digest-pinned Python 3.11.17 / Node 22.23.4 / Ollama 0.40.11, non-root app UID10001, stable volume-owned workspace, single Gunicorn worker. Local Docker VM: 8 CPUs / ~8GiB. Next verify runtime libs, bring up only task's Ollama sidecar, populate separate model volume, test real four-role/browser/Qwen and persistence. Native Mac source/functions remain present.
Phase 3 current: default Compose now uses a restricted shared-loopback adapter to native Mac Ollama; actual listener remains 127.0.0.1:11434. CPU sidecar attempt retained separately in compose.cpu.yaml: 180s readiness timeout, not accepted for AI. Docker 110-case live suite and corrected Linux full source suite running; partial stdout preserved. Eleven actual bridge protocol checks PASS. Resume: inspect reports/phase3/raw/container-live.log and linux-source-current.log; never restart successful tests or reset jury_workspace volume. Next after live completion: extra photo/tenant probes, capture durable session/keys, compose down/up without -v, verify. Subagents 0/4.

Priority screenshot packet completed: five real PNG + README + verified ZIP in docs/final_demo/. NLP snapshot expired; actual persisted rule proposals/evidence shown; no active alert pair and no research plot invented. Docker resumes at known 108/110 live results (two AI failures) and Linux 620 PASS/2 launcher FAIL/5XFAIL. Successful tests retained.

<!-- live-evidence-phase3:start -->
Latest completed: `tests_e2e/test_roles_live.py::test_doctor_real_qwen_evidence_manual_note_and_referral` (FAIL).

Append-only observations (includes baseline failures and reruns; not unique acceptance counts):

- live Flask + SQLite + Chromium: FAIL 1
- live Flask + SQLite + Chromium: PASS 8
- real Flask/Ollama missing-model response + Chromium: PASS 1
- source pytest; not live E2E: PASS 72

Raw: `reports/phase3/raw/scenarios.jsonl`. This automated observation summary does not set the phase gate.
<!-- live-evidence-phase3:end -->
