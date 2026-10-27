# Phase 3 — IN_PROGRESS; Docker gate NOT_RUN

Native Phase 2 core gate: two 107-case rehearsals PASS; source 618 PASS / 5 XFAIL / 0 FAIL. Full action breadth remains PARTIAL; no route/API removed. Actual source/API map 102 UI routes / 249 operations.

Preflight evidence: raw/preflight.jsonl. Local context desktop-linux uses a local Unix socket; installed Docker Desktop was stopped, then started successfully. Docker engine/client 29.8.1; Compose 5.5.1. Native Ollama confirmed 100% GPU, context 4096; this does not imply container Metal acceleration.

Exact Python 3.11.17, Node 22.23.4 and Ollama 0.40.11 image manifests fetched; raw manifest files retained. Implementation next: shared app/Ollama network namespace, loopback-only host publication, non-root app, private persistent workspace and model volumes, pinned Linux runtime, actual browser and durability verification.

Portability issue discovered before build: profile image normalization depends on macOS sips. Docker must retain this existing function with a bounded Linux decoder, not silently disable photo upload. Native path must remain unchanged and security/metadata stripping must be retested.

No Docker build, Qwen or container journey PASS has been claimed. Subagents 0/4. Raw results append per completed scenario. See .agent/CHECKPOINT.md for next exact command.
Phase 3 current: default Compose now uses a restricted shared-loopback adapter to native Mac Ollama; actual listener remains 127.0.0.1:11434. CPU sidecar attempt retained separately in compose.cpu.yaml: 180s readiness timeout, not accepted for AI. Docker 110-case live suite and corrected Linux full source suite running; partial stdout preserved. Eleven actual bridge protocol checks PASS. Resume: inspect reports/phase3/raw/container-live.log and linux-source-current.log; never restart successful tests or reset jury_workspace volume. Next after live completion: extra photo/tenant probes, capture durable session/keys, compose down/up without -v, verify. Subagents 0/4.
HANDOFF A0 2026-10-27T20:19:02.174850+00:00: user requests selective integration of Clinical_Compass_Codex_Handoff_Integration_Docker_2026-10-27.zip, then native/live/container acceptance. Read all required handoff documents. Diagnostic apply-check fails only overlapping main.js/views.js; no patch applied. Preserve current 102 routes/249 APIs and 1871 registry rows. Existing Docker: Linux photo real multipart PASS; foreign-tenant Evaluation guard correctly 401 with consent/revoke PASS; Linux 620PASS + 2 noexec-fixture FAIL (focused 4PASS with exec tmpfs), 5XFAIL. Browser Docker108/110 initially; patient Qwen focused now PASS; extraction remains timeout pending explicit nonthinking/context fix (18 focused unit PASS), final image built and dedicated project restarted without deleting volumes. Next: private key/session durability verify and only failed NLP scenario, plus review historical UX patch. No push authorized.

<!-- live-evidence-phase3:start -->
Latest completed: `tests_e2e/test_roles_live.py::test_doctor_real_qwen_evidence_manual_note_and_referral` (PASS).

Append-only observations (includes baseline failures and reruns; not unique acceptance counts):

- live Flask + SQLite + Chromium: FAIL 1
- live Flask + SQLite + Chromium: PASS 16
- real Flask/Ollama missing-model response + Chromium: PASS 1
- real authenticated HTTP; explicit synthetic fixture: PASS 4
- real foreign local identities; Evaluation tenant authentication boundary; explicit current-patient consent + revoke: PASS 1
- real multipart + isolated Linux codec + browser readback: PASS 2
- real ordinary foreign accounts; explicit current-patient consent + revoke: FAIL 1
- source pytest; not live E2E: PASS 72

Raw: `reports/phase3/raw/scenarios.jsonl`. This automated observation summary does not set the phase gate.
<!-- live-evidence-phase3:end -->


Stage A selective integration PASS (source/contract level); see reports/phase3/HANDOFF_INTEGRATION.md and HANDOFF_MERGE_MATRIX.csv. Head before Stage A commit 6d7978a, review branch codex/jury-ux-docker-20261027; no push. Subagents 1/4, finished. Fresh native sandbox /private/tmp/clinical-compass-jury-handoff-20261027 serves :8769. Next: new action-level native E2E, then final container integration and bounded measurements. Reuse unaffected prior evidence; do not reset volumes or repeat full discovery.
