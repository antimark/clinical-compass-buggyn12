# Phase 1 — INCOMPLETE

Run `20261027T151022Z`; completed successful observations in run: 344. Last: `measurement complete; summarize actual rows`. Raw rows flush after every observation; this count includes HTTP/setup and browser tasks, not unique product acceptance.

Raw files: raw/http_latency.csv, task_timing.csv, errors.csv, resources.jsonl, environment.json and llm_metrics.json as available.

Resume: `PYTHONPATH=backend:. /Users/mark/miniforge3/envs/cc-m1/bin/python tests_perf/native_measure.py --workspace /private/tmp/clinical-compass-jury-20261027 --resume-run 20261027T151022Z`

No performance or jury PASS is inferred before summary review.

Measurement gate reviewed: COMPLETE (335 ordinary HTTP samples, zero unexpected HTTP failures, nine successful browser tasks and one actual app Qwen sample). Initial harness errors and logs retained; n=1 is not an LLM distribution. See PERFORMANCE_REPORT.md, LOAD_REPORT.md and PHASE1_SUMMARY.md. Proceeding to Phase 2 preservation/rehearsal. No clinical/Docker readiness inferred.
