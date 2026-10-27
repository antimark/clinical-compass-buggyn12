# Phase 0 checkpoint — INCOMPLETE

Source: extracted distribution, no .git. Subagents 0/4. READY: NOT_READY (gates untested).
Last completed: native environment preflight. macOS 26.5 arm64, 16 GiB, Python 3.11.17, Node 22.23.4, pytest 9.1.1, Playwright 1.64.1. pip check PASS. Ollama 0.40.11; qwen3:4b-instruct installed, generation NOT_RUN.
Evidence: reports/phase0/raw/preflight.jsonl (sandbox denial and successful elevated localhost rerun preserved).

Next three actions:
1. Focused source baseline and browser launch; log each scenario immediately.
2. Start isolated native sandbox /private/tmp/clinical-compass-jury-20261027, port 8766.
3. Live four-form guest→account tests, then catalog and roles; fix verified blockers.

Resume command: `CC_PYTHON=/Users/mark/miniforge3/envs/cc-m1/bin/python CC_CONDA_ENV=cc-m1 bash scripts/evaluation.sh serve --workspace /private/tmp/clinical-compass-jury-20261027 --port 8766`
Localhost and Chromium require sandbox escalation. No permissions/security gates changed. Phase 1–3 NOT_RUN.

Update: 13 live Chromium checks PASS; transfer retry FAIL reproduced (duplicate rows after real commit + response abort). Changes: guest transfer key on self-assign and patient-scoped completed-submission lookup; missing independent research fixture restored and allowlisted. Focused regression `tests/test_jury_regressions.py` added. Full source suite running; next restart server and run `PYTHONPATH=backend:. /Users/mark/miniforge3/envs/cc-m1/bin/python -m pytest -q -p tests_e2e.pytest_evidence tests_e2e/test_jury_live.py --tb=short` with localhost access. Catalog/browser tests now include 77 individually flushed medicine scenarios.

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

PHASE TRANSITION: Phase 0 core native gate PASS; breadth PARTIAL (83 read-only routes, 5 partial, 14 not run). Final full source run 618 PASS, 5 XFAIL, 0 FAIL. Final role batch 7 PASS; occupied appointment-time harness corrected and targeted replay PASS. Restart/session/history/keys PASS. Real Qwen extraction and both chat audiences PASS. Phase 1 IN_PROGRESS; next execute bounded performance harness, then Phase 2 preservation/rehearsal, Phase 3 actual Docker proof. Overall READY remains NOT_READY. See reports/phase0/TEST_REPORT.md and BUGS.csv. Source original archive hash / backup in raw manifests. Subagents 0/4.
