"""Bounded synthetic localhost measurements; append+fsync every observation.
No parallel model load, external targets, mutation load, secrets or payload logging.
"""
import argparse,csv,datetime as dt,http.cookiejar,json,os,platform,statistics,subprocess,sys,threading,time,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import build_opener,HTTPCookieProcessor,ProxyHandler,Request
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/phase1/raw'
FIELDS=['run_id','timestamp','case_key','scenario','role','endpoint','status','elapsed','unit','n','method','users']

class Run:
    def __init__(self,run_id,workspace,base):
        self.id=run_id;self.workspace=workspace;self.base=base;self.count=0;self.lock=threading.Lock();self.active=0;self.max_active=0
        OUT.mkdir(parents=True,exist_ok=True);self.done=set()
        for name in ('http_latency.csv','task_timing.csv'):
            path=OUT/name
            if path.exists():
                self.done.update(r['case_key'] for r in csv.DictReader(path.open()) if r['run_id']==self.id and r['status']=='PASS')
    def append(self,name,key,scenario,role,endpoint,status,elapsed,method,users=1):
        row=dict(run_id=self.id,timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),case_key=key,scenario=scenario,role=role,endpoint=endpoint,status=status,elapsed=elapsed,unit='seconds',n=1,method=method,users=users)
        with self.lock:
            path=OUT/name;new=not path.exists()
            with path.open('a',newline='') as f:
                w=csv.DictWriter(f,fieldnames=FIELDS)
                if new:w.writeheader()
                w.writerow(row);f.flush();os.fsync(f.fileno())
            self.count+=1
            if status=='PASS':self.done.add(key)
            if self.count%5==0:self.checkpoint(key)
        if status!='PASS':
            self.error(row);self.checkpoint(key+' FAIL')
    def error(self,row):
        p=OUT/'errors.csv';new=not p.exists()
        with p.open('a',newline='') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS)
            if new:w.writeheader()
            w.writerow(row);f.flush();os.fsync(f.fileno())
    def checkpoint(self,last):
        command=f'PYTHONPATH=backend:. {sys.executable} tests_perf/native_measure.py --workspace {self.workspace} --resume-run {self.id}'
        text=f'# Phase 1 — INCOMPLETE\n\nRun `{self.id}`; completed successful observations in run: {len(self.done)}. Last: `{last}`. Raw rows flush after every observation; this count includes HTTP/setup and browser tasks, not unique product acceptance.\n\nRaw files: raw/http_latency.csv, task_timing.csv, errors.csv, resources.jsonl, environment.json and llm_metrics.json as available.\n\nResume: `{command}`\n\nNo performance or jury PASS is inferred before summary review.\n'
        p=ROOT/'reports/phase1/PROGRESS.md';tmp=p.with_suffix('.tmp');tmp.write_text(text);tmp.replace(p)
        for name in ('CHECKPOINT.md','EXECPLAN_ACTIVE.md'):
            p=ROOT/'.agent'/name;old=p.read_text().split('<!-- phase1-measurement -->')[0].rstrip()
            tmp=p.with_suffix('.tmp.phase1');tmp.write_text(old+f'\n\n<!-- phase1-measurement -->\nPhase 1 run `{self.id}`, last `{last}`, successful observations {len(self.done)}. Phase 0 source commit eb64d3f. Subagents 0/4. Resume `{command}`. Partial metrics: reports/phase1/raw/.\n');tmp.replace(p)
        print(f'Persisted {len(self.done)} observations; last {last}',flush=True)
    def resource(self):
        # Only the localhost app process, no process arguments or unrelated user data.
        try:
            result=subprocess.run(['lsof','-t','-iTCP:'+str(urlsplit(self.base).port),'-sTCP:LISTEN'],capture_output=True,text=True,timeout=3)
            pid=int(result.stdout.strip().splitlines()[0]);raw=subprocess.check_output(['ps','-p',str(pid),'-o','rss=,%cpu='],text=True,timeout=3).split()
            rss_kib=int(raw[0]);cpu=float(raw[1]);row={'timestamp':dt.datetime.now(dt.timezone.utc).isoformat(),'run_id':self.id,'source':'ps localhost Flask PID; excludes Ollama','rss_kib':rss_kib,'cpu_percent':cpu,'status':'PASS'}
            if rss_kib>6*1024*1024 or cpu>500:raise RuntimeError('bounded resource halt condition')
        except RuntimeError:raise
        except Exception:row={'timestamp':dt.datetime.now(dt.timezone.utc).isoformat(),'run_id':self.id,'status':'BLOCKED','source':'ps resource query unavailable'}
        with (OUT/'resources.jsonl').open('a') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())

class Client:
    def __init__(self,run,role,credentials=None):
        self.run=run;self.role=role;self.opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(http.cookiejar.CookieJar()));self.token=''
        if credentials:
            boot=self.request('/api/v1/onboarding/bootstrap',measure=False)
            self.token=boot['csrf_token'];data=self.request('/api/v1/onboarding/login',method='POST',data={k:credentials[k] for k in ('email','password')},measure=False)
            self.token=data['csrf_token']
    def request(self,path,method='GET',data=None,*,key='',scenario='baseline',users=1,expected=200,measure=True):
        start=time.monotonic();status=0;value={};allowed=(expected,) if isinstance(expected,int) else expected
        headers={'Accept':'application/json'}
        if self.token:headers['X-CSRF-Token']=self.token
        if data is not None:headers['Content-Type']='application/json'
        request=Request(self.run.base+path,method=method,headers=headers,data=None if data is None else json.dumps(data).encode())
        try:
            with self.run.lock:self.run.active+=1;self.run.max_active=max(self.run.max_active,self.run.active)
            try:
                with self.opener.open(request,timeout=100 if scenario=='llm' else 10) as response:status=response.status;body=response.read(2000000)
            except HTTPError as response:status=response.code;body=response.read(10000)
            value=json.loads(body) if body else {}
        finally:
            with self.run.lock:self.run.active-=1
            elapsed=time.monotonic()-start
            if measure:self.run.append('http_latency.csv',key,scenario,self.role,path,'PASS' if status in allowed else 'FAIL',elapsed,method,users)
        if status not in allowed:
            if not measure:self.run.append('errors.csv','setup-'+str(time.time_ns()),'harness setup',self.role,re.sub(r'[a-f0-9]{16,64}','OBJECT',path),'FAIL',elapsed,method)
            raise RuntimeError(f'HTTP {status}, expected {expected}; endpoint {path.split("?")[0]}')
        return value

def atomic(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2));temp.replace(path)

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--base',default='http://127.0.0.1:8766');p.add_argument('--resume-run');a=p.parse_args()
    if urlsplit(a.base).hostname not in ('127.0.0.1','localhost','::1'):p.error('Loopback targets only')
    workspace=Path(a.workspace).resolve();run=Run(a.resume_run or dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'),workspace,a.base)
    actors=json.loads((workspace/'jury-actors.json').read_text());actors['patient']=json.loads((workspace/'jury-linked-patient.json').read_text())
    atomic(OUT/'environment.json',dict(run_id=run.id,timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),platform=platform.platform(),machine=platform.machine(),python=sys.version,base=a.base,workspace_type='private synthetic evaluation',model='qwen3:4b-instruct',load_cap_rps=2,load_users=[1,3,5],load_seconds_per_scenario=30,ai_parallelism=1,method='stdlib HTTP + real Chromium; no human usability study',revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()))
    run.checkpoint('start / resume')
    clients={role:Client(run,role,actor) for role,actor in actors.items()}
    targets=[('guest','/api/v1/health'),('guest','/api/v1/clinical-catalog/search?type=medicine'),('guest','/api/v1/clinical-catalog/medicine/sertraline'),('patient','/api/v1/patient-experience/dashboard'),('doctor','/api/v1/doctors/me/linked-patients'),('researcher','/api/v1/research/demo-datasets/synthetic_research_v3/summary'),('clinic_admin','/api/v1/p1/clinic/staff')]
    clients['guest']=Client(run,'guest')
    for index,(role,path) in enumerate(targets):
        for n in range(20):
            key=f'baseline-{index}-{n}'
            if key in run.done:continue
            start=time.monotonic();clients[role].request(path,key=key)
            if n%5==0:run.resource()
            time.sleep(max(0,.5-(time.monotonic()-start)))
    # Scripted task timing includes UI interaction and real server-confirmed save.
    from playwright.sync_api import sync_playwright,expect
    from tests_e2e.test_jury_live import fill_guest,login,register,show
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        for kind in ('guest_login','guest_register','role_navigation'):
            for n in range(3):
                key=f'task-{kind}-{n}'
                if key in run.done:continue
                context=browser.new_context(viewport={'width':1280,'height':900});page=context.new_page();start=time.monotonic();status='FAIL'
                try:
                    if kind=='guest_login':
                        fill_guest(page,'phq_9',1);login(page,actors['patient']['email'],actors['patient']['password'])
                        expect(page).to_have_url(re.compile(r'/patient/questionnaires/dq_[^/]+/result$'))
                    elif kind=='guest_register':
                        import secrets
                        fill_guest(page,'gad_7',1);register(page,'performance-'+secrets.token_hex(5)+'@evaluation.test',secrets.token_urlsafe(24))
                        expect(page).to_have_url(re.compile(r'/patient/questionnaires/dq_[^/]+/result$'))
                    else:
                        login(page,actors['researcher']['email'],actors['researcher']['password']);expect(page).to_have_url(a.base+'/#/research');show(page,'/research/demo-v3');expect(page.locator('#main')).to_contain_text('Методика и ограничения')
                    status='PASS'
                finally:
                    run.append('task_timing.csv',key,kind,'researcher' if kind=='role_navigation' else 'patient','scripted task',status,time.monotonic()-start,'Chromium; automation time, not human time');context.close()
        browser.close()
    # One actual sequential app Qwen chat. Existing guarded source + durable job.
    llm=OUT/'llm_metrics.json';existing=json.loads(llm.read_text()) if llm.exists() else {}
    if existing.get('run_id')!=run.id or existing.get('status')!='PASS':
        run.checkpoint('starting one sequential real app Qwen chat')
        patient=clients['patient'];doctor=clients['doctor'];started=time.monotonic()
        state_path=workspace/('performance-llm-'+run.id+'.json')
        if state_path.exists():state=json.loads(state_path.read_text())
        else:
            case=patient.request('/api/v1/previsit-cases',method='POST',data={'doctor_id':actors['doctor']['id'],'text':'Вымышленный пациент: плохо сплю. Тревожусь из-за работы.','case_consent':True},expected=201,measure=False)
            state={'cid':case['id'],'thread_key':str(uuid.uuid5(uuid.NAMESPACE_URL,'jury-perf-thread-'+run.id)),'message_key':str(uuid.uuid5(uuid.NAMESPACE_URL,'jury-perf-message-'+run.id))}
            fd=os.open(state_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as f:json.dump(state,f);f.flush();os.fsync(f.fileno())
        pid=actors['patient']['patient_id'];cid=state['cid'];base='/api/v1/clinical-intelligence/patients/'+pid
        sources=doctor.request(base+'/threads?encounter_id='+cid,measure=False)
        thread=doctor.request(base+'/threads',method='POST',data={'encounter_id':cid,'source_version':sources['source_version'],'grant_version':sources['grant_version'],'idempotency_key':state['thread_key']},expected=(200,201),measure=False)
        thread_path='/api/v1/clinical-intelligence/threads/'+thread['id']
        current=doctor.request(thread_path,measure=False)
        if not current['jobs']:
            doctor.request(thread_path+'/messages',method='POST',data={'revision':thread['revision'],'source_version':thread['source_version'],'grant_version':thread['grant_version'],'content':'Какие справочные материалы о сне доступны?','idempotency_key':state['message_key']},expected=(200,202),measure=False)
        deadline=time.monotonic()+100
        while True:
            dto=doctor.request(thread_path,measure=False);job=dto['jobs'][-1]
            if job['status'] not in ('queued','running'):break
            if time.monotonic()>deadline:raise RuntimeError('Bounded model wait exceeded')
            time.sleep(1)
        assistant=next((x for x in reversed(dto['messages']) if x['role']=='assistant'),{})
        metrics=dict(run_id=run.id,timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),status='PASS' if job['status']=='completed' and assistant.get('mode')=='local_llm' else 'FAIL',n=1,wall_seconds=time.monotonic()-started,model=assistant.get('model'),mode=assistant.get('mode'),timings=job['timings'],prompt_eval_count=assistant.get('prompt_eval_count'),eval_count=assistant.get('eval_count'),prompt_eval_duration_ns=assistant.get('prompt_eval_duration_ns'),generation_duration_ns=assistant.get('generation_duration_ns'),ttft='NOT_AVAILABLE: backend non-streaming request; wall latency is not TTFT')
        if metrics['generation_duration_ns'] and metrics['eval_count']:metrics['tokens_per_second']=metrics['eval_count']/(metrics['generation_duration_ns']/1e9)
        with (OUT/'llm_calls.jsonl').open('a') as f:f.write(json.dumps(metrics)+'\n');f.flush();os.fsync(f.fileno())
        atomic(llm,metrics);run.checkpoint('real app Qwen chat '+metrics['status'])
        if metrics['status']!='PASS':raise RuntimeError('Actual Qwen performance sample failed')
    # Warm-up once then 1/3/5 independent virtual-user cookie jars, global 2 RPS.
    for users in (1,3,5):
        pool_clients=[Client(run,'guest') for _ in range(users)]
        with ThreadPoolExecutor(max_workers=users) as pool:
            futures=[]
            for n in range(60):
                key=f'load-{users}-{n}'
                if key in run.done:continue
                started=time.monotonic()
                future=pool.submit(pool_clients[n%users].request,'/api/v1/clinical-catalog/search?type=medicine',key=key,scenario='load',users=users)
                futures.append(future)
                if len(futures)>=users:
                    for f in futures:f.result()
                    futures=[]
                if n%5==0:run.resource()
                time.sleep(max(0,.5-(time.monotonic()-started)))
            for f in futures:f.result()
        for n in range(5):
            key=f'recovery-{users}-{n}'
            if key not in run.done:clients['guest'].request('/api/v1/health',key=key,scenario='recovery',users=users);time.sleep(.5)
    run.checkpoint('measurement complete; summarize actual rows')
    print('MEASUREMENTS COMPLETE',run.id,flush=True)

if __name__=='__main__':
    import re
    main()
