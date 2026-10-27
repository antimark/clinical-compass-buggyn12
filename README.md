# Clinical Compass — Evaluation MVP, Phase04

Current application: Flask + SQLAlchemy/Alembic + vanilla JavaScript, design system v11, Clinical Catalog v5, local Ollama/Qwen. This is a technical evaluation environment, not a clinical pilot or validated medical device. Use generated synthetic or lawfully and properly deidentified cases only. 


```bash
./scripts/evaluation.sh check --workspace "$HOME/Library/Application Support/ClinicalCompassEvaluation"
./scripts/evaluation.sh doctor --workspace "$HOME/Library/Application Support/ClinicalCompassEvaluation" --email expert@evaluation.test
./scripts/evaluation.sh serve --workspace "$HOME/Library/Application Support/ClinicalCompassEvaluation" --port 8766
```

`doctor` prompts twice for your own password (12+ characters); there are no bundled credentials. Open **http://127.0.0.1:8766/** and log in normally. Create a separate patient account using another browser profile; doctor issues an invitation and patient explicitly accepts its scopes. Start with the role-aware **«Начать тестирование»** panel. See [evaluator quickstart](docs/phase04/EVALUATOR_QUICKSTART.md) and [deployment guide](docs/phase04/EVALUATION_DEPLOYMENT.md).

The private workspace must be outside the source folder and readable only by its owner. It contains a stable private session secret and isolated persistent SQLite database; repeat `serve` to resume existing records. Nothing is reset or globally seeded. Back up the workspace only while safely stopped and under an operator retention policy; never send it with the source ZIP. Stop with Ctrl+C. If Conda is absent from PATH, set `CC_PYTHON` to the existing cc-m1 Python executable. `CC_CONDA_ENV` overrides the environment name. Other operating systems/hardware and new dependency installation are NOT_VERIFIED; environment.yml/backend/requirements.txt describe the environment for a separately planned installation.

## Available workflows and boundaries

New cases use real registration, invitations and consent, intake, versioned NLP evidence, independent physician correctness/relevance review, explicitly transferred native drafts, clinical teaching proposals, manually confirmed referrals, and scoped doctor chat. Governed intake safety events use durable outbox → protected local test inbox → explicit physician ACK with audit/readback. Critical severity, urgency, referral category, transport receipt and human review are separate concepts. Local test delivery/ACK does not mean emergency response or care occurred.

Patient **«Справочный AI-помощник»** uses only explicitly selected own intake/private diary and bounded own history. Qwen selects permitted references; server publishes verified public reference extracts, not unrestricted medical model prose. Catalog links/highlights bind current version/digest/publication/rights. Patient AI/private diary do not trigger clinician safety detection or automatically disclose content to a doctor. No24h monitoring, autonomous diagnosis, prescription, treatment change, signature or referral is provided.

Research fixture browsing and the explicitly synthetic NLP lab are available only to their ordinary authorized roles in evaluation/synthetic workspaces. They remain labeled demonstrations and do not import patient sources. Trusted operators can provision ordinary `clinic_admin`/`researcher` accounts with the documented CLI; no clinical grants, professional verification or special evaluator role are created. Licensed questionnaire rights remain separately enforced; technical demo forms do not imply permission to use every scale.

## Verification and distribution

```bash
CC_CONDA_ENV=cc-m1 bash scripts/validate_full.sh --browser
```

The jury-release acceptance checklist is [JURY_RELEASE_ACCEPTANCE.md](docs/phase04/JURY_RELEASE_ACCEPTANCE.md); this is a **future gate**, not a passed test. Earlier evaluation context is in [current acceptance summary](docs/phase04/EVALUATION_ACCEPTANCE_SUMMARY.md). Full team test results, before/after screenshots and detailed evidence are delivered separately in docs/phase04 of the development repository. Earlier phase reports are historical and retain their original scope/status. Strict P0, clinical validation, real PostgreSQL/Keycloak/MFA and professional/email verification are separate gates and must not be inferred from SQLite/demo success.

The organizer ZIP is mechanically allowlisted and checksummed: source/runtime reference assets, tests, current guides and configuration example. It excludes runtime DB/WAL/SHM, secrets/.env, credentials, logs, caches, weights, nested archives and bulky QA captures. `PACKAGE_MANIFEST.json` identifies its source revision and every file checksum; verify with `python scripts/build_organizer.py --output /path/to/package.zip --verify-only`. Team QA screenshots/JSON are delivered separately from this clean source package.

For a separately planned **new-machine installation only**, the legacy Conda setup command is `conda env create -f environment.yml` (requires network and dependency review). It is not needed or executed for this existing cc-m1 evaluation environment. Linux/Windows and freshly installed stacks require their own acceptance before use.


## Journeys and guest pilot assessments — 2026-10-27

- `/#/demo/journeys`: navigation through patient, doctor, researcher, clinic admin routes; incomplete endpoints remain explicitly labeled.
- `/#/assessments`: four *evaluation-draft, unapproved* PHQ/GAD forms; guest can view temporary sum and choose login/registration to save on server. This is synthetic-only; no clinical interpretation.
- `/#/patient/profile` → history of saved questionnaire results; `/patient/admin-identity`: optional, consent-controlled administrative FIO; never exposed without permission.
- Operator opt-in for isolated evaluation privacy template/flags: `CC_CONDA_ENV=cc-m1 bash scripts/evaluation.sh privacy-setup --workspace "$HOME/Library/Application Support/ClinicalCompassEvaluation-QA"`; privacy key stays private in workspace. A separate patient opt-in remains mandatory.
- **Canonical Codex task and evidence protocol**: `docs/phase04/CODEX_JURY_RELEASE_PHASE0_PHASE3_PROMPT_2026_10_27.md` (Phase 0 functionality, Phase 1 technical UX/performance, Phase 2 juror rehearsal/hardening, Phase 3 Docker). Offline/static checks from the prior assembly are not live Flask/Ollama/macOS/Playwright acceptance. The current Docker implementation and actual acceptance scope are documented in [Docker jury runbook](docs/phase04/DOCKER_JURY_RUNBOOK.md) and [release report](reports/FINAL_JURY_READINESS.md); a successful build alone is not acceptance.



Current native and Docker operator commands, synthetic role provisioning and clinical limits: [JURY_RUNBOOK.md](docs/phase04/JURY_RUNBOOK.md).
