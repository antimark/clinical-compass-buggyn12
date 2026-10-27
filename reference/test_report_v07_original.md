# Verification report — authoring environment, 2026-10-18

## Executed

- `python -m compileall -q backend`: **PASS** (syntactically valid backend modules).
- `node frontend/dist/tests/smoke_mock_states.cjs`: **PASS** — 21 mock UI-state/route display assertions; NOT a server ACL test.
- `node --check` for frontend JavaScript files: run as part of final packaging verification.
- `python -m pytest -q`: **NOT EXECUTED**: the authoring container lacks Flask; attempted installation fails because package index DNS/network are inaccessible. `tests/test_workflows.py` and existing `backend/tests/test_contract.py` are provided to run by maintainers after installing requirements.

## Assertions encoded in backend tests

- Previsit case limited to participants; unrelated physician gets HTTP 403.
- Exactly one patient's message before first doctor reply; then dialogue opens.
- Appointment offer and patient confirmation without automatic clinical link.
- Invitation issuer role authorization, one-time code redemption, recipient-role restriction.
- Clinic cannot issue doctor-to-patient link.
- Shared-patient pair consent enables and revocation hides shared patient.
- CSRF and researcher-only synthetic aggregate endpoint.

## Known limitations / blockers

1. No full HTTP/server E2E runtime test in current environment.
2. v0.6 frontend is client-state demo; separate API Lab connects actual Flask endpoints. Not yet a unified persisted UI.
3. 86 inventory routes are specification targets, not 86 working pages.
4. Clinic Admin PII reference package copied but not integrated; no production-grade credential provisioning or vault.
5. Real AI summary, provider calls, audio/video and validated clinical algorithms absent by design.
6. SQLite demo store and static fixture data are NOT adequate to protect real health information.
7. Concurrency-safe one-time code redemption needs a transactional uniqueness guard and database migration for production.

## Reproducible commands

```
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
./scripts/test.sh
./scripts/start.sh
```

Manually test `http://127.0.0.1:8000/api-lab.html`: switch to patient, submit case and first message, second message is refused; switch to doctor, open case/reply/offer; switch patient, confirm; switch doctor, issue invitation; switch patient, accept. Try foreign doctor and clinic roles to check 403. Repeat test after clearing synthetic SQLite DB.
