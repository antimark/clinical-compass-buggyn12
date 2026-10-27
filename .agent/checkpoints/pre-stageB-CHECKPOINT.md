# Resumable checkpoint — Phase 2 IN_PROGRESS

Source checkpoint: **eb64d3f** (local Git initialized after private source backup). Subagents 0/4. Overall READY: **NOT_READY** pending rehearsal, parity and actual Docker verification. Do not restart discovery.

Completed:
- Phase 0: full source 618 PASS / 5 XFAIL / 0 FAIL (raw/source-regression.log). Live four forms, guest login/register saves/history/retry/tab isolation and 77 medicine DOM field checks PASS (95-case batch + four live server-negative cases). All eight role scenarios passed in recorded batches, including Qwen extraction/evidence/review/draft/referral, patient/doctor Qwen chats, consent-controlled patient FIO/revoke, staff full name, researcher filter/CSV and appointment/message/check-in flow.
- Native server restart retained actual patient session, saved score/history and stable private keys. Private Playwright trace captured; redacted timeline shared. Inventory: 83 read-only PASS, 5 PARTIAL, 14 NOT_RUN, no observed 5xx/page-exception dead end in traversed final routes. Not exhaustive action acceptance.
- Phase 1: run 20261027T151022Z, 335 ordinary HTTP samples / zero unexpected API errors; task n=3 each; one real Qwen chat 10.279s wall, ~19.48 generated tokens/s. See reports/phase1/PERFORMANCE_REPORT.md and LOAD_REPORT.md. Both initial harness errors (login race, invalid UUID key) retained; successful samples were not rerun.

Preservation: original resumable source archive has 102 routes / 249 API operations (two app.route methods refined into inventory); none removed. reports/phase2/FEATURE_PARITY.csv has 1,871 entries. User forbids hiding/removal/static substitution of working functions in Phases 2/3. Keep experimental and privacy restrictions. Source backup: reports/phase0/raw/source-backup-manifest.json.

Next exact command:
`PYTHONPATH=backend:. /Users/mark/miniforge3/envs/cc-m1/bin/python scripts/jury_rehearsal.py --mode fresh --workspace /private/tmp/clinical-compass-jury-phase2-20261027 --port 8767`
Then restart same workspace with `--mode restart`, verify parity, run full source regression before Phase 3. Native original sandbox still serves on 127.0.0.1:8766; no reset required. Rehearsal server stops itself; private credentials/logs stay in its workspace. Full command logs/raw observations stay under reports/phase2/raw/ after each task.

Disclosed gaps: genuine OIDC/MFA invited staff enrollment not configured; legacy researcher study grants absent; some baseline preview/dynamic actions and reviewed clinical content remain partial/not run. Source XFAILs are retained and not promoted. External source-link availability not verified. These limitations prevent unconditional jury readiness.

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

PHASE 2 GATE REVIEWED: fresh 107 PASS / restart 107 PASS; final source 618 PASS, 5 XFAIL, 0 FAIL. Supplemental catalog search/back, guest wrong-role and other-patient isolation, modal keyboard-focus fix, and actual doctor Qwen/pending-state regression pass. Files/evidence: reports/phase2/REHEARSAL_RESULTS.md, PARITY_STATUS.json, FEATURE_PARITY.csv (1,871 rows), API_REGISTRY.csv (249 actual operations / 213 paths). No 102-route/249-API loss. Full action breadth stays PARTIAL; overall NOT_READY pending Docker proof. Phase 3 now IN_PROGRESS. Native rehearse workspace serves at 127.0.0.1:8767; original native QA also at 8766. Next: read-only local Docker context/version preflight, then safe sidecar namespace build and real smoke. Never touch a remote Docker context or user databases. Subagents 0/4.
Phase 3: local Docker Desktop engine now ready (29.8.1, Compose 5.5.1; Unix desktop-linux context). Exact arm64 Python/Node/Ollama manifests saved. Safe Compose sidecar namespace and non-root Gunicorn app implemented; native loopback provider allowlist unchanged. Linux portability repair retains macOS sips and adds CPU/memory/time-limited Pillow worker; native photo regression 19 PASS. Linux decoder must be tested after build; no container gate yet. Next: `CC_JURY_PORT=8768 docker compose -p ccjuryqa20261027 config`, actual build, explicit model volume setup, real smoke + restart/down-up. Never touch unrelated Docker projects/volumes. Subagents 0/4.
Phase 3 current: default Compose now uses a restricted shared-loopback adapter to native Mac Ollama; actual listener remains 127.0.0.1:11434. CPU sidecar attempt retained separately in compose.cpu.yaml: 180s readiness timeout, not accepted for AI. Docker 110-case live suite and corrected Linux full source suite running; partial stdout preserved. Eleven actual bridge protocol checks PASS. Resume: inspect reports/phase3/raw/container-live.log and linux-source-current.log; never restart successful tests or reset jury_workspace volume. Next after live completion: extra photo/tenant probes, capture durable session/keys, compose down/up without -v, verify. Subagents 0/4.

Priority screenshot packet completed: five real PNG + README + verified ZIP in docs/final_demo/. NLP snapshot expired; actual persisted rule proposals/evidence shown; no active alert pair and no research plot invented. Docker resumes at known 108/110 live results (two AI failures) and Linux 620 PASS/2 launcher FAIL/5XFAIL. Successful tests retained.
HANDOFF A0 2026-10-27T20:19:02.174850+00:00: user requests selective integration of Clinical_Compass_Codex_Handoff_Integration_Docker_2026-10-27.zip, then native/live/container acceptance. Read all required handoff documents. Diagnostic apply-check fails only overlapping main.js/views.js; no patch applied. Preserve current 102 routes/249 APIs and 1871 registry rows. Existing Docker: Linux photo real multipart PASS; foreign-tenant Evaluation guard correctly 401 with consent/revoke PASS; Linux 620PASS + 2 noexec-fixture FAIL (focused 4PASS with exec tmpfs), 5XFAIL. Browser Docker108/110 initially; patient Qwen focused now PASS; extraction remains timeout pending explicit nonthinking/context fix (18 focused unit PASS), final image built and dedicated project restarted without deleting volumes. Next: private key/session durability verify and only failed NLP scenario, plus review historical UX patch. No push authorized.
Stage A selective integration PASS (source/contract level); see reports/phase3/HANDOFF_INTEGRATION.md and HANDOFF_MERGE_MATRIX.csv. Head before Stage A commit 6d7978a, review branch codex/jury-ux-docker-20261027; no push. Subagents 1/4, finished. Fresh native sandbox /private/tmp/clinical-compass-jury-handoff-20261027 serves :8769. Next: new action-level native E2E, then final container integration and bounded measurements. Reuse unaffected prior evidence; do not reset volumes or repeat full discovery.
<!-- live-evidence-phase3:start -->
Latest completed: `tests_e2e/test_handoff_live.py::test_explicit_pair_visibility_enable_and_revoke` (PASS).

Append-only observations (includes baseline failures and reruns; not unique acceptance counts):

- authenticated persisted photo GET + Chromium reload: PASS 1
- live Flask + SQLite + Chromium: FAIL 1
- live Flask + SQLite + Chromium: PASS 137
- real Flask/Ollama missing-model response + Chromium: PASS 1
- real authenticated HTTP; explicit synthetic fixture: PASS 4
- real foreign local identities; Evaluation tenant authentication boundary; explicit current-patient consent + revoke: PASS 1
- real multipart + isolated Linux codec + browser readback: PASS 2
- real multipart upload to running app; old image retained: PASS 4
- real ordinary foreign accounts; explicit current-patient consent + revoke: FAIL 1
- source pytest; not live E2E: PASS 72

Raw: `reports/phase3/raw/scenarios.jsonl`. This automated observation summary does not set the phase gate.
<!-- live-evidence-phase3:end -->

<!-- live-evidence-phase0:start -->
Latest completed: `tests_e2e/test_roles_live.py::test_live_contextual_qwen_chat_and_privacy[patient]` (PASS).

Append-only observations (includes baseline failures and reruns; not unique acceptance counts):

- Chromium layout overflow; not full accessibility audit: PASS 30
- actual browser multipart + macOS sips: PASS 1
- authenticated persisted photo GET + Chromium reload: PASS 1
- live Flask + SQLite + Chromium: FAIL 5
- live Flask + SQLite + Chromium: PASS 298
- live read-only route inventory: BLOCKED 31
- live read-only route inventory: PARTIAL 15
- live read-only route inventory: PASS 83
- real Chromium trace; redacted timeline exported: PASS 1
- real multipart upload to running app; old image retained: PASS 4
- source pytest; not live E2E: FAIL 17
- source pytest; not live E2E: PASS 1986
- source pytest; not live E2E: SKIP 17

Raw: `reports/phase0/raw/scenarios.jsonl`. This automated observation summary does not set the phase gate.
<!-- live-evidence-phase0:end -->
