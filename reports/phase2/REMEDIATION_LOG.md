# Phase 2 preservation and remediation

| Issue / requirement | Change | Verification |
|---|---|---|
| Lost submit-response duplicate | Exact patient/form transfer-key recovery using existing submissions | Phase 0 failed reproduction, fixed live retry; repeated in both 107-case rehearsals |
| Missing researcher dataset | Independent deterministic fixture restored and source allowlist extended; real filter/methodology/CSV UI | Research browser test in both rehearsals |
| Qwen paraphrased evidence | Source excerpts constrain generation; independent exact evidence validator remains | Actual extraction/evidence/review/draft/referral and source validator regressions |
| Modal blocked later route | Close on hash/back navigation; retain all modal actions | Result modal followed by live Clinical Intelligence path |
| Linked unpublished doctor missing from intake selector | Add existing authorized links without publishing private physician profile; public profiles retained | Actual intake/messages/appointment test |
| Occupied repeat-test appointment | Harness reads real slots and selects a free time; server 409 retained | Initial genuine conflict retained, targeted replay and fresh/restart rehearsals pass |
| Source tests referenced old UI | Current designer renderer, safe URL/escaping, route/CSRF/error-state contracts tested; obsolete filenames no longer treated as runtime requirements | Phase 0 full 618 PASS / 5 XFAIL; Phase 2 regression pending |
| Preserve all baseline functions | Original archive + DOM controls + actual Flask map registry | 102 UI routes and 249 API operations retained; 1,871 feature-parity rows |
| Avoid state/secret leakage | Private QA workspace, generated credentials, stable keys, private full trace and redacted timeline | Source backup manifest; local Git checkpoint eb64d3f excludes runtime/raw state |

No implemented function was deleted, disabled or replaced by a static demonstration. Existing guarded or partial functions remain classified and reachable. Role-/tenant-/source-ACL, consent, CSRF, revision checks, idempotency and clinician authority were retained. No schema migration was needed for these repairs.

Additional focused repair: modal ESC now restores focus to its account trigger; a real failing keyboard check was retained before the fix. Long-running Clinical Intelligence commands show a bounded pending UI and re-enable on completion/error, retaining all existing actions. Focused real doctor flow and keyboard replays pass. No backend clinical guard changed.
