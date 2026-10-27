# Clinical Compass — 10–15 minute synthetic jury demonstration

This is an experimental evaluation prototype. The four Russian PHQ/GAD drafts are unapproved; scores are mechanical sums, not diagnosis or risk assessment. Reference medicines are not prescriptions. Local Qwen suggestions require physician review. No emergency monitoring or professional credential verification is claimed.

## Reproducible native setup

Use the existing `cc-m1` environment; do not recreate or upgrade it. From the source folder:

```bash
export CC_PYTHON=/Users/mark/miniforge3/envs/cc-m1/bin/python
export CC_CONDA_ENV=cc-m1
export PYTHONPATH=backend:.
# Choose a NEW private path outside source. Fresh refuses existing content.
"$CC_PYTHON" scripts/jury_rehearsal.py --mode fresh --workspace /private/tmp/clinical-compass-jury-new --port 8767
# Verify retained state and replay without reset:
"$CC_PYTHON" scripts/jury_rehearsal.py --mode restart --workspace /private/tmp/clinical-compass-jury-new --port 8767
bash scripts/evaluation.sh serve --workspace /private/tmp/clinical-compass-jury-new --port 8767
```

The rehearsal creates ordinary operator roles, registers synthetic patients through the normal UI, accepts recipient-bound invitations with explicit scopes, exercises real APIs/Qwen and writes four-form history for one coherent linked patient. It never imports a clinical database, disables gates, or installs dependencies. The test server stops at the end; `serve` reopens the same state. `/private/tmp` is suitable for disposable QA; an operator may choose a new private persistent directory under Application Support for long-term retention. Never put the workspace in the source archive.

The **already tested** workspace on this Mac is `/private/tmp/clinical-compass-jury-phase2-20261027`, port 8767. Its private `jury-actors.json` contains generated doctor/researcher/clinic-admin credentials; `jury-linked-patient.json` contains the current coherent patient. View these only locally; never include them in screenshots, reports, source or evidence archives. No passwords are bundled in the source. Use separate browser profiles/contexts for the four roles; ordinary tabs in the same profile share login cookies.

Open `http://127.0.0.1:8767/#/demo/journeys`. Native Ollama must serve `qwen3:4b-instruct` on `http://127.0.0.1:11434`. Installed model digest in the verified run: `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`. Source archives contain no model weights. An installed tag is not proof of inference; the browser rehearsals prove actual inference.

## Timed operator script

| Time | Role / action | Expected observable evidence |
|---|---|---|
| 0:00–1:00 | Guest: `/assessments`; open PHQ-9, answer every item with synthetic 0–3 values, submit | Exact provisional sum, source questions and explicit unsaved/tab-local notice. Reload retains it in the same tab. |
| 1:00–2:00 | Click “Войти и сохранить”, use the synthetic patient account | Server-confirmed canonical `/patient/questionnaires/<id>/result`; profile → “Открыть историю результатов” shows it. Do not call the provisional screen saved. |
| 2:00–3:00 | In a separate guest context, GAD-7 → “Зарегистрироваться и сохранить”; use a fresh `.test` account and your own/generated private password | Normal registration and server result. PHQ-2/GAD-2 use the same working flow; coherent patient fixture also has all four results. |
| 3:00–4:00 | Doctor: `/doctor/invitations` → recipient-bound invitation; patient opens token, previews scopes and explicitly accepts | Confirmed relation in patient specialists and physician patient list. The fixture already has one; creating another remains a real action. |
| 4:00–5:00 | Doctor `/doctor/questionnaires`: assign a draft form to linked patient; patient completes; doctor opens result | Real assignment, mechanical score and answers in a result modal; private drafts and unlinked access remain guarded. |
| 5:00–7:30 | Patient `/patient/requests/new`: select linked doctor and send synthetic text with separate case consent. Doctor opens patient → Clinical Intelligence → select this intake → “Запустить анализ” | Actual local Qwen mode, exact evidence quotes and proposed tags. Allow bounded native inference time; do not label deterministic fallback as Qwen success. |
| 7:30–9:00 | Doctor reviews a proposed tag; edits proposed chart text and confirms saving an unsigned draft; writes independent referral rationale and confirms | Persisted review, editable unsigned chart document, manually attributed referral. No automatic diagnosis, prescribing, signature or publication. |
| 9:00–10:00 | Open a medicine in `/clinical-library?type=medicine`; inspect source sections, nested data, cross-links and second page | 77 medicines across two pages, all 242 catalog records. No source fields are replaced with invented prose. |
| 10:00–11:00 | Researcher `/research/demo-v3`: select A/B, calculate, inspect methodology and download CSV | Actual file-backed synthetic query. All: 12 observations / 10 present / 2 missing / mean 3.5; A: mean 3, B: mean 4. CSV is the unfiltered aggregate, explicitly labelled. |
| 11:00–12:30 | Patient `/patient/admin-identity`: stored fictional values remain hidden until separately granting the name-only template. Clinic admin `/clinic/patients` and `/clinic/staff`; revoke on patient side and reload admin | Staff full name is available. Patient FIO appears only from consent-authorized identity fields and disappears after revocation. No diagnosis/diary projection. |
| 12:30–14:00 | Patient/doctor case messages and doctor appointment offer; patient confirms. Optionally show patient-private AI chat and doctor contextual chat | Real messages, guarded booking conflict handling, persisted confirmation; Qwen histories are private to their audience. |
| 14:00–15:00 | Reload history and return to journey index; explain disclosed limits | The result remains saved; ordinary navigation recovers without a misleading success toast. |

## Recovery and truthful fallback

- If model busy/offline or evidence validation fails, keep the source and permissions; show the returned diagnostic/mode. Retry only when the condition changes. The separate `/doctor/clinical-copilot` teaching illustration stays labelled and never counts as real Qwen inference.
- If a save response is lost, the guest result remains provisional; retry recovers the same committed transfer using its nonce. Do not clear browser data or report failure as a successful save.
- If appointment returns 409, choose another genuinely free slot; do not disable conflict protection. Automated rehearsals query actual slots before selecting time.
- For a local stop/restart, Ctrl+C then repeat `serve` with the **same** workspace and port. Preserve DB plus both private keys together. Do not delete a workspace to repair a startup error.
- Legacy researcher study/cohort screens retain their actual grant checks. A new evaluation workspace has no legacy study grants; the independent synthetic dataset is a working alternate path, not a claim that the legacy workflow passed.
- Invited professional enrollment retains genuine OIDC/MFA and `synthetic_dev` requirements. The local evaluation deployment does not bypass those gates. Existing staff listing works; invited enrollment remains separately blocked until a real provider is configured.
- Some baseline video/review/import/psychotherapy/opaque-thread paths remain explicit partial previews. They were preserved and are separately classified in feature parity; no working feature was hidden to make the rehearsal pass.

Evidence: `reports/phase0/TEST_REPORT.md`, `reports/phase1/PERFORMANCE_REPORT.md`, `reports/phase2/REHEARSAL_RESULTS.md`, `FEATURE_PARITY.csv`. Full Playwright traces/cookies remain private; shared captures are redacted. Overall clinical/production readiness is not asserted.
