"""One-command isolated native jury setup/rehearsal, preserving existing workspaces.
Fresh refuses existing content. Restart never resets the database or keys.
"""
import argparse,datetime as dt,json,os,socket,subprocess,sys,time
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
ROOT=Path(__file__).resolve().parents[1]

def source_revision():
    try:
        return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError):
        try:return json.loads((ROOT/'PACKAGE_MANIFEST.json').read_text())['source_commit']
        except (OSError,ValueError,KeyError):return 'UNVERSIONED_SOURCE'

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--port',type=int,default=8767);p.add_argument('--mode',choices=['fresh','restart'],required=True);p.add_argument('--phase',choices=['2'],default='2');a=p.parse_args()
    workspace=Path(a.workspace).expanduser().resolve()
    if workspace.is_relative_to(ROOT):p.error('Private workspace must be outside source')
    if a.mode=='fresh' and workspace.exists() and any(workspace.iterdir()):p.error('Fresh mode refuses nonempty workspace. Choose a new private path; no reset is performed.')
    if a.mode=='restart' and not (workspace/'organizer-evaluation.sqlite').is_file():p.error('Restart needs existing initialized workspace')
    if os.environ.get('CC_DATABASE_URL'):p.error('Unset external CC_DATABASE_URL; this harness owns only explicitly named private SQLite')
    with socket.socket() as probe:
        try:probe.bind(('127.0.0.1',a.port))
        except OSError:p.error('QA port is occupied; existing process was not touched')
    out=ROOT/'reports/phase2';raw=out/'raw';raw.mkdir(parents=True,exist_ok=True)
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ');run=a.mode+'-'+stamp
    env=dict(os.environ,PYTHONPATH=str(ROOT/'backend')+os.pathsep+str(ROOT),CC_QA_PHASE='2',CC_QA_WORKSPACE=str(workspace),CC_E2E_BASE_URL='http://127.0.0.1:'+str(a.port),CC_QA_RUN_ID=run)
    def cmd(argv,name,timeout=600):
        with (raw/(run+'-'+name+'.log')).open('w') as log:
            result=subprocess.run(argv,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
        if result.returncode:raise RuntimeError(name+' failed; see phase2 raw log')
    (out/'PROGRESS.md').write_text(f'# Phase 2 — INCOMPLETE\n\nCurrent rehearsal `{run}`. All raw results append after each scenario. Source functionality must be preserved; no gate is inferred from render-only inventory.\n\nResume current existing workspace with `PYTHONPATH=backend:. {sys.executable} scripts/jury_rehearsal.py --mode restart --workspace {workspace} --port {a.port}`; successful earlier scenarios remain in raw evidence.\n')
    if a.mode=='fresh':
        cmd([sys.executable,'tests_e2e/prepare_actors.py','--workspace',str(workspace)],'accounts')
        cmd([sys.executable,'-m','cc_api.evaluation_launcher','privacy-setup','--workspace',str(workspace)],'privacy-setup')
    # Keep full operational logs private, not in the distributable source/evidence.
    fd=os.open(workspace/'jury-server.log',os.O_CREAT|os.O_APPEND|os.O_WRONLY,0o600)
    with os.fdopen(fd,'a') as log:
        server=subprocess.Popen([sys.executable,'-m','cc_api.evaluation_launcher','serve','--workspace',str(workspace),'--port',str(a.port)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            opener=build_opener(ProxyHandler({}));deadline=time.monotonic()+30
            while True:
                if server.poll() is not None:raise RuntimeError('QA server failed to launch; private log retained')
                try:
                    with opener.open(env['CC_E2E_BASE_URL']+'/api/v1/health',timeout=1) as response:
                        if response.status==200:break
                except OSError:pass
                if time.monotonic()>deadline:raise RuntimeError('Bounded app readiness timeout')
                time.sleep(.2)
            if a.mode=='restart':cmd([sys.executable,'tests_e2e/restart_probe.py','verify'],'restart-verification')
            cmd([sys.executable,'-m','pytest','-q','-p','tests_e2e.pytest_evidence','tests_e2e/test_jury_live.py','tests_e2e/test_roles_live.py','--tb=short','--junitxml='+str(raw/(run+'.xml'))],'browser')
            cmd([sys.executable,'tests_e2e/seed_form_history.py'],'coherent-history')
            cmd([sys.executable,'tests_e2e/restart_probe.py','capture'],'restart-capture')
            outcome={'run_id':run,'mode':a.mode,'status':'PASS','timestamp':dt.datetime.now(dt.timezone.utc).isoformat(),'source_revision':source_revision(),'methods':'real Flask/SQLite/Chromium/Ollama; no mock API; normal auth and explicit synthetic consent','evidence':str(raw.relative_to(ROOT)/(run+'-browser.log'))}
            with (raw/'rehearsals.jsonl').open('a') as f:f.write(json.dumps(outcome)+'\n');f.flush();os.fsync(f.fileno())
            print(json.dumps(outcome),flush=True)
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()
if __name__=='__main__':main()
