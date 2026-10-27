# Stage C — Docker local jury core PASS

Accepted mode: **Linux/arm64 Flask/Gunicorn app + restricted loopback adapter to native Mac Ollama GPU**. CPU-sidecar alternative is preserved but AI readiness BLOCKED by actual180s timeout; it is not promoted to PASS.

## Actual final acceptance

- 117 PASS in43.60s: all102 core/form/catalog cases plus15 new UX cases against the container app. Includes every nonempty permitted field of77 medicine cards, all242 inventory counts, both four-form guest-to-account paths, patient history and retry/ACL.
- Final focused batch10 PASS in49.49s: two affected history/behavioral-document scenarios + all8 role journeys. These make **126 distinct pytest E2E cases** across the final batches; the repeated history case is counted once. No unresolved unexpected failure. This is specific workflow proof, not a claim every source control was activated.
- Actual container Qwen: physician NLP/evidence/review/draft/referral22.194s; patient chat8.570s and doctor chat8.553s, actual local_llm/model/citations asserted. No cloud/mock provider. Initial timeout failures retained; explicit nonthinking/context4096 extraction fixed the remaining NLP timeout without weakening validation.
- Linux photo: actual multipart upload201, normalized PNG, metadata marker absent, UI reload and private read ACL PASS. Malformed/MIME mismatch/pixel bomb/>2MiB all422 with previous image/revision retained. Final real restart photo readback PASS. Linux source codec tests cover JPEG/PNG/WebP and truncation; native sips remains verified.
- Real down/up retained original session, questionnaire score/history and hashes read from the actual volume keys. After final coherent fixture, real app restart retained a published authored plan, paired messages, session/score/history/keys and photo. Both native and container readbacks PASS. No volume deletion, reset, mock DB or host database used.
- Invitation QR origin/key/link, recipient-bound signup, explicit consent, consumed token409, wrong recipient403, revoked404 and missing-CSRF403 proven. Actual clipboard copy action passed separately with no token exported; created test invite revoked.
- FIO separate consent/revoke and staff full name PASS. Foreign-tenant local identities are rejected401 by the Evaluation tenant boundary before any patient data; no guard relaxed to manufacture an authenticated foreign tenant. Deeper same-organization/per-scope/pair ACLs are covered by full source security tests and real linked/unlinked/revocation cases.

## Runtime and parity

Current running image matches **487 functional source files by SHA256 in both directions**, including backend, frontend, catalog, research, migrations and docker runtime: RUNTIME_SOURCE_MATCH.json. Both original source archive and GitHub675ce74 preserve102 UI routes,249 API operations and every originally declared static form/command. FEATURE_PARITY / DOCKER_PARITY contain1883 rows, keeping all1871 earlier IDs and adding12 handoff controls. Uncovered individual actions remain NOT_RUN/PARTIAL; source presence is never E2E proof.

Docker Desktop29.8.1/Compose5.5.1, local desktop-linux Unix socket, Linuxaarch64. AppPython3.11.17; UID/GID10001; workspace0700, keys0600; Alembic0018_safety_patient_chat. Web published127.0.0.1:8768 only; host Ollama remains127.0.0.1:11434, model digest0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0. Native100%GPU/context4096 actually observed. Loopback provider allowlist unchanged. Adapter fixed upstream/paths, no proxies/redirects, single inference, bounded bodies/output/model digest;11 actual protocol denial/inventory checks PASS.

Existing Linux full source run:620PASS/2temporary-executable-mount FAIL/5expectedXFAIL; corrected exec tmpfs focused launcher4PASS resolves those harness failures. New final native full source618PASS/1Linux-only SKIP/5expectedXFAIL covers integration;22 focused package/privacy checks PASS. No unneeded second20-minute Linux full suite was run after platform-independent UX additions. Actual Linux final E2E covers the running app.

## Evidence and limits

Raw: handoff-container-core-ux.xml/log, handoff-container-final-roles.xml/log, handoff-container-photo-edges.log, handoff-container-photo-restart.log, handoff-container-persisted-state.log, handoff-coherent-restart-verify.log, handoff-coherent-plan-message-verify.log, bridge-protocol-checks.jsonl, source JUnit/findings, container-http-latency.csv, container-load-batches.jsonl and append-only scenarios.jsonl. Raw failures/retries preserved. Private full Playwright traces are indexed in TRACE_MANIFEST.json, not shipped. Sanitized browser timeline contains no cookies, headers or bodies.

Coherent synthetic demo fixture created via ordinary auth APIs: four saved forms, manually authored published teaching plan with no clinical dose, own observations and paired messages. Credentials stay outside source in private jury-demo-patient.json / jury-actors.json. Fixture preparation is labelled fixture work, not extra acceptance counts. Do not enter real patient records.

Known limits: genuine invited OIDC/MFA staff enrollment and legacy study grants are unconfigured, some protected baseline review/import/shared-draft/opaque paths remain partial or untested; no feature was hidden/removed. Full missed-dose calendar is not implemented. External source-site availability not verified. Clinical algorithms/instrument editions remain experimental/unapproved, with explicit physician confirmation. No public/clinical deployment readiness or exhaustive action coverage is claimed.

Run instructions: docs/phase04/DOCKER_JURY_RUNBOOK.md and JURY_RUNBOOK.md. Current projectccjuryqa20261027, port8768; same project/volume resumes. Native fallbackport8769 remains working. Never use down-v to resume.
