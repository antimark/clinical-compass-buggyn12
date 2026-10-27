# Phase 0 — INCOMPLETE

Live user scenarios completed: 0. No AI or browser acceptance yet.
Native preflight: 11/11 commands returned successfully with localhost access; initial sandbox denials retained separately. Installed model digest recorded; inference NOT_RUN.
Raw evidence: raw/preflight.jsonl. Source test results will append to raw/scenarios.jsonl via tests_e2e.pytest_evidence.
Remaining: four scored forms, both guest authentication paths and persistence/retry, 77 medicine DOM completeness, four roles, real Qwen, control inventory, security and restart regressions.
Resume: see ../../.agent/CHECKPOINT.md. Source checkout has no Git metadata.

Completed live batch: 13 PASS in `raw/live-guest-run2.log` (8 guest auth/persistence/history paths, 4 required-answer guards, public API/auth contracts). Initial stale-CSRF test-harness failure preserved in sanitized `raw/live-guest-baseline.log`; fixed test navigation, no app security change.
Confirmed app FAIL: lost successful submit response causes duplicate result on retry (`raw/retry-before.log`). Repair adds patient-scoped transfer-key recovery using existing submissions; targeted rerun requires server restart.
Research fixture missing from distribution repaired in `research_data/`; source package allowlist updated. Full source baseline running (`raw/source-baseline.log`).

<!-- measured-progress -->
Latest completed: `inventory /clinic/invitations` (PARTIAL).

Append-only observations (includes baseline failures and reruns; not unique acceptance counts):

- Chromium layout overflow; not full accessibility audit: PASS 30
- live Flask + SQLite + Chromium: FAIL 3
- live Flask + SQLite + Chromium: PASS 153
- live read-only route inventory: BLOCKED 31
- live read-only route inventory: PARTIAL 15
- live read-only route inventory: PASS 83
- real Chromium trace; redacted timeline exported: PASS 1
- source pytest; not live E2E: FAIL 17
- source pytest; not live E2E: PASS 1368
- source pytest; not live E2E: SKIP 12

Raw: `reports/phase0/raw/scenarios.jsonl`. Phase 0 remains INCOMPLETE until all release gates are reviewed.

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
