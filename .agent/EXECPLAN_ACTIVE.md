# Clinical Compass — execution plan (2026-10-27T20:39:53.964331+00:00)

Branch `codex/jury-ux-docker-20261027`; no push. Baseline GitHub c86c09f / fetched675ce74, checkpoint b9d6aa6, merge6d7978a, Stage A97998fa. Subagents **1/4 used**, none active.

- Stage A PASS: selective historical UX port, no force/overwrite. reports/phase3/HANDOFF_INTEGRATION.md and HANDOFF_MERGE_MATRIX.csv.
- Stage B PASS: native126 distinct browser cases +6 real photo observations; full source618PASS/1Linux-only SKIP/5expectedXFAIL, zero unexpected failure. reports/phase0/HANDOFF_NATIVE_RESULTS.md and raw JUnit/logs. Failed harness attempts retained; only affected cases retested.
- Stage C IN_PROGRESS: post-UX Docker117 core/new cases PASS, previous real Linux photo/invalid inputs/persistent state PASS; final history/behavioral2cases and four-role8 incl actualQwen remain. Default nonpublic Mac host-GPU bridge; CPU sidecar readiness timeout retained, never accepted as AI.
- Stage D PENDING: final parity, trace manifest, measured Docker load, runbooks, readiness and clean source archive.

Native private WS `/private/tmp/clinical-compass-jury-handoff-20261027` on8769. Docker dedicated project `ccjuryqa20261027`, port8768; private client files `/private/tmp/clinical-compass-jury-docker-client-20261027`. Do not reset volumes, copy credentials to source, alter clinical ACL, or rerun successful full suites.

Next exact action: run final Docker `tests_e2e/test_roles_live.py` + only two affected history/behavioral tests, env `CC_QA_PHASE=3 CC_QA_CONTAINER=1 CC_QA_WORKSPACE=/private/tmp/clinical-compass-jury-docker-client-20261027 CC_E2E_BASE_URL=http://127.0.0.1:8768 PYTHONPATH=backend:.`, existing cc-m1 Python. Then bounded `tests_perf/container_measure.py`, actual volume key/session/photo readback, parity + source packaging.

Current architecture, migrations, global scripts, integration and tests owned by coordinator. Functional preservation: 102 routes /249 APIs baseline,1871 original registry rows; new actions to be appended, no removals. Clinical tools remain unapproved/experimental and require physician decisions. Full action breadth is not inferred from route rendering. Previous detailed checkpoint archived under .agent/checkpoints/ and Git. Raw evidence remains append-only.

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


Stage C PASS (2026-10-27T20:54:24.500399+00:00): final Docker126 distinct pytest E2E cases, real NLP22.194s and patient/doctor chats8.570/8.553s; live photo/negative upload guards; actual down-up + final restart session/keys/forms/plan/messages/photo;60 controlled reads0errors, p9517.85/25.17/28.74ms. Running image487 functional files equal source in both directions;102 routes/249 APIs/no static controls removed; parity1883 rows. See reports/phase3/DOCKER_TEST_REPORT.md, PERFORMANCE_REPORT.md, RUNTIME_SOURCE_MATCH.json and DOCKER_PARITY.csv. Stage D now final documentation/archive verification only. No app code/architecture/model requests remain necessary. Next: final acceptance/status/storyboard/defects, clean source+sanitized evidence ZIP, checksums, local delivery commit. No push authorized. Subagents1/4.
