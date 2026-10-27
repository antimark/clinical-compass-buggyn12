# Phase 0 — INCOMPLETE; release NOT_READY

Environment: macOS 26.5 arm64, 16 GiB; existing cc-m1 Python 3.11.17, Node 22.23.4, pytest 9.1.1, Playwright 1.64.1. Native Flask + private persistent SQLite on 127.0.0.1:8766. Ollama 0.40.11, qwen3:4b-instruct, digest in raw/preflight.jsonl. No real patient data used.

Completed live proofs:

- 95 tests passed in raw/live-guest-catalog-run3.log: eight guest authentication/save paths, reload/logout/login/profile history, tab isolation, four missing-answer guards, lost-submit retry recovery, all 77 medicine detail DOMs against every nonempty source leaf, 242 catalog entries and internal links/pagination.
- Four server validation cases passed in raw/live-negative-contracts.log: invalid answers, missing CSRF, incomplete submission, stale revision, repeat-submit key and unauthenticated access.
- Researcher cohort filter/methodology/CSV and clinic name opt-in/revoke passed in raw/roles-run2.log. Physician assignment/result passed in raw/doctor-run3.log; independently repeated source security coverage is not counted as browser acceptance.
- Real Qwen extraction, exact evidence, persisted claim review, physician-edited unsigned chart draft and manual referral passed in raw/doctor-qwen-run4.log. Earlier rejected model evidence is retained as FAIL, not hidden.
- Both contextual chat audiences used actual Qwen with persisted histories and cross-role denial (raw/live-contextual-chats.log, raw/chat-qwen-metadata.jsonl).
- Patient intake, messages, check-in and appointment offer/confirmation passed in raw/intake-appointment-live.log.
- Native restart retained an authenticated browser session, saved score/history and both stable private keys (raw/restart-capture.log and raw/restart-verify.log). Cookie files and keys remain outside the repository.

Source baseline: 607 passed, 8 failed, 5 xfailed; all results retained in raw/source-baseline.log. Obsolete frontend assumptions were repaired against the current designer UI; role/staff privacy guards retained. Current targeted renderer/Qwen check: 17 passed (raw/renderer-qwen-focused.log). Final full source regression running, not yet accepted.

Read-only route/control evidence: ROUTE_CONTROL_MATRIX.csv, raw/controls.jsonl, raw/inventory-live.log. Rendering is READ-ONLY PASS, never action E2E. Some parameter substitutions need route-specific refinement; those initial 404s are retained and are not attributed to the app without reproduction. Mobile home checks cover 360/768/1280 and both themes; this is not a complete accessibility audit. External source URL availability is NOT_RUN; internal links and safe link schemes were tested.

Current defects and guard-related limitations: BUGS.csv. No baseline routes or API operations removed (102 and 232 respectively). The feature preservation registry is ../phase2/FEATURE_PARITY.csv; phases 2/3 are pending. Source backup and original archive checksums are recorded in raw/source-backup-manifest.json and raw/feature-parity-baseline.json. Subagents used: 0/4.

Reproduce using existing cc-m1 binaries with PYTHONPATH=backend:. and the commands in .agent/CHECKPOINT.md. Browser tests use real HTTP, cookies and CSRF. Successful API fixtures exist only in source/unit tests; the browser retry test forwards a real commit and drops only its transport response.

## Phase 0 checkpoint outcome

Core native functional gate: PASS with disclosed breadth limits. Full source regression: **618 PASS, 5 XFAIL, 0 FAIL** in 334.45s (`raw/source-regression.log`, XML). XFAILs concern real-world identity/professional verification, complete legacy SignalEngine integration, and reviewed/licensed clinical release; none is promoted to implemented clinical functionality.

Final role run: 7 PASS plus an expected occupied-time 409 incorrectly treated as failure by the rerun harness. The appointment harness now reads actual slots and selects a free time; targeted replay PASS (`raw/appointment-repeat-safe.log`). Server conflict protection was retained. Staff full name, both real Qwen chat audiences, researcher and clinic consent passed in the final role run. Browser trace captured privately outside source; redacted timeline in `raw/browser-timeline.jsonl`.

Targeted route recheck: **83 READ-ONLY PASS, 5 PARTIAL, 14 NOT RUN**, no browser-exception/5xx DEAD END recorded in traversed routes. Incomplete dynamic object routes remain explicitly unaccepted; this is not exhaustive action completion. Research legacy-study grants and genuine OIDC/MFA invited staff enrollment remain guarded and disclosed, with working alternate paths added without removing functions. All 102 routes and 232 API operations in the original archive remain present; 1,854 parity rows now include additional observed controls.

Proceed to Phase 1 measurement on the proven native paths. Phase 2 must preserve baseline functionality, address material gaps and rerun regression; overall jury readiness remains NOT_READY pending rehearsal and Docker proof.
