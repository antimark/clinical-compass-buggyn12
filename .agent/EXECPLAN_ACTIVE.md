# Active execution plan — jury release

Phase 0 IN PROGRESS; Phase 1–3 NOT_RUN. Coordinator owns integration, schema, shared harness and packaging. Subagents used: 0/4.
Source revision: distributed checkout without .git; baseline PACKAGE_MANIFEST.json retained.

1. Baseline: source/contracts, native runtime and isolated workspace, focused tests. Evidence: reports/phase0/raw/preflight.jsonl.
2. Live guest four-form score/persistence and auth failures; fix root causes and rerun.
3. Catalog 242 entries / all 77 medicine fields in browser; linked physician, research and clinic consent journeys.
4. Inventory controls at 360/768/1280 and both themes; classify gaps and repair P0/P1.
5. Full source regression and restart checks; Phase 0 gate before sequential phases 1–3.

Sandbox: /private/tmp/clinical-compass-jury-20261027 (private, outside source, synthetic only).
Changes are reversible source edits; retain existing schema/ACL/consent/CSRF. Add migration only if durable contracts require it.
Native commands use existing cc-m1 binaries. Browser traces/session state stay private in sandbox; sanitized evidence only in reports.
Last completed batch: native environment preflight. Next: focused tests and live launch. Exact resume details: .agent/CHECKPOINT.md.

<!-- measured-progress -->
Latest completed: `inventory /clinic/invitations` (PARTIAL).

Append-only observations (includes baseline failures and reruns; not unique acceptance counts):

- Chromium layout overflow; not full accessibility audit: PASS 30
- live Flask + SQLite + Chromium: FAIL 3
- live Flask + SQLite + Chromium: PASS 153
- live read-only route inventory: BLOCKED 31
- live read-only route inventory: PARTIAL 15
- live read-only route inventory: PASS 83
- real Chromium trace; redacted timeline exported: PASS 1
- source pytest; not live E2E: FAIL 17
- source pytest; not live E2E: PASS 1368
- source pytest; not live E2E: SKIP 12

Raw: `reports/phase0/raw/scenarios.jsonl`. Phase 0 remains INCOMPLETE until all release gates are reviewed.

Phase 0 checkpoint: core native gate PASS with disclosed breadth limits; source 618 PASS / 5 XFAIL / 0 FAIL. All original 102 routes/232 API operations retained. No known reproduced core P0/P1 remains; guarded OIDC/legacy study and incomplete preview breadth remain tracked P2/NOT_RUN. Phase 1 now IN_PROGRESS: bounded localhost latency/load, scripted task timing and one real app Qwen chat timing, then honest measurement report. Phases 2/3 NOT_RUN. Native runtime data remain /private/tmp/clinical-compass-jury-20261027. Source checkpoint should be committed locally after backup; no secrets or raw QA state tracked.
