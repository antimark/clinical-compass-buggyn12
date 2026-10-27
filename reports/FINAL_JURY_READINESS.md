# Clinical Compass — final local jury readiness

**Recommendation: READY_WITH_DISCLOSED_LIMITATIONS for the documented localhost synthetic jury demonstration.** Native Mac and Linux/arm64 Docker application work with actual local Qwen, persistent state and all four roles. Clinical/public deployment and exhaustive acceptance of every individual source control remain unapproved/PARTIAL. No P0 failure remains in the tested core journeys.

## Baseline and local commits

Current GitHub baselinec86c09f; origin README675ce74 merged into review branch `codex/jury-ux-docker-20261027`. Local checkpointb9d6aa6, merge6d7978a, selective Stage A97998fa, native Stage B50adacf, Docker Stage Cb611325; final documentation commit is shown by Git and the source ZIP manifest. Nothing pushed; master not overwritten.
Historical patch was inspected, apply-check conflicts recorded, only missing intent ported. Newer guest persistence, research, Linux photo, Ollama/Docker and privacy fixes retained. Source comparison against both the original archive and GitHub675ce74: **102 routes,249 API operations, no removed original static form/command**. All1871 original feature IDs remain,12 new controls added (1883 total). Source preservation does not assert all possible interactions were executed.

## Final evidence

| Gate | Result and scope |
|---|---|
| Native live |126 distinct pytest browser cases PASS:102 forms/catalog/core,8 role journeys,16 new UX/security cases. Separate actual clipboard and6 Mac photo observations PASS. |
| Native source |618PASS,1SKIP (Linux-only Pillow module; native sips path tested),5expectedXFAIL,0unexpected failures;317.28s. Final package/privacy22 focused PASS; frontend npm contracts PASS (simulated/source, not live). |
| Docker live |126 distinct pytest cases PASS:117 batch +10 final batch with one repeated case counted once. Actual clipboard, valid Linux photo/metadata/ACL,4 invalid uploads, and final persisted photo read PASS. |
| Actual Qwen |Native NLP/review workflow30.619s, patient/doctor chats10.572/10.564s; Docker22.194/8.570/8.553s. Mode local_llm, exact source evidence/citations and private histories asserted. These are task wall timings, not TTFT or a latency distribution. |
| Durability |Actual native process restart and Docker down/up/restart preserve session, score/history, actual volume key hashes, published manual plan, paired messages and photo. Fresh/restarted workspace gates are separately evidenced. |
| Privacy |Consent-bound invitation/recipient/single-use/revoke, CSRF, draft versus publication, fresh-session doctor denial after link revoke, pairwise visibility, patient-private chat, staff names and separate clinic FIO opt-in/revoke PASS. Evaluation foreign-tenant identities rejected401 before data; deeper ACL source security tests PASS. |
| Catalog/research |All242 discoverable records;77 medicines and all nonempty permitted nested source fields checked in actual DOM in both modes. Source-backed dosing labels, pagination/internal links. Independent synthetic research12 observations/10present/2missing/mean3.5, A/B filter, formula and aggregate-only CSV PASS. |
| Docker operations |Nonroot10001, workspace0700/keys0600, Alembic0018, localhost-only publication, pinned runtimes/model, bounded fixed bridge;487 functional files match running image/source SHA256 both directions; standalone image has no private runtime files or model weights. |
| Measurements |Docker60 actual non-AI reads/0errors, observed1/3/5 peak clients; p9517.85/25.17/28.74ms. App end-batch~110.5–110.9MiB. Separate earlier native335 HTTP observations retained. No saturation/SLO claim. |
| Delivery |Clean source+instructions archive and separate sanitized QA archive, manifest/per-file checksums and ZIP checks recorded in deliverables. No DB, generated identities, cookies, keys, weights or private full trace shipped. Fresh extracted source without Git additionally passed5 live smoke cases and metadata/evidence bootstrap; see phase3/ARCHIVE_VALIDATION.md. |

Full reports: [native](phase0/HANDOFF_NATIVE_RESULTS.md), [Docker](phase3/DOCKER_TEST_REPORT.md), [performance](phase3/PERFORMANCE_REPORT.md), [parity](phase2/FEATURE_PARITY.csv), [Docker parity](phase3/DOCKER_PARITY.csv), [runtime match](phase3/RUNTIME_SOURCE_MATCH.json), [trace manifest](phase3/TRACE_MANIFEST.json), [defects](phase3/DEFECTS.csv). Raw failed attempts/retries are retained locally; sanitized release evidence excludes private full traces, headers/bodies and invitation tokens.

## Runnable paths

- Current native synthetic app: `http://127.0.0.1:8769/#/demo/journeys`, private workspace `/private/tmp/clinical-compass-jury-handoff-20261027`; native process restarted and left running.
- Current Docker synthetic app: `http://127.0.0.1:8768/#/demo/journeys`, project`ccjuryqa20261027`; same volume/project resumes, no reset. Real native Ollama loopback GPU is the accepted model topology.
- Commands/provisioning: [JURY_RUNBOOK](../docs/phase04/JURY_RUNBOOK.md), [Docker guide](../docs/phase04/DOCKER_JURY_RUNBOOK.md), [10–15min script](../docs/phase04/JURY_DEMO_RUNBOOK.md). Coherent private `jury-demo-patient.json` selects the patient whose four forms, plan, observations and messages belong to the same linked doctor. No credentials bundled.
- Run on existing native environment: `CC_PYTHON=/Users/mark/miniforge3/envs/cc-m1/bin/python bash scripts/evaluation.sh serve --workspace /private/tmp/clinical-compass-jury-handoff-20261027 --port 8769` (do not start another process if already running).
- Resume tested container: `CC_JURY_PORT=8768 docker compose -p ccjuryqa20261027 up -d`. Fresh-machine/model initialization is in the Docker guide. Native fallback remains available.

## Disclosed limitations

CPU-sidecar Ollama installed the exact model but a real180s readiness call timed out (load111.73s). It remains an optional diagnostic topology, **not accepted AI mode**. The default restricted Mac host-GPU bridge is actually proven; host Ollama stays127.0.0.1, no cloud/model allowlist expansion.

Read-only route matrix:83READ-ONLY PASS,8 newly proven LIVE WORKFLOW PASS,7conditional routes NOT_RUN and4guarded/partial baseline routes. Full1883-row action breadth remains PARTIAL. Genuine invited staff OIDC/MFA and legacy study grants are unconfigured; some import/shared-draft/opaque review paths remain partial or not run. Those functions and guards were preserved, not hidden to improve the demo. External source-site uptime was not checked. The adherence action is a saved self-report, not a full per-dose missed-days calendar. Qwen snapshots expire after5minutes; persisted reviews/documents survive. No fresh screenshot/recording is falsely attributed to an expired snapshot.

PHQ/GAD editions are unapproved evaluation drafts, scores mechanical. Catalog drugs are references. NLP/routing are experimental, require evidence and physician decisions. Draft edits, signature, publication and referrals are separate explicit actions. No autonomous diagnosis, prescribing or emergency monitoring. No clinical validation, real professional verification, public deployment security or exhaustive action completion is inferred from local tests.

No screencast was recorded and no Drive file replaced. The storyboard is updated for the final real workflows; supplied screenshot ZIP is a real browser capture set with its own documented limitations.

## Proposed publication after review

No push has been executed. Proposed review-branch command only:

```bash
git push -u origin codex/jury-ux-docker-20261027
```

Do not merge/push master without the operator's explicit approval.
