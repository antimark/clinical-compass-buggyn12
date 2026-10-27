#!/usr/bin/env python3
"""One-command Clinical Compass synthetic QA orchestrator (run in Conda).

Usage: python scripts/validate_full.py [--browser] [--postgres] [--keycloak] [--acceptance]

Uses isolated temporary SQLite for browser and pytest fixtures. --postgres creates
and destroys a uniquely named disposable database (needs CC_TEST_PG_ADMIN_URL).
Never points tests at a real clinical DB or external AI provider.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import glob
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from xml.etree import ElementTree as ET
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
MANDATORY='C02 C03 C04 C05 C06 C07 C08 P07 P08 P10 P14 D04 D05 D06 D08 D09 D10 D13 D22 D23 K02 K03 K04 R02'.split()

def junit_summary(path):
    if not path.exists():return {}
    root=ET.parse(path).getroot()
    suite=root if root.tag=='testsuite' else root.find('testsuite')
    return {key:int(suite.get(key,'0')) for key in ('tests','failures','errors','skipped')}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser',action='store_true',help='Start live Flask and run Playwright Chromium')
    parser.add_argument('--postgres',action='store_true',help='Test actual disposable PostgreSQL DB; needs CC_TEST_PG_ADMIN_URL')
    parser.add_argument('--keycloak',action='store_true',help='Verify actual synthetic realm OIDC discovery/JWKS; does not prove PKCE/MFA')
    parser.add_argument('--acceptance',action='store_true',help='Fail unless all mandatory P0 routes have test-backed accepted status')
    parser.add_argument('--offline-only',action='store_true',help='Run static Python/JS checks even without Flask; does not validate P0 backend')
    parser.add_argument('--suite-timeout',type=int,default=900,help='Per integration suite timeout; baseline on M1 takes over six minutes')
    parser.add_argument('--report-dir',default='',help='Folder to write JSON, JUnit and complete logs')
    args=parser.parse_args()
    if args.offline_only and any((args.browser,args.postgres,args.keycloak,args.acceptance)):
        parser.error('--offline-only cannot be combined with integration/acceptance switches')
    if args.offline_only:
        print('OFFLINE-ONLY: this mode does NOT test Flask, PostgreSQL, OIDC, browser or P0 acceptance.',flush=True)
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=Path(args.report_dir).resolve() if args.report_dir else ROOT/'test_reports'/stamp
    out.mkdir(parents=True,exist_ok=True)
    stages=[]
    env=os.environ.copy()
    env.update({'CC_DEMO_MODE':'1','CC_AI_MODE':'disabled','PYTHONPATH':str(ROOT/'backend')+os.pathsep+env.get('PYTHONPATH',''),
                'CC_SECRET_KEY':'QA_SYNTHETIC_ONLY_'+stamp})
    env.pop('CC_DATABASE_URL',None)
    def record(name,state,detail='',extra=None):
        stages.append({'name':name,'state':state,'detail':detail,'result':extra or {}})
        print(f'[{state}] {name}: {detail}',flush=True)
    def cmd(name,argv,env_override=None,timeout=240):
        logfile=out/(name+'.log')
        runenv=dict(env)
        if env_override:runenv.update(env_override)
        try:
            with logfile.open('w',encoding='utf-8') as log:
                proc=subprocess.run(argv,cwd=ROOT,env=runenv,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
            status='PASS' if proc.returncode==0 else 'FAIL'
            record(name,status,f'exit={proc.returncode}, log={logfile.name}',{'exit_code':proc.returncode})
            return status=='PASS'
        except (OSError,subprocess.TimeoutExpired) as exc:
            record(name,'FAIL',str(exc))
            logfile.write_text(str(exc),encoding='utf-8')
            return False
    deps={module:importlib.util.find_spec(module) is not None for module in
          ['pytest','yaml','sqlalchemy','alembic','flask','jwt','psycopg']}
    (out/'dependencies.json').write_text(json.dumps(deps,indent=2),encoding='utf-8')
    requirements=['pytest','yaml','sqlalchemy','alembic'] if args.offline_only else list(deps)
    if all(deps[x] for x in requirements):record('python_dependencies','PASS','Required modules importable')
    else:record('python_dependencies','FAIL','Missing: '+', '.join(x for x in requirements if not deps[x]))
    cmd('python_syntax',[sys.executable,'-m','compileall','-q','backend','tests','scripts'])
    if deps['pytest']:
        testfiles=['tests/test_static_contract.py','tests/test_conda_launchers.py',
                   'tests/test_p0_offline.py','tests/test_p0_engines.py']
        p=out/'offline.junit.xml'
        cmd('offline_python',[sys.executable,'-m','pytest','-q',*testfiles,'--junitxml='+str(p)])
        if p.exists():record('offline_junit','INFO','',junit_summary(p))
    if shutil.which('node'):
        jsfiles=sorted(glob.glob(str(ROOT/'frontend/dist/tests/*.cjs')))
        jsfiles.append(str(ROOT/'frontend/dist/tests/p1_route_smoke.cjs')) if (ROOT/'frontend/dist/tests/p1_route_smoke.cjs').exists() else None
        cmd('node_syntax',['node','--check','frontend/dist/assets/js/p1_screens.js'])
        cmd('node_tests',['node','--test',*sorted(set(jsfiles))])
    else:record('node_tests','FAIL','Node.js 22 absent from environment')
    if not args.offline_only:
        if deps['flask']:
            p=out/'full_flask.junit.xml'
            cmd('flask_full_suite',[sys.executable,'-m','pytest','-q','tests','backend/tests',
                    '--ignore=tests/test_browser_e2e.py','--ignore=tests/test_p0_browser_live.py','--ignore=tests/test_phase5_browser.py',
                    '--junitxml='+str(p)],timeout=args.suite_timeout)
            if p.exists():record('flask_junit','INFO','XPASS and XFAIL must be reviewed (not accepted capabilities)',junit_summary(p))
        else:record('flask_full_suite','BLOCKED','Install dependencies in clinical-compass Conda environment')
        if args.browser:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                record('browser_live','FAIL','Python Playwright package missing in Conda environment')
            else:
                # Verify the actual headless-shell binary before spawning Flask.
                # Importing playwright is insufficient: its browser download is separate.
                browser_error=None
                try:
                    with sync_playwright() as pw:
                        probe=pw.chromium.launch(headless=True)
                        probe.close()
                except Exception as exc:
                    browser_error=str(exc).splitlines()[0]
                if browser_error:
                    record('browser_live','FAIL',
                           'Chromium preflight failed: '+browser_error+
                           '; run: conda run -n clinical-compass python -m playwright install chromium')
                else:
                    with tempfile.TemporaryDirectory(prefix='cc_qa_') as folder:
                        from cryptography.fernet import Fernet
                        browser_env=dict(env,CC_PII_ENCRYPTION_KEY=Fernet.generate_key().decode(),CC_DB_PATH=str(Path(folder)/'browser.sqlite'),CC_AI_MODE='deterministic_mock',CC_APP_ENV='synthetic_dev',CC_SEED_PATIENT_PERSONAS='1')
                        with socket.socket() as s:
                            s.bind(('127.0.0.1',0));port=s.getsockname()[1]
                        browser_env['CC_PORT']=str(port)
                        browser_env['CC_PUBLIC_BASE_URL']=f'http://127.0.0.1:{port}'
                        logfile=out/'flask_live_server.log'
                        with logfile.open('w',encoding='utf-8') as log:
                            process=subprocess.Popen([sys.executable,'backend/run.py'],cwd=ROOT,
                                                      env=browser_env,stdout=log,stderr=subprocess.STDOUT)
                            try:
                                url=f'http://127.0.0.1:{port}'
                                ready=False
                                for _ in range(50):
                                    if process.poll() is not None:break
                                    try:
                                        with urlopen(url+'/api/v1/health',timeout=1) as r:
                                            ready=r.status==200
                                            if ready:break
                                    except Exception:time.sleep(.2)
                                if not ready:record('browser_live','FAIL','Local Flask did not start; see flask_live_server.log')
                                else:
                                    cmd('browser_live',[sys.executable,'-m','pytest','-q','tests/test_browser_e2e.py',
                                        'tests/test_p0_browser_live.py','tests/test_phase5_browser.py',
                                        '--junitxml='+str(out/'browser.junit.xml')],env_override={
                                            'CC_E2E_BASE_URL':url,'CC_BROWSER_ENABLED':'1',
                                            'CC_SCREENSHOT_DIR':str(out/'screenshots')},timeout=args.suite_timeout)
                            finally:
                                process.terminate()
                                try:process.wait(timeout=5)
                                except subprocess.TimeoutExpired:process.kill();process.wait()
        else:record('browser_live','NOT_RUN','Run --browser after installing Chromium')
        if args.postgres:
            if not os.environ.get('CC_TEST_PG_ADMIN_URL'):
                record('postgres_disposable','FAIL','Set CC_TEST_PG_ADMIN_URL to a synthetic PostgreSQL admin DSN')
            else:cmd('postgres_disposable',[sys.executable,'scripts/check_postgres_profile.py'],timeout=180)
        else:record('postgres_disposable','NOT_RUN','Run --postgres with CC_TEST_PG_ADMIN_URL')
        if args.keycloak:
            base=os.environ.get('CC_TEST_KEYCLOAK_BASE_URL','http://127.0.0.1:8080').rstrip('/')
            url=base+'/realms/clinical-compass-synthetic/.well-known/openid-configuration'
            try:
                with urlopen(url,timeout=6) as response:discovery=json.load(response)
                assert discovery['issuer'].rstrip('/').endswith('/realms/clinical-compass-synthetic')
                assert 'authorization_endpoint' in discovery and 'token_endpoint' in discovery
                with urlopen(discovery['jwks_uri'],timeout=6) as response:keys=json.load(response)
                assert keys.get('keys')
                record('keycloak_discovery','PASS','Realm and JWKS reachable; PKCE/MFA NOT verified')
            except Exception as exc:record('keycloak_discovery','FAIL',str(exc))
        else:record('keycloak_discovery','NOT_RUN','Run --keycloak; realm availability != PKCE/MFA acceptance')
    with (ROOT/'docs/SCREEN_IMPLEMENTATION_MATRIX.csv').open(newline='',encoding='utf-8') as handle:
        inventory=list(csv.DictReader(handle))
    rows={r['id']:r for r in inventory}
    assert len(inventory)==86 and len(MANDATORY)==24
    blocked=[{'id':x,'route':rows[x]['route'],'status':rows[x]['implementation_status'],
              'unmet_requirement':rows[x]['unmet_requirement']} for x in MANDATORY
              if rows[x]['implementation_status'] not in ('accepted','verified')]
    record('p0_acceptance_gate','FAIL' if args.acceptance and blocked else 'INFO',
           f'{len(blocked)}/24 mandatory P0 routes not accepted',{'unaccepted':blocked})
    summary={'timestamp_utc':stamp,'synthetic_only':True,'environment':{'python':sys.version.split()[0],
             'node':shutil.which('node') is not None},'stages':stages,
             'p0_acceptance':{'total':24,'not_accepted':len(blocked),'details':blocked},
             'caveat':'Infrastructure reachability never certifies actual PKCE/MFA or clinical validity'}
    report=out/'summary.json';report.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'\nReport: {report}',flush=True)
    return 1 if any(s['state']=='FAIL' for s in stages) else 0

if __name__=='__main__':sys.exit(main())
