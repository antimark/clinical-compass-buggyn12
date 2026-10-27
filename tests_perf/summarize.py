"""Compute reports only from already-flushed observations; retain failed attempts."""
import csv,datetime as dt,html,json,math,statistics
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/phase1';RAW=OUT/'raw'
def percentile(values,p):
    values=sorted(values);index=(len(values)-1)*p;low=math.floor(index);high=math.ceil(index)
    return values[low]+(values[high]-values[low])*(index-low)
def stats(rows):
    values=[float(r['elapsed'])*1000 for r in rows]
    if not values:return 'n=0'
    return f"n={len(values)}, p50={percentile(values,.5):.2f} ms, p95={percentile(values,.95):.2f} ms"+(f", p99={percentile(values,.99):.2f} ms" if len(values)>=100 else '; p99 omitted (n<100)')
def write(name,text):
    p=OUT/name;temp=p.with_suffix('.tmp');temp.write_text(text);temp.replace(p)
def main():
    environment=json.loads((RAW/'environment.json').read_text());run=environment['run_id']
    http=[r for r in csv.DictReader((RAW/'http_latency.csv').open()) if r['run_id']==run]
    tasks=[r for r in csv.DictReader((RAW/'task_timing.csv').open()) if r['run_id']==run]
    llm=json.loads((RAW/'llm_metrics.json').read_text()) if (RAW/'llm_metrics.json').exists() else {'status':'NOT_RUN'}
    errors=[r for r in http if r['status']!='PASS'];failed_tasks=[r for r in tasks if r['status']!='PASS']
    groups=defaultdict(list)
    for r in http:
        if r['scenario']=='baseline':groups[(r['role'],r['endpoint'])].append(r)
    table='| Role | Endpoint | Observed latency |\n|---|---|---|\n'
    for (role,path),rows in groups.items():table+=f'| {role} | `{path}` | {stats(rows)} |\n'
    task_table='| Scripted task | Successful samples / failed attempts | Median automation time |\n|---|---|---|\n'
    for name in sorted({r['scenario'] for r in tasks}):
        rows=[r for r in tasks if r['scenario']==name];values=[float(r['elapsed']) for r in rows if r['status']=='PASS']
        task_table+=f'| {name} | {len(values)} / {sum(r["status"]!="PASS" for r in rows)} | {statistics.median(values):.3f} s |\n' if values else f'| {name} | 0 / {len(rows)} | NOT_AVAILABLE |\n'
    resources=[json.loads(line) for line in (RAW/'resources.jsonl').read_text().splitlines()] if (RAW/'resources.jsonl').exists() else []
    good=[r for r in resources if r.get('status')=='PASS' and r['run_id']==run]
    resource_text=f"App-only RSS range {min(r['rss_kib'] for r in good)/1024:.1f}–{max(r['rss_kib'] for r in good)/1024:.1f} MiB; sampled process CPU max {max(r['cpu_percent'] for r in good):.1f}% (n={len(good)}). Ollama/browser/OS memory is excluded." if good else 'Resource sampling BLOCKED.'
    report=f'''# Phase 1 — measured native performance (run {run})

Status: {'MEASURED' if len(http)>=335 and llm['status']=='PASS' else 'INCOMPLETE'}. Native macOS 26.5 arm64, 16 GiB, existing cc-m1; Python {environment['python']}. Source checkpoint `{environment['revision']}`. Flask development server on localhost with persistent synthetic SQLite, native host Ollama. This is no production SLO, clinical validation or human usability study.

{table}

Percentiles use linear interpolation over observed samples. Per-endpoint n=20 makes p95 exploratory; per-endpoint p99 is deliberately omitted. Baseline contains the first read/cache warm-up rather than claiming every request is equally warm. Non-AI requests are paced to 2 RPS, on the same machine and sandbox. No external endpoints were load tested.

{task_table}

Scripted times include automation, validation and actual server-confirmed results. They are not human Time on Task. One navigation attempt raced the login redirect because the harness did not await UI completion; its FAIL remains in raw/task_timing.csv and errors.csv. The wait was corrected. A model-setup request also received a correct 422 because the harness supplied a non-UUID idempotency key; no model generation occurred in that failed setup (measurement-resume1.log). UUID keys and a private resumable request state were added. Only incomplete measurements resumed; the 140 successful baseline samples were preserved.

Qwen: {json.dumps(llm,ensure_ascii=False)}

The model sample uses the real physician chat API and durable job, no mocked response. n=1 cannot support an LLM distribution or accuracy claim. TTFT is unavailable with the non-streaming backend. Token throughput is included only when the backend exposes count and generation duration. Source/evidence/clinician requirements remain unchanged.

HTTP unexpected failures: {len(errors)} / {len(http)} measured ordinary reads. Browser task failed attempts retained: {len(failed_tasks)}. {resource_text}

Bottlenecks/limits: local model generation dominates model-backed task latency; n=1 is insufficient for tail claims. Ordinary endpoints should be evaluated on larger independent samples before adopting targets. Source audit found duplicate render-triggered GETs; no security gate or working feature was removed to reduce measured time. Legacy study grants, genuine invited OIDC/MFA enrollment, complete action coverage and Docker remain separate gates.

Raw evidence: raw/http_latency.csv, raw/task_timing.csv, raw/errors.csv, raw/resources.jsonl, raw/llm_calls.jsonl and raw/environment.json. Resume command is preserved in PROGRESS.md and .agent/CHECKPOINT.md.
'''
    write('PERFORMANCE_REPORT.md',report)
    load='# Phase 1 — bounded localhost non-AI load\n\n'
    for users in (1,3,5):
        rows=[r for r in http if r['scenario']=='load' and int(r['users'])==users]
        recovery=[r for r in http if r['scenario']=='recovery' and int(r['users'])==users]
        if rows:
            start=dt.datetime.fromisoformat(rows[0]['timestamp']);end=dt.datetime.fromisoformat(rows[-1]['timestamp']);span=(end-start).total_seconds()+.5
            load+=f'- {users} independent virtual-user contexts, global cap 2 RPS; actual {len(rows)/span:.3f} responses/s over approximately {span:.2f}s; {stats(rows)}; failures {sum(r["status"]!="PASS" for r in rows)}. Recovery health: {stats(recovery)}.\n'
        else:load+=f'- {users} users: NOT_RUN.\n'
    load+='\nVirtual-user count is a configured population, not evidence of sustained concurrent in-flight work. Fast local responses and the global rate cap can leave only one request in flight. No claim of saturated capacity is made. No mutation or parallel LLM load. Every sample is flushed; any unexpected HTTP error halts the harness. Resource stop caps: app RSS >6 GiB or sampled app CPU >500%. No host thermal telemetry was collected.\n\n'+resource_text+'\n'
    write('LOAD_REPORT.md',load)
    write('PHASE1_SUMMARY.md',f'# Phase 1 summary\n\n{len(http)} HTTP observations, {len(tasks)} browser attempts (including {len(failed_tasks)} retained failure), real Qwen status {llm["status"]}. See PERFORMANCE_REPORT.md and LOAD_REPORT.md. Native role acceptance remains the specifically tested Phase 0 scope. No benchmark proves clinical correctness or complete feature parity. Proceed to Phase 2 only after this run finishes and review confirms no unexpected API/5xx errors. Docker NOT_RUN.\n')
    write('latency.html','<!doctype html><meta charset="utf-8"><title>Measured native endpoint latency</title><pre>'+html.escape(table)+'</pre><p>Observed run '+html.escape(run)+'; no SLO or clinical claim.</p>')
    print(json.dumps({'run_id':run,'http_samples':len(http),'http_failures':len(errors),'task_attempts':len(tasks),'task_failed_attempts':len(failed_tasks),'llm':llm['status']}))
if __name__=='__main__':main()
