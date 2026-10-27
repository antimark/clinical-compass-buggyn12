# Clinical Compass — current jury operator guide

Use only the private synthetic Evaluation Sandbox. PHQ/GAD Russian forms are unapproved evaluation drafts; score is a mechanical sum. Qwen, tags and routing are experimental; evidence and clinician review remain required. A reference card is not a prescription. There is no emergency monitoring or autonomous diagnosis/signature/publication.

Native setup and guest/catalog/research/admin script: [native demo runbook](JURY_DEMO_RUNBOOK.md). Container setup, exact local model pin and persistence: [Docker runbook](DOCKER_JURY_RUNBOOK.md). Current readiness/evidence: [final report](../../reports/FINAL_JURY_READINESS.md).

For the existing native environment:

```bash
export CC_PYTHON=/Users/mark/miniforge3/envs/cc-m1/bin/python
export CC_CONDA_ENV=cc-m1
export PYTHONPATH=backend:.
# Current verified synthetic sandbox; restart does not reset it.
"$CC_PYTHON" -m cc_api.evaluation_launcher serve \
  --workspace /private/tmp/clinical-compass-jury-handoff-20261027 --port 8769
```

If that server is already running, open `http://127.0.0.1:8769/#/demo/journeys` rather than starting a second process. For a new operator workspace choose a new private path; use `prepare_actors.py --workspace ...` and `evaluation_launcher privacy-setup --workspace ...` before serve. Generated role credentials stay mode 0600 outside source. Use independent browser profiles for roles. The patient is registered in the real UI; an invitation requires matching recipient, explicit categories and consent. QR is a secret for the recipient, not a slide asset. A localhost QR works on this Mac, not on a remote phone.

## Updated 10–15 minute route

1. Guest (2 min): PHQ/GAD draft → exact provisional sum → login or registration → server result/history. Explain unsaved versus server-confirmed state.
2. Invite (1 min): doctor creates recipient-bound invite, shows link/key/QR privately; patient previews categories and explicitly accepts. Show patient access categories.
3. Doctor (3 min): linked patient → intake → Clinical Intelligence → real Qwen tags and exact evidence. Review a tag; manually edit an unsigned chart suggestion. Snapshot is transient (five minutes); persisted reviews/documents remain. If expired, explain and run a bounded analysis rather than pretending stored tags are a fresh result.
4. Doctor → patient (2 min): visit/treatment tab → manually authored synthetic draft → edit → separate sign → separate publish. Patient sees the published plan with authored details; Today records a self-reported completion. Use test prose, not invented clinical doses. Optional behavioral plan uses the same explicit lifecycle. Old records stay available.
5. Communication/safety (1 min): linked pair messages; actual observation-derived signal → readable cause/evidence → physician review → reload. Signals do not establish a risk forecast or emergency response. A lack of signals is shown honestly.
6. Catalog (1 min): full medicine source fields, prominent dosing section, related/source links; 242 records / 77 medicines. Do not imply medical review or licensing release.
7. Research (1 min): synthetic dataset A/B/all filter, n/nonmissing/missing/mean, methodology and aggregate CSV; no patient-level export or causal treatment claim.
8. Clinic/privacy (1–2 min): staff full name; patient FIO requires separate name-only consent within the clinic; revoke and reload. Patient may revoke a doctor link and separately control pairwise doctor visibility. Subsequent server access must fail.
9. Resume (1 min): reload results, restart same private workspace or Compose project without deleting its volume, confirm retained state.

No screencast or Drive replacement is claimed. The storyboard describes real actions; record only after reviewing the final acceptance report. Never record invitation tokens, credentials, cookies or private traces in a public presentation.
