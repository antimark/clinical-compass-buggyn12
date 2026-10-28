# Phase 2 — INCOMPLETE

Current rehearsal `restart-20261027T152223Z`. All raw results append after each scenario. Source functionality must be preserved; no gate is inferred from render-only inventory.

Resume current existing workspace with `PYTHONPATH=backend:. /Users/mark/miniforge3/envs/cc-m1/bin/python scripts/jury_rehearsal.py --mode restart --workspace /private/tmp/clinical-compass-jury-phase2-20261027 --port 8767`; successful earlier scenarios remain in raw evidence.

<!-- live-evidence-phase2:start -->
Latest completed: `backend/tests/test_contract.py::test_session_required` (PASS).

Append-only observations (includes baseline failures and reruns; not unique acceptance counts):

- live Chromium accessibility spotcheck: PASS 2
- live Chromium keyboard spotcheck: FAIL 1
- live Chromium keyboard spotcheck: PASS 1
- live Flask + SQLite + Chromium: PASS 231
- real authenticated HTTP; explicit synthetic fixture: PASS 8
- source pytest; not live E2E: PASS 615
- source pytest; not live E2E: SKIP 5

Raw: `reports/phase2/raw/scenarios.jsonl`. This automated observation summary does not set the phase gate.
<!-- live-evidence-phase2:end -->

Diagnosis→medication browser http://127.0.0.1:8769: 5 scenarios PASS; last=manual_title_clears_reference_binding; raw reports/phase2/raw/diagnosis_medicine_20261028.jsonl flushed. Resume with saved raw document ID; no repeat of successful batches.

Diagnosis→medication browser http://127.0.0.1:8768: 5 scenarios PASS; last=physician_diagnosis_persisted_draft; raw reports/phase2/raw/diagnosis_medicine_20261028.jsonl flushed. Resume with saved raw document ID; no repeat of successful batches.

Diagnosis→medication browser http://127.0.0.1:8768: 10 scenarios PASS; last=manual_title_clears_reference_binding; raw reports/phase2/raw/diagnosis_medicine_20261028.jsonl flushed. Resume with saved raw document ID; no repeat of successful batches.


2026-10-28 F41.1→Aviandr COMPLETE: existing exact source-match API connected to structured visit diagnoses and treatment UI; name+pinned reference selection only, no dose/order or auto sign/publish. Immutable references initialized for unseeded evaluation without accounts/patients; fresh/restart test PASS.24 distinct medical-reference tests PASS via focused runs, frontend contracts + pinned-version/escaping module PASS; native/Docker real browser create/edit/reload/exact/negative/clear/catalog/back/name-only checks PASS. One synthetic encounter draft per demo, no plan/order. Native private consistent backup retained. Evidence reports/phase2/DIAGNOSIS_MEDICATION_20261028.md and append-only raw/diagnosis_medicine_20261028.jsonl; new screenshots docs/final_demo/screenshots/diagnosis_medication_20261028 and ZIP. Intermediate environment/test harness/empty seed failures recorded with fixes. Both demo apps remain running; Docker rebuilt with existing volume. No clinical rule/provider change, no new Qwen queries, no full regression repeated, no push/master update. Baseline26a793d; final local commit follows. Subagents1/4. Resume: open existing synthetic doctor patient treatment; do not rerun completed checks just to resume.

Catalog-only http://127.0.0.1:8769:n=5;last=all_source_fields_aspirin_low_dose PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=10;last=all_source_fields_citalopram PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=15;last=all_source_fields_clozapine PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=20;last=all_source_fields_duloxetine PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=25;last=all_source_fields_guanfacine PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=30;last=all_source_fields_levetiracetam PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=35;last=all_source_fields_maritupirdine PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=40;last=all_source_fields_nalmefene PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=45;last=all_source_fields_ofatumumab PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=50;last=all_source_fields_paracetamol PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=55;last=all_source_fields_propranolol PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=60;last=all_source_fields_ropinirole PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=65;last=all_source_fields_topiramate PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=70;last=all_source_fields_atomoxetine_canon_40mg PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=75;last=all_source_fields_seroquel_quetiapine_ir_100mg PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=80;last=visual_jump_light_390 PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=5;last=visual_jump_dark_1440 PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8768:n=5;last=visual_jump_dark_1440 PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8769:n=5;last=visual_jump_dark_1440 PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.

Catalog-only http://127.0.0.1:8768:n=5;last=visual_jump_dark_1440 PASS; raw reports/phase2/raw/catalog_visual_20261028.jsonl flushed. Existing tests reused; no full app audit.


2026-10-28 catalog hierarchy COMPLETE: six medicine essentials first, orange side rules/borders/bold contrast, extra outlined warnings, keyboard jump links, responsive light/dark/mobile; delayed opening scroll fixed. Full source fields kept expanded and untruncated; sources/rules/ACL unchanged. Focused source5 PASS; frontend102routes0errors/contracts PASS. Native77 medicine scalar-field browser cases PASS + final3medicine/theme/mobile/scroll smokes; final Docker smoke PASS, saved volume retained. F41.1→Aviandr2cf8062 preserved and real native/Docker read/nav/name-only proof PASS; no new plan/order/LLM. Evidence reports/phase2/CATALOG_VISUAL_20261028.md, CATALOG_VISUAL_RESULTS_20261028.json, append-only raw/catalog_visual_20261028.jsonl, docs/final_demo/screenshots/catalog_visual_20261028. Baseline2cf8062; new visual commit follows. Subagents1/4, no push/master changes. User next: review native8769/Docker8768; git push -u origin codex/jury-ux-docker-20261027 only on user action. Existing untracked duplicate screenshot folder untouched.
