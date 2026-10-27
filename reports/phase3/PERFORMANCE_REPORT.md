# Docker measurements — actual local app, native host GPU model

Run `20261027T204235Z`; 60 actual catalog HTTP reads, zero unexpected failures. One/three/five independent clients, batches paced to an average maximum two requests/second. No mutation or AI load. Raw CSV flushes/fsync after each response; batch JSONL after each population.

| Clients | n | p50 ms | p95 ms | Observed peak in flight | Failures | Docker memory sample | CPU sample |
|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 20 | 10.40 | 17.85 | 1 | 0 | 110.7MiB / 1GiB | 1.22% |
| 3 | 20 | 18.03 | 25.17 | 3 | 0 | 110.5MiB / 1GiB | 0.88% |
| 5 | 20 | 18.75 | 28.74 | 5 | 0 | 110.9MiB / 1GiB | 0.97% |

These n=20 p95 values are exploratory interpolated observed percentiles, not capacity/SLO guarantees. Burst concurrency was observed, not inferred from configured client count. No p99 is claimed. Resource columns are end-of-batch Docker samples, not peaks or total host/model memory. The native Qwen process and Docker VM overhead are outside these app cgroup figures.

Compare separately with the earlier native Phase1 baseline: `reports/phase1/PERFORMANCE_REPORT.md` / LOAD_REPORT.md (335 ordinary reads, 0 unexpected errors; 1/3/5-user capped runs60 samples each). That baseline predates the UX handoff; no false final-version native rebenchmark is asserted. It included one real physician Qwen chat10.279s and~19.48 generated tokens/s; TTFT was unavailable.

Final UI/API Qwen journeys are acceptance samples, not an LLM latency distribution: native patient/doctor chat10.572/10.564s; container8.570/8.553s; container NLP+review/draft/referral22.194s, native corresponding workflow30.619s (exact JUnit). Wall task timings include browser/API/review actions and must not be relabelled pure model inference or TTFT. Model job metadata is retained in raw/chat-qwen-metadata.jsonl and phase0 equivalent. All use actual qwen3:4b-instruct; no mocked response was measured.

CPU sidecar is separate: exact model installed but readiness generation timed out180s; load111.73s. It is not the accepted AI topology. Mac host Ollama100%GPU/context4096 was actually observed. See raw/handoff-final-model-processor.txt, final runtime/model metadata and DOCKER_TEST_REPORT.md.

Raw: raw/container-http-latency.csv, container-load-batches.jsonl, handoff-container-load.log; no headers, cookies, source texts or patient identifiers in the measurements.
