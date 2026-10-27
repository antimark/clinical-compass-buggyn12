# Role journeys, guest questionnaire persistence, administrator names — 27 October 2026

## What changed in this iteration

- Public guest pages `/#/assessments`, `/#/assessments/phq_9`, `.../phq_2`, `.../gad_7`, `.../gad_2`, `/#/assessments/<code>/result` using four *unapproved, synthetic evaluation* questionnaire JSON definitions from the existing clinical catalog. Anonymous GET serves definitions only in `synthetic_dev` or acknowledged `evaluation_sandbox`; not in production.
- Guest sees provisional score and responses immediately without creating an account. Data are held **only in current browser tab's sessionStorage**, not the backend. No guest answers are sent to the API or shared with a physician. Refresh works within same tab; closing the tab may discard them; browser session restore varies. Never input real patient/health data in this evaluation build.
- "Войти и сохранить" and "Зарегистрироваться и сохранить" lead through existing normal local auth and CSRF. After successful patient authentication the UI uses versioned `self-assign`, server draft and `submit`; only a confirmed server response triggers navigation to canonical `/#/patient/questionnaires/<id>/result`. This result is reachable later under patient tasks and via the profile history link. If server save fails, guest state remains for retry; avoid treating provisional result as saved.
- When a user is logged in as another role, guest results cannot be imported into that role. All four scores are basic 0–3 item sums with no clinical cutoffs, clinical release, or individual risk advice.
- Clinic staff API now returns `display_name` alongside role/specialty only for `clinic_admin` and same organization. Patient FIO is rendered from **explicitly granted** administrative projection fields, never from the core `User.display_name`, login email or diagnosis. Hidden without patient permission.
- Patient can enter synthetic first/last/middle names at `/#/patient/admin-identity`, save encrypted values, choose a policy template and grant/revoke; existing `admin_privacy` server gates remain active. A separate operator CLI `scripts/evaluation.sh privacy-setup --workspace <PRIVATE QA WS>` enables the module and creates a first/last/middle template only in isolated Evaluation Sandbox. This does **not** grant consent; requires patient-doctor/clinic link and subsequent explicit patient action.
- Evaluation launcher creates a stable private `identity-fernet.key` inside workspace (mode 0600). Keep this key alongside the database backup; loss prevents reading encrypted fields. Never include either in distributed ZIP.
- `/#/demo/journeys` now provides four role-specific, real navigation links with candid labels for partially connected screens. It is a map of the UI, not an indication that every linked workflow is E2E complete.

## User flows for local demo

1. Guest: `/#/assessments` → complete PHQ-9/GAD-7/PHQ-2/GAD-2 → provisional score → login OR register `.test` synthetic patient → server result page → sign out and back in → patient profile → "Открыть историю результатов".
2. Doctor: provision `account --role doctor` → invite synthetic patient → patient accepts and grants rights → doctor questionnaires and result, doctor Clinical Copilot (static walkthrough without links; actual Qwen inference with data/ACL), NLP lab, Clinical Catalog.
3. Researcher: provision `account --role researcher` → datasets, demo-v3, signals. Cohort compare/export screens remain partial until live verification. Do not show as already completed analytics.
4. Clinic administrator: provision `account --role clinic_admin` → explicit `privacy-setup` operator action → patient has active clinic relationship → patient saves synthetic FIO and accepts template → clinic patient list/detail show consented name → revoke on patient page → admin no longer sees name. Staff list shows employee display names where data exist.

## Real status vs static rendering

The original designer's 95 declared routes were not all complete: prior audit classified 15 unavailable, 16 partial; AI Clinical Intelligence pages now have illustrative and/or server-backed variants, but their live operation requires Ollama, appropriately seeded cases, and role/consent checks. This iteration declares 102 routes (including new guest and admin consent screens). `npm test` runs dependency-free route/design and simulated-contract tests; **these are not live Flask+SQLite+Playwright E2E tests**. A Codex prompt to verify and measure all paths on the user's Mac is at `docs/phase04/CODEX_JURY_RELEASE_PHASE0_PHASE3_PROMPT_2026_10_27.md`.

## Known outstanding workflows / dead ends requiring Phase 0

- Patient/doctor opaque message thread IDs; share-AI-summary consent flow; native video room; post-visit reviews; clinician import and psychotherapy editor; full researcher cohort builder, mini-case, comparison and CSV export; administrative invitation creation, comprehensive audit and license tally; partial patient care-team visibility editor. The route can render an explanatory screen while the intended action still cannot complete.
- To demonstrate all four roles in one session, use isolated accounts in four separate Chromium contexts; role switching by URL must never bypass the API. The guided page is `/#/demo/journeys`.
- All 77 medicine entries are exposed through the paged Clinical Catalog, including raw nested source sections as in the previous integrated archive, but online source URLs and every real-browser detail interaction remain not independently verified on Mac.

## Mac prerequisites

Already installed in `cc-m1`: Flask, SQLAlchemy, Alembic, Playwright Python, pytest, Node.js, cryptography — no new Conda environment is needed. Check `python -m playwright install chromium` to download the actual browser, verify standalone Ollama and pull `qwen3:4b-instruct`; Qwen weights are NOT in the ZIP. Optional `pytest-playwright` only if choosing pytest fixtures; no dependency is required for small local load tests when using Python standard library.


**Jury release transition:** this file documents the baseline, not a completed release. Implementation and test gates now follow the four-phase canonical Codex prompt and `docs/phase04/JURY_RELEASE_ACCEPTANCE.md`. No Docker build/AI-container smoke test is claimed in this archive.
