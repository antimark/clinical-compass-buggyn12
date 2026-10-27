# Phase 3 — IN_PROGRESS; Docker gate NOT_RUN

Native Phase 2 core gate: two 107-case rehearsals PASS; source 618 PASS / 5 XFAIL / 0 FAIL. Full action breadth remains PARTIAL; no route/API removed. Actual source/API map 102 UI routes / 249 operations.

Preflight evidence: raw/preflight.jsonl. Local context desktop-linux uses a local Unix socket; installed Docker Desktop was stopped, then started successfully. Docker engine/client 29.8.1; Compose 5.5.1. Native Ollama confirmed 100% GPU, context 4096; this does not imply container Metal acceleration.

Exact Python 3.11.17, Node 22.23.4 and Ollama 0.40.11 image manifests fetched; raw manifest files retained. Implementation next: shared app/Ollama network namespace, loopback-only host publication, non-root app, private persistent workspace and model volumes, pinned Linux runtime, actual browser and durability verification.

Portability issue discovered before build: profile image normalization depends on macOS sips. Docker must retain this existing function with a bounded Linux decoder, not silently disable photo upload. Native path must remain unchanged and security/metadata stripping must be retested.

No Docker build, Qwen or container journey PASS has been claimed. Subagents 0/4. Raw results append per completed scenario. See .agent/CHECKPOINT.md for next exact command.
Phase 3 current: default Compose now uses a restricted shared-loopback adapter to native Mac Ollama; actual listener remains 127.0.0.1:11434. CPU sidecar attempt retained separately in compose.cpu.yaml: 180s readiness timeout, not accepted for AI. Docker 110-case live suite and corrected Linux full source suite running; partial stdout preserved. Eleven actual bridge protocol checks PASS. Resume: inspect reports/phase3/raw/container-live.log and linux-source-current.log; never restart successful tests or reset jury_workspace volume. Next after live completion: extra photo/tenant probes, capture durable session/keys, compose down/up without -v, verify. Subagents 0/4.
HANDOFF A0 2026-10-27T20:19:02.174850+00:00: user requests selective integration of Clinical_Compass_Codex_Handoff_Integration_Docker_2026-10-27.zip, then native/live/container acceptance. Read all required handoff documents. Diagnostic apply-check fails only overlapping main.js/views.js; no patch applied. Preserve current 102 routes/249 APIs and 1871 registry rows. Existing Docker: Linux photo real multipart PASS; foreign-tenant Evaluation guard correctly 401 with consent/revoke PASS; Linux 620PASS + 2 noexec-fixture FAIL (focused 4PASS with exec tmpfs), 5XFAIL. Browser Docker108/110 initially; patient Qwen focused now PASS; extraction remains timeout pending explicit nonthinking/context fix (18 focused unit PASS), final image built and dedicated project restarted without deleting volumes. Next: private key/session durability verify and only failed NLP scenario, plus review historical UX patch. No push authorized.
Stage A selective integration PASS (source/contract level); see reports/phase3/HANDOFF_INTEGRATION.md and HANDOFF_MERGE_MATRIX.csv. Head before Stage A commit 6d7978a, review branch codex/jury-ux-docker-20261027; no push. Subagents 1/4, finished. Fresh native sandbox /private/tmp/clinical-compass-jury-handoff-20261027 serves :8769. Next: new action-level native E2E, then final container integration and bounded measurements. Reuse unaffected prior evidence; do not reset volumes or repeat full discovery.

<!-- live-evidence-phase3:start -->
Latest completed: `tests_e2e/test_roles_live.py::test_patient_intake_messages_checkin_and_appointment` (PASS).

Append-only observations (includes baseline failures and reruns; not unique acceptance counts):

- authenticated persisted photo GET + Chromium reload: PASS 1
- live Flask + SQLite + Chromium: FAIL 1
- live Flask + SQLite + Chromium: PASS 153
- real Flask/Ollama missing-model response + Chromium: PASS 1
- real authenticated HTTP; explicit synthetic fixture: PASS 4
- real foreign local identities; Evaluation tenant authentication boundary; explicit current-patient consent + revoke: PASS 1
- real multipart + isolated Linux codec + browser readback: PASS 2
- real multipart upload to running app; old image retained: PASS 4
- real ordinary foreign accounts; explicit current-patient consent + revoke: FAIL 1
- source pytest; not live E2E: PASS 72

Raw: `reports/phase3/raw/scenarios.jsonl`. This automated observation summary does not set the phase gate.
<!-- live-evidence-phase3:end -->

Container load 20261027T204235Z: 1 clients, 1/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 2/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 3/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 4/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 5/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 6/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 7/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 8/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 9/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 10/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 11/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 12/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 13/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 14/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 15/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 16/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 17/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 18/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 19/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 1 clients, 20/20 samples flushed; current peak 1.

Container load 20261027T204235Z: 3 clients, 3/20 samples flushed; current peak 3.

Container load 20261027T204235Z: 3 clients, 6/20 samples flushed; current peak 3.

Container load 20261027T204235Z: 3 clients, 9/20 samples flushed; current peak 3.

Container load 20261027T204235Z: 3 clients, 12/20 samples flushed; current peak 3.

Container load 20261027T204235Z: 3 clients, 15/20 samples flushed; current peak 3.

Container load 20261027T204235Z: 3 clients, 18/20 samples flushed; current peak 3.

Container load 20261027T204235Z: 3 clients, 20/20 samples flushed; current peak 3.

Container load 20261027T204235Z: 5 clients, 5/20 samples flushed; current peak 5.

Container load 20261027T204235Z: 5 clients, 10/20 samples flushed; current peak 5.

Container load 20261027T204235Z: 5 clients, 15/20 samples flushed; current peak 5.

Container load 20261027T204235Z: 5 clients, 20/20 samples flushed; current peak 5.


Stage C PASS (2026-10-27T20:54:24.500399+00:00): final Docker126 distinct pytest E2E cases, real NLP22.194s and patient/doctor chats8.570/8.553s; live photo/negative upload guards; actual down-up + final restart session/keys/forms/plan/messages/photo;60 controlled reads0errors, p9517.85/25.17/28.74ms. Running image487 functional files equal source in both directions;102 routes/249 APIs/no static controls removed; parity1883 rows. See reports/phase3/DOCKER_TEST_REPORT.md, PERFORMANCE_REPORT.md, RUNTIME_SOURCE_MATCH.json and DOCKER_PARITY.csv. Stage D now final documentation/archive verification only. No app code/architecture/model requests remain necessary. Next: final acceptance/status/storyboard/defects, clean source+sanitized evidence ZIP, checksums, local delivery commit. No push authorized. Subagents1/4.


# Clinical Compass — delivery checkpoint (2026-10-27T21:03:05.134415+00:00)

Review branch `codex/jury-ux-docker-20261027`, no push. Commits: checkpointb9d6aa6 / merge6d7978a / A97998fa / B50adacf / Cb611325. Subagents1/4 used, none active.

A/B/C PASS. Native126 and Docker126 distinct pytest E2E cases; real Qwen3 actions in each; both modes retain forms/session/keys/published plan/messages/photo across actual restart. Source618PASS/1Linux-only SKIP/5expectedXFAIL; final packaging22PASS; final frontend source/simulated contracts PASS. Docker60read samples0errors. Runtime487files match current functional source;102routes/249APIs/no original controls removed,1883parity rows. Reports: reports/FINAL_JURY_READINESS.md, phase0/HANDOFF_NATIVE_RESULTS.md, phase3/DOCKER_TEST_REPORT.md and PERFORMANCE_REPORT.md.

D DELIVERY PREPARED; final archive smoke/verification next. Source+instructions ZIP must use a clean reviewed Git commit, no DB/secrets/actor/session files/model weights/private traces. A separate sanitized QA archive and screenshot ZIP are local only. Exact final hashes go in ignored deliverables/RELEASE_CHECKSUMS.json; do not self-reference archive hashes inside the source tree.

Native app left running127.0.0.1:8769; private WS /private/tmp/clinical-compass-jury-handoff-20261027. Docker app healthy127.0.0.1:8768 projectccjuryqa20261027, private clientWS /private/tmp/clinical-compass-jury-docker-client-20261027; same volumes preserved. Coherent patient credentials privately in jury-demo-patient.json. Never ship them or down-v.

Next exact command: existing cc-m1 Python scripts/build_organizer.py --output deliverables/Clinical_Compass_Jury_Source_20261027.zip; verify-only; extract privately and smoke5public cases on new localhost8772/private SQLite, prove manifest revision fallback without.git and evidence bootstrap. This is packaging validation, not a reason to rerun126successes or any Qwen. Then final local checkpoint/commit and final archive checksum verification.

Recommendation READY_WITH_DISCLOSED_LIMITATIONS for the documented local synthetic jury scope. CPU-sidecar model timed out and is not accepted AI mode; accepted restricted native host GPU bridge proved. Seven conditional routes/four guarded/partial baseline routes and broad action breadth remain explicit; no feature hidden/removed. Clinical/public deployment not approved. Storyboard only; no video/Drive replacement. Master publication requires explicit operator approval.


# Clinical Compass — completed local handoff (2026-10-27T21:07:12.811526+00:00)

Review branch codex/jury-ux-docker-20261027. A97998fa, B50adacf, Cb611325, documentation9ed2803; final delivery/checkpoint commit follows. No push, master not overwritten. Subagents1/4, finished.

A/B/C/D achieved for the documented local synthetic jury scope. Native126 and Docker126 distinct pytest E2E PASS; real Qwen3actions each; actual photo/ACL/negative inputs/clipboard; restart retained session/keys/forms/published plan/messages/photo. Full source618PASS/1Linux-only SKIP/5expectedXFAIL; package/privacy22PASS; final frontend source/simulated contracts PASS. Docker60 reads0errors. Functional runtime/source487files match. Source parity102routes/249APIs/no original controls removed;1883registry rows. Broader action coverage remainsPARTIAL.

Clean initial source archive validated/extracted without.git and launched from fresh private SQLite on8772;5 real smoke cases PASS, manifest revision fallback and evidence bootstrap PASS. Sanitized evidence ZIP CRC/per-file hashes verified. Final source ZIP is rebuilt/verified from this final checkpoint commit; exact SHA256/commit/file counts live in ignored deliverables/RELEASE_CHECKSUMS.json, avoiding self-referential hashes.

Deliverables: deliverables/Clinical_Compass_Jury_Source_20261027.zip; deliverables/Clinical_Compass_Jury_QA_Sanitized_20261027.zip; docs/final_demo/Clinical_Compass_Final_Screenshots_20261027.zip. Reports: reports/FINAL_JURY_READINESS.md, phase3/DOCKER_TEST_REPORT.md, PERFORMANCE_REPORT.md, ARCHIVE_VALIDATION.md, TRACE_MANIFEST.json, DOCKER_PARITY.csv; phase0/HANDOFF_NATIVE_RESULTS.md. Raw historical failures preserved locally, not shipped with private content.

Working apps left running: native http://127.0.0.1:8769/#/demo/journeys, private WS /private/tmp/clinical-compass-jury-handoff-20261027; Docker http://127.0.0.1:8768/#/demo/journeys, projectccjuryqa20261027, private client WS /private/tmp/clinical-compass-jury-docker-client-20261027. Private coherent account file jury-demo-patient.json, ordinary role file jury-actors.json. Never distribute them. Same workspace/project resumes without reset.

Next reproducible action: review docs/phase04/JURY_RUNBOOK.md and DOCKER_JURY_RUNBOOK.md, open an already running app; if stopped use CC_PYTHON=/Users/mark/miniforge3/envs/cc-m1/bin/python bash scripts/evaluation.sh serve --workspace /private/tmp/clinical-compass-jury-handoff-20261027 --port 8769, or CC_JURY_PORT=8768 docker compose -p ccjuryqa20261027 up -d. Do not rerun successful full audits just to resume. No development blocker remains in tested core; broader conditional paths/clinical rights/actual OIDC/MFA/legacy study grants remain disclosed, CPU-sidecar inferenceBLOCKEDoptional. Accepted restricted Mac host-GPU topology proved; no model allowlist expansion/cloud substitution.

Recommendation READY_WITH_DISCLOSED_LIMITATIONS for the exact localhost synthetic script. Clinical/public deployment and exhaustive control acceptance not approved. Storyboard only, no recording/Drive update. Proposed publication after review: git push -u origin codex/jury-ux-docker-20261027; no master push/merge without explicit approval.
