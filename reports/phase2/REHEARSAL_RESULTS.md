# Phase 2 — native jury rehearsals

- Fresh private workspace, real Flask/SQLite/Chromium/Ollama: **107 PASS**, 86.62s, `raw/fresh-20261027T152001Z-browser.log` and XML. Additional coherent four-form history and restart capture completed through authenticated APIs.
- Same workspace restarted with no reset: existing session/score/history/keys verified first, then **107 PASS**, 89.96s, `raw/restart-20261027T152223Z-browser.log` and XML. Existing database and keys retained; coherent fixture history refreshed through normal actions.

Both complete automated scripts cover all four roles, both guest auth paths, four forms and server validation, 77 medicine DOM field checks / 242 records, actual Qwen extraction and private chats, clinician review/draft/referral, researcher filter/methodology/CSV, clinic name opt-in/revoke, staff full name, intake/messages and appointment confirmation. No successful HTTP response was mocked. Automation times are not the 10–15 minute human demo duration.

Method: `scripts/jury_rehearsal.py --mode fresh|restart --workspace <PRIVATE OUTSIDE SOURCE> --port 8767`. The harness refuses nonempty fresh workspaces, starts only localhost, uses ordinary accounts/CSRF/consent and stops its own server afterwards. Credentials, cookies and operational logs remain in the private workspace.

Source regression after these rehearsals is running in `raw/source-regression.log`; no Phase 3 gate is granted before review. Baseline partial/guarded features are retained; a passing core rehearsal is not exhaustive action coverage. See `FEATURE_PARITY.csv` and `API_REGISTRY.csv`. Actual Flask URL map: 249 API operations / 213 paths, matching the refined original-archive inventory. No route or API operation removed.

Final source regression after the native rehearsals: **618 PASS, 5 expected XFAIL, 0 FAIL**, 332.11s (`raw/source-regression.log` and XML). Focused keyboard audit reproduced lost modal-return focus; fixed and both checks pass (`keyboard-before.log`, `keyboard-after.log`). Model actions now show pending state and prevent duplicate clicks; actual physician assignment/result and real Qwen/draft/referral regression pass (`ai-progress-and-modal-regression.log`, 2 PASS). Frontend suite PASS.

Supplemental native catalog search/cross-link/back/empty recovery PASS (`catalog-search-after.log`); wrong-role guest transfer and other registered patient isolation PASS (`search-and-guest-isolation.log`, where the initial catalog assertion only mismatched unchanged source title capitalization). No successful batch was discarded or rerun to conceal failures. Source/API parity reviewed in PARITY_STATUS.json; remaining action breadth stays PARTIAL.
