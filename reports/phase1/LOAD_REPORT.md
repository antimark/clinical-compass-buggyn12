# Phase 1 — bounded localhost non-AI load

- 1 independent virtual-user contexts, global cap 2 RPS; actual 1.985 responses/s over approximately 30.22s; n=60, p50=7.31 ms, p95=12.65 ms; p99 omitted (n<100); failures 0. Recovery health: n=5, p50=5.43 ms, p95=7.34 ms; p99 omitted (n<100).
- 3 independent virtual-user contexts, global cap 2 RPS; actual 1.984 responses/s over approximately 30.24s; n=60, p50=6.82 ms, p95=22.06 ms; p99 omitted (n<100); failures 0. Recovery health: n=5, p50=2.90 ms, p95=4.40 ms; p99 omitted (n<100).
- 5 independent virtual-user contexts, global cap 2 RPS; actual 1.988 responses/s over approximately 30.19s; n=60, p50=7.57 ms, p95=17.37 ms; p99 omitted (n<100); failures 0. Recovery health: n=5, p50=2.90 ms, p95=11.21 ms; p99 omitted (n<100).

Virtual-user count is a configured population, not evidence of sustained concurrent in-flight work. Fast local responses and the global rate cap can leave only one request in flight. No claim of saturated capacity is made. No mutation or parallel LLM load. Every sample is flushed; any unexpected HTTP error halts the harness. Resource stop caps: app RSS >6 GiB or sampled app CPU >500%. No host thermal telemetry was collected.

App-only RSS range 41.8–85.0 MiB; sampled process CPU max 2.8% (n=64). Ollama/browser/OS memory is excluded.
