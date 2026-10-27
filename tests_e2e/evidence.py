"""Append-only, crash-resilient evidence for synthetic jury checks."""
import datetime as dt
import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
RUN_ID = os.environ.get('CC_QA_RUN_ID', dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
PHASE = int(os.environ.get('CC_QA_PHASE', '0'))
if PHASE not in (0, 1, 2, 3): raise ValueError('Invalid evidence phase')
OUT = ROOT / f'reports/phase{PHASE}/raw'
_completed = 0
def snapshot():
    from collections import Counter
    rows=[]
    for line in (OUT/'scenarios.jsonl').read_text().splitlines():
        try: rows.append(json.loads(line))
        except ValueError: pass
    counts=Counter((r['method'],r['status']) for r in rows)
    marker=f'live-evidence-phase{PHASE}'
    text='\n\n<!-- '+marker+':start -->\nLatest completed: `'+rows[-1]['scenario']+'` ('+rows[-1]['status']+').\n\n'
    text+='Append-only observations (includes baseline failures and reruns; not unique acceptance counts):\n\n'
    for (method,status),n in sorted(counts.items()): text+=f'- {method}: {status} {n}\n'
    text+=f'\nRaw: `reports/phase{PHASE}/raw/scenarios.jsonl`. This automated observation summary does not set the phase gate.\n<!-- '+marker+':end -->\n'
    for relative in (f'reports/phase{PHASE}/PROGRESS.md','.agent/CHECKPOINT.md','.agent/EXECPLAN_ACTIVE.md'):
        target=ROOT/relative
        old=target.read_text()
        old=re.sub(r'\n*<!-- '+marker+r':start -->.*?<!-- '+marker+r':end -->\n*','\n',old,flags=re.S).rstrip()
        temp=target.with_suffix('.tmp.'+str(os.getpid()))
        temp.write_text(old+text);temp.replace(target)
def record(scenario, status, elapsed, *, role='operator', method='', detail='', n=1):
    global _completed
    OUT.mkdir(parents=True, exist_ok=True)
    row = dict(run_id=RUN_ID, timestamp=dt.datetime.now(dt.timezone.utc).isoformat(), scenario=scenario,
               role=role, status=status, elapsed=elapsed, unit='seconds', n=n, method=method, detail=detail)
    with (OUT / 'scenarios.jsonl').open('a') as stream:
        stream.write(json.dumps(row, ensure_ascii=False)+'\n'); stream.flush(); os.fsync(stream.fileno())
    print(f'{status}: {scenario} ({elapsed:.3f}s)', flush=True)
    _completed+=1
    if _completed % 5 == 0: snapshot()
@contextmanager
def scenario(name, **kwargs):
    start=time.monotonic()
    try: yield
    except Exception as exc:
        record(name,'FAIL',time.monotonic()-start,detail=type(exc).__name__+': '+str(exc)[:600],**kwargs)
        raise
    else: record(name,'PASS',time.monotonic()-start,**kwargs)
