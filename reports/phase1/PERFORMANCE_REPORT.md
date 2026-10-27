# Phase 1 — measured native performance (run 20261027T151022Z)

Status: MEASURED. Native macOS 26.5 arm64, 16 GiB, existing cc-m1; Python 3.11.17 (main, Oct 13 2026, 16:38:53) [Clang 21.1.8 ]. Source checkpoint `eb64d3f3e68df552afeec5dbaecf0f412293b528`. Flask development server on localhost with persistent synthetic SQLite, native host Ollama. This is no production SLO, clinical validation or human usability study.

| Role | Endpoint | Observed latency |
|---|---|---|
| guest | `/api/v1/health` | n=20, p50=2.40 ms, p95=3.41 ms; p99 omitted (n<100) |
| guest | `/api/v1/clinical-catalog/search?type=medicine` | n=20, p50=7.02 ms, p95=10.63 ms; p99 omitted (n<100) |
| guest | `/api/v1/clinical-catalog/medicine/sertraline` | n=20, p50=3.11 ms, p95=6.05 ms; p99 omitted (n<100) |
| patient | `/api/v1/patient-experience/dashboard` | n=20, p50=10.47 ms, p95=14.60 ms; p99 omitted (n<100) |
| doctor | `/api/v1/doctors/me/linked-patients` | n=20, p50=12.77 ms, p95=15.08 ms; p99 omitted (n<100) |
| researcher | `/api/v1/research/demo-datasets/synthetic_research_v3/summary` | n=20, p50=6.09 ms, p95=9.06 ms; p99 omitted (n<100) |
| clinic_admin | `/api/v1/p1/clinic/staff` | n=20, p50=6.41 ms, p95=8.90 ms; p99 omitted (n<100) |


Percentiles use linear interpolation over observed samples. Per-endpoint n=20 makes p95 exploratory; per-endpoint p99 is deliberately omitted. Baseline contains the first read/cache warm-up rather than claiming every request is equally warm. Non-AI requests are paced to 2 RPS, on the same machine and sandbox. No external endpoints were load tested.

| Scripted task | Successful samples / failed attempts | Median automation time |
|---|---|---|
| guest_login | 3 / 0 | 0.656 s |
| guest_register | 3 / 0 | 0.631 s |
| role_navigation | 3 / 1 | 0.397 s |


Scripted times include automation, validation and actual server-confirmed results. They are not human Time on Task. One navigation attempt raced the login redirect because the harness did not await UI completion; its FAIL remains in raw/task_timing.csv and errors.csv. The wait was corrected. A model-setup request also received a correct 422 because the harness supplied a non-UUID idempotency key; no model generation occurred in that failed setup (measurement-resume1.log). UUID keys and a private resumable request state were added. Only incomplete measurements resumed; the 140 successful baseline samples were preserved.

Qwen: {"run_id": "20261027T151022Z", "timestamp": "2026-10-27T15:15:10.749879+00:00", "status": "PASS", "n": 1, "wall_seconds": 10.27884812495904, "model": "qwen3:4b-instruct", "mode": "local_llm", "timings": {"inference_wall_ms": 9971, "prompt_generation_ms": 6, "queue_ms": 4, "wall_ms": 9986}, "prompt_eval_count": 393, "eval_count": 80, "prompt_eval_duration_ns": 1909313000, "generation_duration_ns": 4107370000, "ttft": "NOT_AVAILABLE: backend non-streaming request; wall latency is not TTFT", "tokens_per_second": 19.477183696623385}

The model sample uses the real physician chat API and durable job, no mocked response. n=1 cannot support an LLM distribution or accuracy claim. TTFT is unavailable with the non-streaming backend. Token throughput is included only when the backend exposes count and generation duration. Source/evidence/clinician requirements remain unchanged.

HTTP unexpected failures: 0 / 335 measured ordinary reads. Browser task failed attempts retained: 1. App-only RSS range 41.8–85.0 MiB; sampled process CPU max 2.8% (n=64). Ollama/browser/OS memory is excluded.

Bottlenecks/limits: local model generation dominates model-backed task latency; n=1 is insufficient for tail claims. Ordinary endpoints should be evaluated on larger independent samples before adopting targets. Source audit found duplicate render-triggered GETs; no security gate or working feature was removed to reduce measured time. Legacy study grants, genuine invited OIDC/MFA enrollment, complete action coverage and Docker remain separate gates.

Raw evidence: raw/http_latency.csv, raw/task_timing.csv, raw/errors.csv, raw/resources.jsonl, raw/llm_calls.jsonl and raw/environment.json. Resume command is preserved in PROGRESS.md and .agent/CHECKPOINT.md.
