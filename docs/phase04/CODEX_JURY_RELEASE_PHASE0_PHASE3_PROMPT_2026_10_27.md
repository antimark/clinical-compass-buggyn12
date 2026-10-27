# CODEX MASTER PROMPT — Clinical Compass | Jury release | Phases 0–3

You are the technical lead, QA automation engineer, full-stack integrator and release engineer for Clinical Compass. **Your final deliverable is a functional jury-ready application**, reproducibly launched both natively on the Mac and through Docker, plus measured and truthful test evidence. **Make code changes and fix discovered blockers**; do not stop at a test plan, UI mockup, Dockerfile or status report. Start with an isolated evaluation workspace on the operator's Apple Silicon Mac. Keep all runtime medical and account data synthetic. Do not replace the existing Flask + SQLAlchemy + vanilla JS application, rewrite its design, disable CSRF/RBAC/consent, or simulate successful API responses in release-gate tests.

## Final outcome, authority and release gates

- Primary source of truth: **working source code and actual API/DB semantics**; follow the updated `AGENTS.md` and `docs/phase04/JURY_RELEASE_ACCEPTANCE.md`. Preserve current designer UI and product goals. The application is a *synthetic evaluation prototype*, not a medically validated clinical product.
- The 4 user roles (**patient, doctor, researcher, clinic administrator**) plus **guest** must have rehearsal-ready journeys on actual API and persistent data. No active primary CTA may produce a blank screen, unexplained 404/422/500, false success or a route without a usable next action. Repair core missing actions; where a future feature is not feasible, give an **explicit interactive synthetic demonstration** with provenance, explanatory label and a working return action. Do not present illustration as persisted result or Qwen output.
- Core exit criteria include: four pilot PHQ/GAD forms completed as guest and authenticated patient, result display, guest→login and guest→registration server save with durable history; doctor questionnaire assignment/review and clinical review; real Qwen/Ollama evidence tagging/chat (no mocked inference); discoverable full catalog and **all allowed nonempty fields** of all 77 drug records (69 summaries and 8 source instructions), paginated; consent-controlled patient FIO and staff names in clinic admin; researcher demonstrable sample-to-result journey.
- Preserve role/tenant/consent/CSRF/audit rules, manual physician review, synthetic-only inputs, licensing and publication gates. Medical validation remains pending, **but experimental features remain demo-capable with honest labels**.
- Run phases in exact order **0 = functional audit/repair, 1 = performance/UX measurement, 2 = stabilization and juror rehearsal, 3 = Docker packaging + real verification**. Checkpoints and proofs are mandatory between phases. Do not claim jury readiness until all release gates are tested; Docker build alone is not acceptance.
- Use `reports/phase0/`, `reports/phase1/`, `reports/phase2/`, `reports/phase3/`, `reports/FINAL_JURY_READINESS.md` as evidence directory names. Generate a final source distribution and separately sanitized reports. Output exact commands, URLs, test accounts provisioning steps (no passwords) and remaining issues.

## Inputs / operating environment

- Source of truth: this repository, `AGENTS.md`, `docs/phase04/*`, `frontend/INTEGRATION_MATRIX.csv`, `frontend/dist/assets/data/routes.json`, all migrations, tests and existing backend contracts.
- Hardware/OS: operator's macOS Apple Silicon device; do not assume host machine hardware or version: record it.
- **Existing** Conda environment: `/Users/mark/miniforge3/envs/cc-m1` (Python 3.11.17, Node 22.23.4, Flask 3.1.3, SQLAlchemy 2.1.6, Alembic 1.20.1, pytest 9.1.1, Playwright 1.64.1, cryptography 50.0.2, psycopg 3.3.6). Use `/Users/mark/miniforge3/bin/conda run --no-capture-output -n cc-m1 ...` or activate `cc-m1`. **Do not create a new Conda environment, pip-upgrade everything or delete an existing database.**
- Ollama endpoint on the SAME Mac: `http://127.0.0.1:11434` with *exact* local model `qwen3:4b-instruct`; keep AI routes backed by this actual model. Do not replace with cloud calls or scripted model responses when claiming AI integration. Distinguish static Clinical Intelligence walkthrough from Ollama inference.
- HTTP app exclusively on loopback, e.g. `http://127.0.0.1:8766`, launched with `CC_CONDA_ENV=cc-m1 bash scripts/evaluation.sh serve --workspace "$HOME/Library/Application Support/ClinicalCompassEvaluation-QA" --port 8766`. **Never run load testing against an external/shared production system.** Use a new, dedicated QA workspace (not user's normal evaluation database); back up before migrations and preserve the seed/provenance.
- `scripts/evaluation.sh account --role doctor|clinic_admin|researcher --email ... --workspace ...`; create synthetic patient through the normal registration workflow. `scripts/evaluation.sh privacy-setup --workspace ...` explicitly enables *optional* administrative PII projection for this isolated sandbox only; it does NOT grant consent. PHQ/GAD are `evaluation_draft_unapproved`, not medically approved; don't remove that status.

## Low-usage execution policy for Codex Plus / subagents (MANDATORY)

**Primary objective is a finished jury-ready prototype within the user's available usage, not maximal parallel agent count.** Read `docs/phase04/SUBAGENT_BUDGET_PROTOCOL.md`; its delegation, checkpoint and short-report rules are binding for all four phases. Do not assume a guaranteed number of Plus messages/tokens; availability and charging may vary.

- **Default one coordinator, no subagents** when focused scripts/patches suffice. Spawn only when the work is both independent and demonstrably saves coordination time. Cap **2 active subagents at once and 4 delegations for the entire 0–3 project** unless the operator explicitly approves exceeding the budget. Subagents must not spawn their own agents. If the chosen Codex runtime lacks delegation support, use sequential work packages; do not hunt for hidden capabilities.
- Preferred specialist work packages: **A** pilot PHQ/GAD scores + guest→auth persistent save, **B** completeness of 77 drug records + pagination, **C** UI dead ends for the four roles, **D** Docker/Ollama integration. Reassign a slot only if essential; never duplicate analysis or ask two agents to solve the same feature. Coordinator reserves ownership of migrations, global auth/config, `AGENTS.md`, phase prompt, shared test harness, manifest and release archive; integrations must be reviewed before merging.
- Each task packet MUST contain `TASK-ID`, phase/priority, single objective, allowed files, concrete known blocker, dependencies, **1–3 focused test commands**, pass/fail exit, stopping conditions; no full-prompt repeats or giant file dumps. Require **≤600 words of summary** plus references to changed files and evidence. Parallel tasks must have disjoint edit scopes and must not independently launch whole test suites, long-running servers, load tests, Docker image builds or extra Qwen generations.
- Automated inventories and tests should be reusable: one machine-readable route/control scan, one shared Playwright harness, data-driven coverage of all 77 drugs, tests of all four forms, a bounded set of real E2E role journeys. Run **focused regression after each fix**, **one full suite at phase checkpoints** and final release, rather than repeatedly rerunning everything for each delegate. Never trade away essential security tests or honest live-evidence gates for usage savings.
- After each phase write/update `.agent/EXECPLAN_ACTIVE.md` and `.agent/CHECKPOINT.md`: current git revision, files changed, actual PASS/FAIL/BLOCKED, precise commands/log paths, next three actions, remaining subagent budget X/4, and `READY` gate status. Subsequent Codex sessions MUST first read these two files, `AGENTS.md` and the current phase report, then resume exact remaining work **without repeating the whole initial audit**. If the usage budget is reached, leave a runnable checkpoint and actionable one-paragraph resume instruction; do not claim asynchronous continuation.

### Continuous evidence + restart safety (mandatory, even mid-phase)

- **Persist while working, not only at phase end.** Create `reports/phase0..phase3/PROGRESS.md` on first phase entry, and append results from **each finished Playwright task/test**, endpoint measurement batch or short bounded load batch to the corresponding raw CSV/JSONL *immediately*. For phase 1, specifically keep `reports/phase1/raw/http_latency.csv`, `task_timing.csv`, `errors.csv`, `llm_metrics.json` (update atomically per model call) and `environment.json` as soon as observations exist. Record `run_id`, UTC timestamp, scenario, actor/role, observed status, timing unit, elapsed value, n, endpoint/task, and reproducible environment/command. Preserve failures and partial runs instead of filtering them out.
- Keep `PROGRESS.md` truthful: PASS / FAIL / BLOCKED / NOT_RUN counts, **completed so far** and **remaining**, latest raw-data locations, partial summary p50/p95 only where sample size supports, and exact command to resume. Update it plus `.agent/CHECKPOINT.md`/`.agent/EXECPLAN_ACTIVE.md` after every **5 scenarios or 10 minutes**, whichever first, **before long operations**, and at end of each subtask/phase. Write checkpoint/summary files via temporary file + atomic rename where practical; append and flush raw observations within the generating script.
- Never accumulate all observations exclusively in RAM until the end; if a benchmark fails after 73 measured requests, those 73 samples must already be usable. Group short requests in a bounded batch and flush between batches; assign stable `run_id` to avoid duplicate rows after restart. Do not rerun completed costly tests by default; continue at the first uncompleted case and later repeat only if changes invalidate baseline.
- If Codex Plus usage is exhausted mid-task, the repo **must already contain a usable intermediate deliverable**: modified source, current PASS/FAIL matrix, raw metrics collected to date, partial report labeled `INCOMPLETE`, checkpoint pointing to exact last test and next safe command. Never state that the entire phase passed based on incomplete runs. If safe, make a git commit of a tested code checkpoint, excluding credentials, DB and browser profiles.

- **Priority if usage is tight:** (1) safe auth/role/consent; (2) 4 forms + guest account save; (3) all 77 medicine data; (4) live doctor Qwen+chart/referral; (5) basic researcher/admin journeys; (6) minimum reliable measurements and rehearsal; (7) Docker live proof. Never silently mark lower-priority gates passed; label as `BLOCKED/NOT_RUN` if not executed. A native working release is better than an untested Docker facade, although Phase 3 remains the ultimate target.

---

## Mandatory preflight (run and record actual console outputs)

1. Read `AGENTS.md` and relevant technical handoff/docs; inventory dependencies, ports, build commands, migrations, feature gates, account provisioning and current 102 routes (count again, do not assume).
2. Record `sw_vers`, `uname -m`, `sysctl -n hw.memsize`, Conda executable path, `python --version`, `node --version`, `python -m pip check`, `python -m pytest --version`, `python -m playwright --version`, `ollama --version`, `ollama list` and `curl -s http://127.0.0.1:11434/api/tags`. Avoid logging authentication tokens and clinical test text.
3. If no Playwright Chromium browser binary: `python -m playwright install chromium` (WebKit optional for Safari-specific coverage). Record exact installation. Python Playwright already appears installed; **browser binary is a separate prerequisite**. `pytest-playwright`, `psutil`, `locust`, etc. are NOT prerequisites if tests use existing `playwright` and Python stdlib. Add dependencies only when justified and pin reproducibly.
4. If Ollama isn't installed/running: install from https://ollama.com/download/mac; start application. If model missing: `ollama pull qwen3:4b-instruct`. Validate actual model response with a benign synthetic request, provider timeouts and the application feature toggles. Do not infer AI success from `/api/tags` alone.
5. Run static suite `cd frontend && npm test`, Python syntax checks and existing focused pytest modules; log PASS/FAIL/SKIP/XFAIL, reason, environment. Start real Flask server; probe `/api/v1/health`, `/api/v1/evaluation/questionnaires/public-definitions` and `/api/v1/clinical-catalog/search`. Test unauthorized routes and expected access errors.
6. Use separate browser contexts and distinct test accounts for patient / doctor / researcher / clinic admin. Avoid hard-coded passwords in source/reports, collect via `.env.qa.local` or OS secrets protected by chmod 600; do not commit secrets/DB/session cookies.

---

# PHASE 0 — Actual functionality, all navigation paths and user journeys

**Goal:** determine what really works on live Flask+SQLite+Ollama, remove reproducible dead ends where safe, cover all roles and exactly distinguish confirmed behavior vs illustrative screens, with screenshots, timings, HTTP responses, persisted DB checks and role-access checks. A successful HTML render is not proof that a button works. No mock API responses qualify as Phase 0 acceptance.

## 0.1 Route and control inventory

- Parse `frontend/dist/assets/data/routes.json`, `frontend/INTEGRATION_MATRIX.csv`, nav configuration, `<a href>`, submit forms, `[data-command]`, modal actions and dynamic linked routes; enumerate **every clickable element** in rendered pages for each role and state: list location, label, selector, expected navigation/action, expected HTTP method, authorization, happy path, error path, actual result and evidence link. Cross-check source-code commands vs DOM controls to find dangling/unreachable/unused handlers.
- Use real Playwright browser (Chromium headless; 360px/768px/1280px, keyboard navigation, dark/light). Listen for `pageerror`, console.error, failed fetch, HTTP 4xx/5xx, navigation to unknown route, blank pages, hidden/overlapped buttons, broken `href`, repeat submission, focus and scroll jumps. Verify no dead end without a discoverable recovery/back path.
- Classify every route/control: **E2E PASS**, **READ-ONLY PASS**, **WORKING PROTOTYPE**, **ILLUSTRATIVE DEMO**, **PARTIAL**, **DEAD END/FAIL**, **NOT RUN (with blocker)**. Do not mark mock tests as E2E. Update `frontend/INTEGRATION_MATRIX.csv` and `docs/phase04/ROLE_JOURNEY_AUDIT.md`. Create issues with severity P0/P1/P2, screenshots and exact steps to reproduce.

## 0.2 Patient journey (normal and guest)

- Guest `/#/assessments` → select each of PHQ-9 / PHQ-2 / GAD-7 / GAD-2 → complete with synthetic inputs (0 and 3 extrema, typical case, missing/invalid values) → local result (`0–27`, `0–6`, `0–21`, `0–6`). Refresh and test sessionStorage state; validate browser tab boundary and that temporary data is never reported as saved remotely.
- Guest result → **login** as existing synthetic patient → automatic transfer through self-assign → server draft → submit → landing on canonical persisted `/patient/questionnaires/<id>/result`; result survives full reload, logout/login, and is visible under `/patient/tasks` AND via the `/patient/profile` history link.
- Guest result → **register** new synthetic patient `.test` account → same transfer and persisted result. Test retry on interrupted network, invalid password, role mismatch, CSRF failure, 409 revision conflict, double clicks, competing submissions; no duplicate/overwritten result. Ensure redirect to retry screen rather than misleading "login failed" if save fails after successful auth.
- Logged-in patient → self-assign / resume draft / score / history / doctor-assigned form; doctor sees only authorized submissions. Check version snapshots. No diagnostic interpretation while not approved.
- Full patient path: register → onboarding/profile → find physician → invitation/consent → write diary/check-in → create intake → reply via authorized chat → appointment offer and confirmation → treatment/adherence → adverse-event report → permissions → private AI diary/chat using local Ollama; distinguish backend-generated content from illustrative fallback. Test access revocation and privacy boundaries, 401/403 routes.

## 0.3 Doctor journey

- Login as doctor, manage invitations; patient accepts → authorized relation → patient list → patient details, trends, visits, safety alerts, clinical summaries, questionnaire assignment/result, booking, correspondence, colleague messages and shared patients under consent.
- Clinical Intelligence: synthetic source → Ollama-backed analyze → evidence-linked tags → approve/reject → proposed unsigned chart entry with manual edit/approval → manual referral decision (urgency and rationale) → catalog links and version/audit trail. Validate no auto-diagnosis or medication order; one route to interactive preview must still work without sample patient. Test genuine provider unavailability separately.
- Catalog: verify all 242 internal records (77 medicine entries incl. 8 source monographs, 77 diagnoses, 58 therapies, 30 instruments); 77/77 medicine detail records must display **all nonempty JSON source fields**, nested fields, and origins. Check paging through all items, filtering, result count, cross-links, external links (external availability distinct from internal functionality). No clipping/ellipsis of important medical fields.
- Check encountered 404/409/422 and false-success toasts; examine editor save behavior, scroll preserving when adding a medication, errors/safety permissions.

## 0.4 Researcher journey

- Login researcher → dashboard → dataset/source inventory → demonstrated cohort definition (if available) → A/B compare → signals → demo datasets → export. For each action: inspect real server response, missing data, method/denominator metadata, cohort constraints and no patient-identifying output. Explicitly tag unfinished cohort builder, CSV export and mini-case route until operational and tested; create an interactive synthetic demo rather than a dead blank page if feasible within Phase 0.
- Cross-role test: researcher cannot access named patient records, patient answers, internal physician approvals or encrypted PII.

## 0.5 Clinic administrator journey

- Login clinic admin → overview → appointment administration → patient list → detail → staff names/roles/specialty → staff invitations → permissions/templates → audit logs.
- FIO: verify display of `display_name` for clinic staff; patient name is composed **only** from consent-authorized `fields.last_name`, `.first_name`, `.middle_name` on `p0/clinic/patients`. With absent consent show "ФИО скрыто: нет разрешения пациента", not core `User.display_name`/email. Prove absence of unauthorized disclosure with negative tests.
- Dedicated synthetic scenario: operator runs `privacy-setup` on isolated QA workspace; patient separately saves fictitious FIO in `/patient/admin-identity`, accepts allowed admin template; clinic admin sees full name, *without* diagnosis, notes, diary or contacts. Patient revokes; admin refresh immediately hides name. Test organization scope and cross-clinic isolation. Do not auto-consent or bulk enable in production.
- Check invitation creation/revocation, granular access and audit UI. Report precise missing API/workflows; don't claim all work because route displays a placeholder.

## 0.6 Acceptance and remediation

- Phase 0 exit criteria: a traceable result for **every declared route** and reachable action, all P0 flow blockers addressed or explicitly blocked with reproducible reason; 4 questionnaires work for guest and authenticated patient, both login and registration flows save correctly, persisted results remain after re-entry; admin PII opt-in correctly demonstrated; no 500s/JS errors in the core journeys; no role or consent bypass. Clinical Intelligence and AI-backed paths verified **with actual Ollama Qwen** (not UI illustration alone).
- Run each core scenario with minimum two passes on a fresh QA DB and a warm/revisited DB. Collect API status and sanitized payload shape, evidence screenshots and Playwright traces. No real patient data. Compare original and changed behavior; fix safely and rerun regression tests. Document non-reproducible environmental blockers.
- At phase boundary output: `reports/phase0/TEST_REPORT.md`, `reports/phase0/ROUTE_CONTROL_MATRIX.csv`, `reports/phase0/BUGS.csv`, `reports/phase0/ENVIRONMENT.json`, `reports/phase0/screenshots/`, `reports/phase0/traces/` (sanitized), and Playwright/pytest runnable scripts. Include counts by role and pass/fail/partial/not-run, observed request logs and changes made. **Do not start Phase 1 until Phase 0 evidence and blockers are recorded.**

---

# PHASE 1 — Technical/UX performance measurements and minimal local load

**Goal:** quantify actual user-perceived latency and backend processing, automated Time on Task, render quality, error reliability, and safe bounded concurrency with reproducible raw data. Record device/OS/model/temperature/CPU/memory and cold/warm state. Do not confuse a model response with deterministic work or user clinical effectiveness.

## 1.1 Measurements and definitions

1. **Response time:** per endpoint and journey action: server-side request latency, client `performance.getEntriesByType('resource')` durations if available, Playwright response timings; median/p50, p90, p95, p99 when sample size supports it; n, error ratio, min/max, confidence/limitations. Split ordinary JSON CRUD, search, authentication, chart, database writes and LLM inference.
2. **Page/navigation performance:** `DOMContentLoaded`, LCP if PerformanceObserver supported, initial route to usable state, route-to-content duration (hash SPA routes), layout shift/CLS if available, long-task counts, JS memory (if Chromium supports metrics), transfer sizes, total requests, failed requests; detect slow source and UI blocking. For <N samples label p99 unreliable, report distributions and n.
3. **Time on Task (ToT):** (a) automated scripted task time from initial click to verified final server state, measured with `performance.now`/Python `time.perf_counter`, excluding test fixture provisioning; (b) separately, **real observed human** Time on Task requires consented participants and observer timestamp protocol; without real participants report only *scripted ToT*, NOT usability-based human ToT. Breakdown by step and role. Number of clicks, backtracks, recoveries, validation errors, completions/timeouts and time-to-first-success.
4. **AI/Ollama:** cold versus warm Qwen3 4B request; end-to-end Clinical Intelligence latency, prompt-eval and decode if Ollama metadata returned, tokens/sec, total tokens, timeout/fallback rates; label whether result was actual model generation, rule-based NLP, or fixed visual example. Record exact model name and digest, do not expose clinical text. Run 1 outstanding LLM request initially; at most 2 only if memory/thermals safe and the user authorizes.
5. **Correctness/reliability:** server persist check after login, role/consent gate accuracy, 4xx expected vs unexpected, 5xx errors, duplicate/submission races, 404 links, broken external references separately, application errors per 1000 requests, uptime during bounded test, idempotency.
6. **UX/accessibility:** viewport 360/768/1280, dark/light, color contrast WCAG where tool available, keyboard tabs/focus, target hit area, labels/form errors, overflow and scroll-jump reproduction; results by route and role.
7. **Resource use:** peak process RSS and CPU for Flask/Ollama if collectible without privileged utilities; memory pressure, SQLite lock duration/retries, DB size, local system load, warm/cold comparison. Do not claim metrics if inaccessible.

## 1.2 Scripted ToT tasks to instrument

- Guest opens PHQ-9 → answers 9 items → sees sum → logs in → verified result in profile.
- Guest opens GAD-7 → answers → registers `.test` account → stored result; repeat PHQ-2/GAD-2 with authenticated patient.
- Physician creates invitation → patient accepts → physician sees link; physician assigns questionnaire → patient completes → doctor sees permitted result.
- Doctor opens synthetic intake → launches real Clinical Intelligence → reviews tags → saves an unsigned draft → manually records referral.
- Doctor searches catalog for drug → opens detail → expands all fields → navigates linked diagnosis and returns; iterate list across 77 medicines.
- Researcher opens dataset → checks cohort/compare/screens (mark workflow incomplete rather than recording false success); clinic admin locates consented patient name, staff list and appointment.

## 1.3 Minimal local load: safe profile

- Use dedicated loopback and QA DB only; no external service. Prefer a Python asyncio/http.client/urllib custom bounded runner or simple stdlib `ThreadPoolExecutor`; **no need for Locust** unless justified. Collect individual latency observations CSV, success/failure counts and throughput.
- Read-only non-AI endpoints: warm-up 10 requests; then 1, 3 and 5 concurrent *virtual users*, each 30 seconds, rate capped at **max 2 RPS total** (or lower if host struggles), total <= 250 requests per scenario. Targets: `/api/v1/health`, authorized catalog search/detail, role-appropriate read-only dashboard where feasible. Preserve cookies/CSRF in per-user contexts, never mix sessions.
- Write-path smoke: at most 1–2 sequential synthetic write actions with unique identifiers, no spam or race-stress of clinical records; verify persistence and rollback using disposable QA workspace. Do not exercise patient login as a brute force or stress auth rate limits.
- AI: exactly 1 real Qwen call for baseline; optionally 3 sequential calls to estimate variation with warm model. **No parallel LLM load by default**; no flood requests, no external cloud fallback, no infinite loops.
- Stop immediately for 5xx burst, repeated SQLite locks, excessive thermal/memory pressure or safety failures. Declare stop conditions in harness. Capture CPU/RSS where possible. Run baseline, load, recovery; compare resulting p95/p99 and error rate. State results as measurements, not established SLO.

## 1.4 Targets for review (not predetermined PASS results)

- Functional target: 100% completion of four pilot questionnaires under guest+login and guest+register, server response and revisited history verified; strict 0 unauthorized PII leaks; all role journeys have a classified outcome.
- Illustrative engineering thresholds for discussion, **not SLA**: local cached ordinary read endpoint p95 <= 500 ms; normal authenticated interactive action p95 <= 1 s; SPA route usable p95 <= 2 s (on specified machine); core-scripted ToT medians recorded for later human usability comparison; 0 unexpected 5xx over bounded synthetic load. Qwen generation latency separately recorded and not judged by generic 500 ms HTTP target.
- If device or scenario invalidates targets, capture constraints and propose thresholds instead of hiding failures. Derive realistic values from baseline plus stakeholder requirements.

## 1.5 Phase 1 outputs and handoff to Phase 2

Create and populate (real evidence, not placeholder templates):

- `reports/phase1/PERFORMANCE_REPORT.md`: executive overview, environment, data sample sizes, percentiles by endpoint, AI traces (non-sensitive), clinical source context, ToT table, graph captions, error/reliability, resource usage, bottlenecks and ranked remediation.
- `reports/phase1/raw/http_latency.csv`, `reports/phase1/raw/task_timing.csv`, `reports/phase1/raw/errors.csv`, `reports/phase1/raw/llm_metrics.json`, `reports/phase1/raw/environment.json` and a *locally generated* plot or HTML table where useful. No credentials/PII.
- `reports/phase1/LOAD_REPORT.md`: endpoint, concurrency, duration, achieved RPS, 2xx/4xx/5xx, p50/p95/p99, observed RSS/CPU, halt condition and recovery.
- `reports/phase1/PHASE1_SUMMARY.md`: observed status of each role, conversion, scores/persistence, consent, full catalog, actual Ollama generation, unresolved findings and ranked engineering fixes; final jury verdict is postponed until Phase 3.
- Runnable scripts `tests_e2e/` and `tests_perf/`, reproducible commands and updated route matrix; do not generate a premature “final” ZIP during Phase 1.

**Phase 1 gate:** identify reproducible bottlenecks and record baseline results, including any failures. Do not optimize by removing validation, security, persisted state, Qwen or the user workflow. Resume Phase 2 with a prioritized list and measurements to rerun.

---

# PHASE 2 — Remediation, jury walkthrough, resilience and release candidate

**Goal:** transform the Phase 0/1 discoveries into a cohesive working prototype that jurors can demonstrate without having to understand implementation internals. Fix the app **in the source** and verify every repaired flow with a browser test and persisted state. The final product must look polished and behave predictably even with missing data or unavailable Ollama. Preserve product UX, don't silently strip promised capabilities.

## 2.1 Resolve blockers and technical debt

1. Address all P0 and demo-blocking P1 issues in `reports/phase0/BUGS.csv` and performance regressions from Phase 1. Rank by broken core path, role-authorization/security, data persistence, Qwen reliability, usability, then speed. A dead-end action is not resolved simply by hiding it: implement it where reasonable, otherwise label it an **interactive product preview** with valid return/navigation and record the gap.
2. Ensure **patient** can complete four PHQ/GAD forms with 0–3 answers; see score and item responses; log in **or register** and save to their own profile; reopen after page refresh/re-login/server restart; physician sees the authorized version. Verify duplicate click/idempotent behavior, invalid inputs, error recovery, permission denial and stale session handoff. No clinical cutoff interpretation for the unapproved drafts. Keep current patient-selected sharing and consent boundaries.
3. Ensure **doctor** can open synthetic intake, run *actual Qwen model extraction* and see tags with direct quoted evidence, inspect chronology and relevance, edit an unsigned proposed chart entry and save it (manual confirmation), see routed-specialist suggestions plus urgency, inspect rationale, add a manual referral or plan item, and navigate source catalog. Resolve any 422 appointment/draft errors and scroll jumps. Keep distinguishable: live AI output, rule-based engine, illustrative walkthrough and physician-persisted action.
4. Ensure **researcher** can run one actual synthetic case-to-analytic result journey with working filter/cohort/summary/methodology/detail (and CSV export if shown as active). If underlying user-facing views are empty, add deterministic but clearly synthetic fixtures through documented seeds, not hard-coded “success” popups. Real database/query output required for any claim of generated research result.
5. Ensure **clinic admin** can see identifiable *staff names* where permission allows, manage plausible team membership and appointment list, and see patient full name **only after explicit patient permission**. Test scope, consent revoke, row-level display and cross-clinic separation. Do not use a demo bypass or populate FIO from core clinical data.
6. Ensure **catalog** exposes all 242 current records, especially all 77 medicines. Enumerate every permitted nonempty field from the source JSON, including nested lists/objects and provenance/links, compare against frontend-rendered detail DOM; fail test for omission, unintended `[object Object]`, escaping/overflow, missing pagination, mislinked diagnosis/therapy, inaccessible source URLs (report external-network failures separately). Do not fabricate descriptions. Examine every medication, not a sample.
7. Check contact, appointment, messages, doctor profiles, onboarding, settings and app navigation for recoverable interactions. Fill obvious null/empty/error UI states, clarify unusual field names, ensure keyboard/viewport accessibility, avoid unexpected scroll restoration and mark read-only content with a real reason. No misleading toast saying “saved” without 2xx + persisted readback.

## 2.2 Construct one reproducible jury data set

- Provide a clearly synthetic but coherent fixture pack containing a clinic, staff, administrator, at least one physician, researcher, linked patient(s), appointments, questionnaire results, diary and intake, clinical AI analysis source, draft note, signals/messages and catalog links as allowed by current models. Reuse the same identities and chronology throughout roles. If seeded doctor/patient links would bypass real consent, provide a scripted authorized onboarding flow instead; fixture seeding must never impersonate an approval in production.
- Supply a **one-command disposable demo setup** that operates only on an explicitly named fresh workspace or volume. Existing databases are preserved. Seed/test accounts must not require a built-in password. Use operator-entered credentials, temporary generated secrets or safe fixture login provisioning, **never commit credentials**. Guarantee judges can start from a known state and the team can restore/rehearse without contaminating primary evaluation data.
- Prepare a **10–15 minute role-by-role live script** at `docs/phase04/JURY_DEMO_RUNBOOK.md`: time budget, operator action, URL, expected screenshot/observable persisted result, login/consent step, AI source/label, next role, backup when Ollama is busy/offline. Provide a compact juror home/route index and contextual navigation. Prefer showing real transitions over feature lists.
- Provide graceful errors, bounded AI wait, progress indication, retry and timeout messaging, and a separately labeled *static illustrative* Clinical Intelligence path that does not masquerade as server Qwen if it fails. Collect demo evidence and link it to release matrix.

## 2.3 Phase 2 acceptance, regression and outputs

- Rerun full Phase 0 matrix and the most meaningful Phase 1 benchmarks after repairs, at desktop 1280 and mobile 360 (plus tablet where possible), in both fresh and warm workspaces. No new P0/P1 regressions or unexplained failures in the juror runbook.
- Conduct **at least two complete automated rehearsals** of the jury script, one after fresh setup and one after restart; preferably manually shadow the same script in the browser and record issues. Real Ollama output and real persisted result must be visible in the live path. Fallback only counts as an explicitly labeled illustration, not a proof of AI.
- Produce `reports/phase2/REMEDIATION_LOG.md` (issue→commit/files→test evidence), `reports/phase2/REHEARSAL_RESULTS.md`, updated `frontend/INTEGRATION_MATRIX.csv`, `docs/phase04/JURY_DEMO_RUNBOOK.md`, documented fixture setup, screenshots/traces and `reports/phase2/RELEASE_CANDIDATE_STATUS.md`.
- **Phase 2 exit:** Every core juror task is actionable and either E2E-passing or explicitly blocked with reproducible evidence and an honest disclosure. No critical security violations; no silent guest-to-account data loss; no medicine field disappearance. Do not bypass an incomplete path by simply suppressing its button.

---

# PHASE 3 — Docker containerization, deployment smoke tests and final jury package

**Goal:** package the same working prototype in a repeatable Docker workflow that a technical juror or organizer can run. Docker must include **working frontend, Flask API, database persistence, migrations and an actually reachable local Qwen/Ollama path**, not an isolated static website. Preserve the native macOS/Conda route as a known-good fallback.

## 3.1 Docker architecture: determine what is actually workable

- Inspect `backend/cc_nlp/providers/ollama.py` and every AI provider config. The current `LocalOllamaProvider` permits **only loopback** endpoints; `http://127.0.0.1:11434` from a standard container points to the container, **not the Mac Ollama server**. Docker on macOS also may not provide Metal/GPU acceleration to a containerized Ollama daemon. **Choose and demonstrate a tested safe deployment design**, explaining trade-offs:
  - **Option A — Docker Compose with Ollama sidecar and app using a deliberately shared network namespace**, so app-to-Ollama via loopback remains valid; design app WSGI bind separately so Docker port publishing works. Ensure Ollama model data is stored in a named volume and startup/pull is a separately documented explicit step. Benchmark potential CPU-only inference, warn about slowness on Apple Silicon.
  - **Option B — reviewed Docker-to-host-Ollama adapter** for macOS using a narrowly restricted, authenticated/local-only bridge or a specifically approved host-gateway path. This requires safe provider config changes and an E2E network test. The default macOS host Ollama listener may be bound only to 127.0.0.1 and `host.docker.internal` may **not** reach it; do not assume it works or demand host `0.0.0.0` exposure. Never allow arbitrary public URLs, proxy redirects or cloud data transfer.
  - An equivalent audited approach is acceptable **only after** actual integration proof. If neither route can be safe/reliable on target hardware, mark Docker AI gate blocked rather than fake model output; native Mac remains demonstrated.
- Keep the exact configured `qwen3:4b-instruct` identity or document a deliberate change and verify server model digest and actual response. **Never place GGUF/model weights inside the source ZIP or the application image**. Pull/setup model explicitly and mount persistent model volume if using sidecar.
- Application server: use a reviewed WSGI runner rather than publicly exposing the Flask development server; bind to container interface **inside** while host publishes only `127.0.0.1:8766`. Pin Python/runtime dependencies and explain differences from the current Conda environment. Prefer single worker for SQLite and the local inference semaphore unless a different safe concurrency approach is proven. Enable appropriate health/readiness checks for backend and provider.

## 3.2 Files to implement (real usable artifacts)

- `Dockerfile` (Python 3.11 runtime and static frontend distribution), `compose.yaml`, `.dockerignore`, and where necessary `docker/entrypoint.sh`, `docker/healthcheck.py`, `docker/Dockerfile.ollama` or `docker/README.md`. Prefer an ordinary pinned base image / reproducible lock; note platform image architecture `linux/arm64` for Apple Silicon. Only introduce extra services needed for the working jury prototype.
- Persistent workspace volume for SQLite, **stable session secret and FIO encryption key**, and distinct Ollama model volume if containerized. Permissions must match `evaluation_launcher.workspace_config` or a precisely equivalent guarded configuration. Verify migrations on first run and upgrade of existing workspace without deleting any prior rows, keys, or session state. Use **named volumes** or explicit private bind mounts, not ephemeral container file state.
- A secure first-run account/setup command or script, login instructions and role provisioning. No hard-coded passwords/real clinical records. Put credentials in local secrets or interactive prompts; `.env.example` contains **placeholders only**, never real values. Explain backups and safe tear-down; `docker compose down` must preserve volumes, while destructive cleanup requires separate confirmation.
- Provide native Mac launch and Docker alternatives in `README.md` and `docs/phase04/DOCKER_JURY_RUNBOOK.md`; document exact prerequisites (Docker Desktop, enough RAM/disk, model pull, expected first-run time *without promising precise estimates*), CLI commands, ports, troubleshooting, space needs and verification commands. Distinguish native host GPU vs container CPU performance.
- Docker/Compose must expose **no database port**, no publicly accessible Ollama endpoint, no extra admin API or debug mode; bind application host port to `127.0.0.1`. Non-root app user, health/readiness, tight mounts and exclusions, and reproducible clean image. Build should not access private Mac paths or Conda.

## 3.3 Mandatory live Docker tests

Run `docker compose config` and an actual build, then launch using a **fresh disposable volume**. Record exact Docker/Compose versions and host machine, image IDs/digests and error output (redacted). Confirm:

1. `docker compose up -d --build` (or the documented safe two-step model-pull then up sequence) starts the application, DB and Ollama path. Health passes, no uncaught backend errors, loopback `http://127.0.0.1:8766/api/v1/health` and SPA available. Wait for real readiness, not a fixed sleep or only a TCP socket.
2. Qwen actually generates on a synthetic controlled request and Clinical Intelligence returns evidence-linked tags through the backend. Record latency and model digest. No cloud calls or mocked model result. Exercise model-offline and model-busy error UI and recovery separately.
3. Guest completes and scores PHQ-9, PHQ-2, GAD-7, GAD-2, then **both guest→login save and guest→register save**, confirms server result and restored patient history. Doctor assigns, reads authorized result, reviews AI suggestions and saves physician-confirmed draft/referral.
4. Researcher loads synthetic cohorts/metrics and follows methodology links. Clinic administrator sees staff FIO, patient opt-in FIO, then revocation hides it. Confirm no cross-role leakage. Check all 77 medicines and the full catalog using the same completeness tests as native.
5. `docker compose restart`, `docker compose down`/`up` (without `-v`) preserve database, results, private keys, consents, fixture identity and medical draft histories. A documented *fresh-volume* reset is deliberate and cannot happen on normal startup. Test reasonable failure modes: absent weights, port occupied, no model connectivity, migration failure, DB file permission errors and graceful notices.
6. Playwright smoke against the **container-served frontend/API** with real cookies/CSRF/roles; compare native-versus-Docker functional results, server response times and Qwen latency. Repeat static and pytest suites using the container runtime where feasible. Limited local non-AI concurrency only; no uncontrolled model load.

**Acceptance:** Docker is green only if build **and** real 4-role + guest + Qwen + durability smoke pass; a YAML validation or image build without tests is only PARTIAL/BLOCKED, never DONE.

## 3.4 Outputs and organizer deliverables

- `reports/phase3/DOCKER_TEST_REPORT.md`, `reports/phase3/DOCKER_ENVIRONMENT.json`, `reports/phase3/DOCKER_VS_NATIVE.md`, sanitized Compose logs, smoke traces/screenshots and remaining limitations. Include command output, pass/fail per test, root causes/fixes and reproduce instructions.
- `reports/FINAL_JURY_READINESS.md` with a concise verdict **READY / READY_WITH_DISCLOSED_LIMITATIONS / NOT_READY**, date/environment, links to test reports, role-by-role PASS/PARTIAL/BLOCKED and evidence, working-versus-illustrative AI distinction, PHQ/GAD status, medicine field coverage, security results, Docker status, measured response times/Time on Task/load, P0/P1 outstanding bugs. Do not assert production or clinical approval.
- `docs/phase04/JURY_DEMO_RUNBOOK.md`, `docs/phase04/DOCKER_JURY_RUNBOOK.md`, concise native and Docker Quickstarts, synthetic fixture/reset/restore steps, test invocation, screenshots and operator recovery/fallback procedure.
- One checksum-verified, clean **jury source ZIP** with backend, frontend, catalog, migrations, test harness, AGENTS.md, deployment files and instructions. A separate **sanitized QA evidence archive** if needed. Exclude real/model weights, `.env`, API keys, Fernet/session secrets, cookies, DB/SQLite WAL, generated logs, personal paths, browser state and any real health data. Update `PACKAGE_MANIFEST.json` for actual bytes and verify every SHA256. Do not claim the *current* planning handoff archive is a Docker-ready release until tests pass.
- Provide in the final Codex response a short operator action list: what changed, precise commands to start native and Docker, how to verify Qwen, URL, how to provision 4 roles, how to reset the disposable demo, key benchmarks, acceptance verdict and any unresolved limitations.

---

# Execution discipline / final instruction

- **Do the work on the actual source, in this repository.** Never stop after writing reports or Compose without running meaningful integration tests. Make an implementation plan, inspect current API and CSS/JS, create regression tests, fix root causes and rerun gates. If full scope is too large for one execution, prioritize guest/patient assessment persistence, doctor AI/record workflow, full drug card fields, researcher real demo, admin consent, four-role rehearsal and safe Docker/Qwen connectivity; produce the strongest functional release and explicitly list what remains blocked.
- Preserve all non-negotiable clinical and privacy gates; technical availability is not evidence of clinical validation. Do not manipulate consent to make a test pass.
- **No fabricated success:** If Flask, Chrome, Ollama, Docker or hardware is inaccessible, mark relevant tests `NOT RUN/BLOCKED` with exact reasons and reproduction steps. A screenshot of illustrative UI does not count as AI E2E. No invented performance figures, human usability findings or model accuracy.
- The final answer must be supported by actual executed tests, durable evidence and the produced source archive. The deliverable is a **working jury-ready prototype**, not a “plan to make one later.”
