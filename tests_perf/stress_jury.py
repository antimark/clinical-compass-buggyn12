"""Isolated localhost stress: closed-loop reads, SQLite writes, real Qwen contention.
No RPS pacing. Only a separate ccstress* Docker project, never the jury workspace.
"""
import http.client
import argparse,copy,csv,datetime as dt,hashlib,http.cookiejar,json,os,platform,resource,secrets,statistics,subprocess,threading,time,uuid
from collections import deque,Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import build_opener,ProxyHandler,HTTPCookieProcessor,HTTPRedirectHandler,Request
from urllib.error import HTTPError
from urllib.parse import urlsplit,quote
ROOT=Path(__file__).resolve().parents[1]
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None
class Client:
 def __init__(self,base,actor=None,parent=None):
  self.base=base;jar=http.cookiejar.CookieJar();self.token=''
  if parent:
   for c in parent.jar:jar.set_cookie(copy.copy(c))
   self.token=parent.token
  self.jar=jar;self.persistent=None;self.opener=build_opener(ProxyHandler({}),NoRedirect(),HTTPCookieProcessor(jar))
  if actor:
   code,b,_,_=self.req('/api/v1/onboarding/bootstrap',timeout=30);assert code==200;self.token=b['csrf_token'];code,b,_,_=self.req('/api/v1/onboarding/login','POST',{k:actor[k] for k in ('email','password')},timeout=30);assert code==200;self.token=b['csrf_token'];assert self.req('/api/v1/auth/me',timeout=30)[0]==200
 def req(self,path,method='GET',payload=None,timeout=5):
  headers={'Accept':'application/json'}
  if self.token:headers['X-CSRF-Token']=self.token
  if payload is not None:headers['Content-Type']='application/json'
  if self.persistent is not None:
   headers['Cookie']='; '.join(c.name+'='+c.value for c in self.jar);headers['Connection']='keep-alive';body=json.dumps(payload).encode() if payload is not None else None
   self.persistent.timeout=timeout;self.persistent.request(method,path,body=body,headers=headers);r=self.persistent.getresponse();raw=r.read(2_000_000)
   try:value=json.loads(raw)
   except ValueError:value={}
   return r.status,value,len(raw),''
  req=Request(self.base+path,method=method,headers=headers,data=json.dumps(payload).encode() if payload is not None else None)
  try:
   with self.opener.open(req,timeout=timeout) as r:raw=r.read(2_000_000);code=r.status
  except HTTPError as r:raw=r.read(20_000);code=r.code
  try:value=json.loads(raw)
  except ValueError:value={}
  return code,value,len(raw),''
def pct(values,p):
 if not values:return None
 a=sorted(values);x=(len(a)-1)*p;lo=int(x);return a[lo]+(a[min(lo+1,len(a)-1)]-a[lo])*(x-lo)
def private(path,value):
 fd=os.open(path,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f:json.dump(value,f)
def append(path,row):
 with path.open('a') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())
class Runner:
 def __init__(self,a):
  self.a=a;self.ws=Path(a.workspace);self.out=ROOT/'reports/stress'/a.run;self.raw=self.out/'raw';self.raw.mkdir(parents=True,exist_ok=True);self.run=a.resume_run or a.run+'-'+dt.datetime.now(dt.timezone.utc).strftime('%H%M%SZ');self.stop=threading.Event();self.done=threading.Event();self.lock=threading.Lock();self.active=0;self.peak=0;self.last=[];self.acked=[];self.total=0;self.stage_name='setup';self.marker='Synthetic stress '+self.run;self.history=[]
  self.request_path=self.raw/('requests-'+self.run+'.csv');new_file=not self.request_path.exists();self.file=self.request_path.open('a',newline='');self.writer=csv.writer(self.file)
  if new_file:self.writer.writerow(['run_id','timestamp','stage','concurrency','worker','sequence','operation','http_status','elapsed_ms','bytes','valid','error_class'])
  self.fsync_at=0
  if a.resume_run:
   self.acked=json.load(open(self.ws/'acknowledged-writes.json'))
   stage_file=self.raw/('stages-'+self.run+'.jsonl');self.history=[json.loads(x) for x in stage_file.read_text().splitlines()] if stage_file.exists() else []
  self.actors=json.load(open(self.ws/'jury-actors.json'));self.clients={r:Client(a.base,v) for r,v in self.actors.items()}
 def persist(self,name,row):append(self.raw/(name+'-'+self.run+'.jsonl'),row)
 def checkpoint(self,last):
  text=f'\n\n<!-- stress-20261028 -->\nStress {self.run}: {last}. Target {self.a.base}, separate container {self.a.container}, independent volume; no demo DB. Raw reports/stress/{self.a.run}/raw/. Stages durably appended, request samples flush each row/fsync<=0.25s. Source baseline d7dec4b; subagents1/4. Resume by reading stages-{self.run}.jsonl; do not rerun successful stages. Current report PARTIAL until summary/recovery.\n'
  for name in ['.agent/CHECKPOINT.md','.agent/EXECPLAN_ACTIVE.md']:
   p=ROOT/name;old=p.read_text().split('\n\n<!-- stress-20261028 -->')[0];tmp=p.with_suffix('.stress.tmp');tmp.write_text(old+text);tmp.replace(p)
  (self.out/'PROGRESS.md').write_text('# Stress test — PARTIAL\n\n'+text+'\nCompleted stages: '+str(len(self.history))+'\n')
  print(last,flush=True)
 def prepare(self):
  saved=self.ws/'stress-patients.json'
  if saved.exists():data=json.load(open(saved));self.patients=data
  else:
   self.patients=[];d=self.clients['doctor']
   for i in range(6):
    p=Client(self.a.base);code,b,_,_=p.req('/api/v1/onboarding/bootstrap');assert code==200;p.token=b['csrf_token'];email='stress-'+secrets.token_hex(5)+'@evaluation.test';password=secrets.token_urlsafe(24)
    code,b,_,_=p.req('/api/v1/onboarding/register','POST',{'display_name':'Синтетический участник нагрузки','email':email,'password':password,'terms_consent':True});assert code==201;user=b['user'];p=Client(self.a.base,{'email':email,'password':password})
    code,inv,_,_=d.req('/api/v1/onboarding/invitations','POST',{'recipient_email':email,'categories':['symptoms','diagnosis','medications','severity']});assert code==201
    code,preview,_,_=p.req('/api/v1/onboarding/invitations/preview','POST',{'token':inv['token']});assert code==200
    code,b,_,_=p.req('/api/v1/onboarding/invitations/accept','POST',{'token':inv['token'],'consent':True,'consent_version':preview['consent_version']});assert code==200
    code,case,_,_=p.req('/api/v1/previsit-cases','POST',{'doctor_id':self.actors['doctor']['id'],'text':'Вымышленный пациент: плохо сплю. Тревожусь из-за работы.','symptoms':[],'conditions':[],'case_consent':True});assert code==201
    self.patients.append({'email':email,'password':password,'patient_id':user['patient_id'],'case_id':case['id']})
    private(saved,self.patients)
  self.clients['patient']=Client(self.a.base,self.patients[0])
  for _ in range(10):assert self.clients['patient'].req('/api/v1/patients/me/check-ins','POST',{'mood_score':3,'comparison':'same','note':'Синтетическое исходное наблюдение.'})[0]==201
  snapshot=self.snapshot();self.persist('dataset',{'patients':len(self.patients),'cases':len(self.patients),'initial_checkins':snapshot['total_checkins'],'initial_integrity':snapshot['integrity'],'catalog_records':242,'medicine_records':77,'note':'separate stress database; reused existing synthetic rows from earlier transport-profile run if present'})
  self.monitor=threading.Thread(target=self.resources,daemon=True);self.monitor.start();self.checkpoint('Setup PASS:6 synthetic patients; ordinary invitations/explicit consent/cases;10 baseline checkins')
 def resources(self):
  while not self.done.is_set():
   try:
    b=json.loads(subprocess.check_output(['docker','stats','--no-stream','--format','{{json .}}',self.a.container],text=True,timeout=8));cpu=float(b['CPUPerc'].rstrip('%'));used=b['MemUsage'].split('/')[0].strip();number=float(''.join(c for c in used if c.isdigit() or c=='.'));mib=number*(1024 if 'GiB' in used else 1 if 'MiB' in used else 1/1024)
    client=subprocess.check_output(['ps','-p',str(os.getpid()),'-o','rss=,%cpu='],text=True,timeout=3).split();row={'timestamp':dt.datetime.now(dt.timezone.utc).isoformat(),'stage':self.stage_name,'app_cpu_percent':cpu,'app_memory_mib':mib,'client_rss_mib':int(client[0])/1024,'client_cpu_percent':float(client[1])};self.persist('resources',row)
    if mib>850 or row['client_rss_mib']>1024:self.stop.set();self.persist('halt',{'reason':'resource limit','sample':row})
   except Exception as e:self.persist('resources',{'status':'UNAVAILABLE','error_class':type(e).__name__})
   self.done.wait(1)
 def observe(self,stage,c,worker,seq,op,code,ms,size,valid,error):
  with self.lock:
   self.writer.writerow([self.run,dt.datetime.now(dt.timezone.utc).isoformat(),stage,c,worker,seq,op,code,round(ms,4),size,valid,error]);self.file.flush();now=time.monotonic()
   if now-self.fsync_at>=.25:os.fsync(self.file.fileno());self.fsync_at=now
   self.total+=1;self.last.append({'code':code,'ms':ms,'valid':valid,'op':op});self.window.append(valid)
   if len(self.window)==100 and sum(not x for x in self.window)>=5:self.stop.set()
   if len(self.last)>=100 and pct([x['ms'] for x in self.last[-100:]],.95)>5000:self.stop.set()
 def stage(self,kind,c,seconds):
  name=f'{kind}-c{c}';self.stage_name=name;self.last=[];self.window=deque(maxlen=100);self.stop.clear();self.peak=0;barrier=threading.Barrier(c+1);end=[0];start=time.monotonic()
  reads=[('guest','catalog_search','/api/v1/clinical-catalog/search?type=medicine')]*5+[('guest','medicine_detail','/api/v1/clinical-catalog/medicine/sertraline')]*2+[('patient','patient_dashboard','/api/v1/patient-experience/dashboard')]*2+[('doctor','doctor_patients','/api/v1/doctors/me/linked-patients'),('researcher','research_summary','/api/v1/research/demo-datasets/synthetic_research_v3/summary'),('clinic_admin','clinic_staff','/api/v1/p1/clinic/staff')]
  def worker(i):
   clients={r:Client(self.a.base,parent=v) for r,v in self.clients.items()};clients['guest']=Client(self.a.base)
   if self.a.keep_alive:
    host=urlsplit(self.a.base);connection=http.client.HTTPConnection(host.hostname,host.port,timeout=5)
    for client in clients.values():client.persistent=connection
   seq=0;barrier.wait()
   while time.monotonic()<end[0] and not self.stop.is_set():
    role,op,path=reads[(seq+i)%len(reads)];method='GET';payload=None;expected=200
    if kind=='mixed-write' and (seq+i)%5==0:role,op,path='patient','checkin_write','/api/v1/patients/me/check-ins';method='POST';payload={'mood_score':3,'comparison':'same','note':self.marker};expected=201
    t=time.monotonic();code=0;size=0;error='';valid=False;body={}
    with self.lock:self.active+=1;self.peak=max(self.peak,self.active)
    try:
     code,body,size,_=clients[role].req(path,method,payload);valid=code==expected and isinstance(body,dict) and bool(body)
     if valid and op=='catalog_search':valid=bool(body.get('items')) and body.get('total')==77
     if valid and op=='checkin_write':valid=body.get('mood_score')==3 and bool(body.get('id'))
    except Exception as e:error=type(e).__name__
    finally:
     ms=(time.monotonic()-t)*1000
     with self.lock:
      self.active-=1
      if valid and op=='checkin_write':self.acked.append(body['id'])
     self.observe(name,c,i,seq,op,code,ms,size,valid,error)
    seq+=1
   if self.a.keep_alive:connection.close()
  with ThreadPoolExecutor(max_workers=c) as pool:
   futures=[pool.submit(worker,i) for i in range(c)];start=time.monotonic();end[0]=start+seconds;barrier.wait()
   for f in futures:f.result()
  wall=time.monotonic()-start;values=[x['ms'] for x in self.last];fail=sum(not x['valid'] for x in self.last);measured_end=min(end[0],time.monotonic());row={'run_id':self.run,'stage':name,'kind':kind,'concurrency':c,'n':len(values),'failures':fail,'status_counts':dict(Counter(str(x['code']) for x in self.last)),'elapsed_seconds':wall,'throughput_rps':len(values)/wall,'goodput_rps':(len(values)-fail)/wall,'p50_ms':pct(values,.5),'p95_ms':pct(values,.95),'p99_ms':pct(values,.99) if len(values)>=100 else None,'peak_inflight':self.peak,'halted':self.stop.is_set(),'operations':dict(Counter(x['op'] for x in self.last)),'method':'closed-loop, no RPS pacing, independent cookie jars cloned from four ordinary role sessions; '+('one persistent HTTP/1.1 connection per worker; no transparent retries' if self.a.keep_alive else 'urllib fresh HTTP connections')}
  self.history.append(row);self.persist('stages',row);os.fsync(self.file.fileno());private(self.ws/'acknowledged-writes.json',self.acked);self.checkpoint(f'{name}:n{row["n"]},RPS{row["throughput_rps"]:.1f},p95{row["p95_ms"]:.1f}ms,errors{fail},peak{self.peak},halt{row["halted"]}');self.recovery(name)
  return row
 def recovery(self,after):
  values=[];codes=[]
  for _ in range(10):
   t=time.monotonic()
   try:code,_,_,_=Client(self.a.base).req('/api/v1/health',timeout=10)
   except Exception:code=0
   values.append((time.monotonic()-t)*1000);codes.append(code)
  row={'after':after,'n':10,'all_200':all(x==200 for x in codes),'p50_ms':pct(values,.5),'p95_ms':pct(values,.95)};self.persist('recovery',row);assert row['all_200'],row
 def llm(self):
  subprocess.run([os.sys.executable,str(ROOT/'docker/warm_native_model.py')],check=True,stdout=open(self.ws/'model-warmup.log','w'),stderr=subprocess.STDOUT)
  d=self.clients['doctor'];cases=[]
  for p in self.patients:
   path='/api/v1/clinical-intelligence/patients/'+p['patient_id']+'/snapshot?encounter_id='+p['case_id'];code,source,_,_=d.req(path);assert code==200
   cases.append((path,{'source_revision':source['source_revision'],'source_version':source['source_version']}))
  for concurrency,items in [(2,cases[:2]),(4,cases[2:6])]:
   self.stage_name='qwen-burst-'+str(concurrency);barrier=threading.Barrier(concurrency)
   def one(i):
    client=Client(self.a.base,parent=d);barrier.wait();t=time.monotonic()
    try:
     code,body,_,_=client.req(items[i][0],'POST',items[i][1],timeout=65);row={'burst':concurrency,'index':i,'http_status':code,'elapsed_seconds':time.monotonic()-t,'analysis_status':body.get('analysis_status'),'mode':body.get('mode'),'model':body.get('model_version'),'tag_count':len(body.get('tags',[])),'evidence_count':len(body.get('evidence',[])),'error_code':body.get('error',{}).get('code') or body.get('error_code')}
    except Exception as e:row={'burst':concurrency,'index':i,'http_status':0,'elapsed_seconds':time.monotonic()-t,'error_class':type(e).__name__}
    self.persist('llm',row);return row
   with ThreadPoolExecutor(max_workers=concurrency) as pool:results=list(pool.map(one,range(concurrency)))
   self.persist('llm-bursts',{'burst':concurrency,'real_model_ready':sum(r.get('mode')=='local_llm' and r.get('analysis_status')=='ready' for r in results),'busy_429':sum(r['http_status']==429 for r in results),'fallback_count':sum(r.get('mode') not in (None,'local_llm') for r in results),'new_inference_success':any(r.get('mode')=='local_llm' and r.get('analysis_status')=='ready' for r in results),'method':'simultaneous requests; rejected busy requests are not inference successes; fallback never counted as real model'})
   self.checkpoint('Qwen burst'+str(concurrency)+': '+str(Counter(r['http_status'] for r in results)));self.recovery(self.stage_name)
 def snapshot(self):
  code="import sqlite3,json,hashlib,pathlib; p=pathlib.Path('/workspace'); c=sqlite3.connect('file:/workspace/organizer-evaluation.sqlite?mode=ro',uri=True); print(json.dumps({'integrity':c.execute('pragma integrity_check').fetchone()[0],'fk_violations':len(c.execute('pragma foreign_key_check').fetchall()),'total_checkins':c.execute('select count(*) from checkins').fetchone()[0],'ids':[r[0] for r in c.execute('select id from checkins where note=?',("+repr(self.marker)+",))],'keys':{n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in ['session.secret','identity-fernet.key']}}))"
  return json.loads(subprocess.check_output(['docker','exec',self.a.container,'python','-c',code],text=True,timeout=15))
 def finish(self):
  before=self.snapshot();assert before['integrity']=='ok' and before['fk_violations']==0;assert set(self.acked)<=set(before['ids']);private(self.ws/'before-restart.json',before)
  subprocess.run(['docker','restart',self.a.container],check=True,stdout=subprocess.DEVNULL);deadline=time.monotonic()+60
  while True:
   try:
    if Client(self.a.base).req('/api/v1/health')[0]==200:break
   except Exception:pass
   assert time.monotonic()<deadline;time.sleep(1)
  after=self.snapshot();assert after==before;assert self.clients['patient'].req('/api/v1/auth/me')[0]==200
  row={'integrity':'ok','foreign_key_violations':0,'acknowledged_writes':len(self.acked),'persisted_matching_marker':len(after['ids']),'missing_acknowledged':len(set(self.acked)-set(after['ids'])),'additional_unacknowledged_writes':len(set(after['ids'])-set(self.acked)),'same_after_restart':True,'keys_unchanged':True,'session_survived':True};self.persist('persistence',row);self.recovery('app-restart');self.checkpoint('Persistence/restart PASS: '+str(len(self.acked))+' acknowledged writes retained')
 def run_all(self):
  self.persist('environment',{'run_id':self.run,'base':self.a.base,'container':self.a.container,'platform':platform.platform(),'python':platform.python_version(),'fd_limits':resource.getrlimit(resource.RLIMIT_NOFILE),'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'image':subprocess.check_output(['docker','inspect','--format','{{.Image}}',self.a.container],text=True).strip(),'limits':'app2CPU/1GiB; stop memory850MiB,client1GiB,5errors/last100,p95last100>5000ms;requesttimeout5s','rate_pacing':False,'keep_alive':self.a.keep_alive,'note':'same Mac; other demo services left idle; not isolated physical hardware'})
  try:
   if self.a.mode in ['finish','llm']:
    self.patients=json.load(open(self.ws/'stress-patients.json'));self.clients['patient']=Client(self.a.base,self.patients[0])
    if self.a.mode=='llm':self.llm()
    self.finish();self.persist('completion',{'status':'MEASURED','run_id':self.run,'mode':self.a.mode});return
   self.prepare();self.recovery('baseline')
   for c in (1,5,10,20,40,80,160):
    row=self.stage('read',c,self.a.read_seconds)
    if row['halted']:break
   for c in (1,5,10,20,40):
    row=self.stage('mixed-write',c,self.a.write_seconds)
    if row['halted']:break
   self.llm();self.finish();self.persist('completion',{'status':'COMPLETE','run_id':self.run,'requests':self.total,'stages':len(self.history)})
  finally:
   self.done.set()
   if hasattr(self,'monitor'):self.monitor.join(timeout=9)
   self.file.flush();os.fsync(self.file.fileno());self.file.close()
def main():
 p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8775');p.add_argument('--workspace',required=True);p.add_argument('--container',default='ccstress20261028-app-1');p.add_argument('--run',default='20261028');p.add_argument('--resume-run');p.add_argument('--keep-alive',action='store_true');p.add_argument('--mode',choices=['all','finish','llm'],default='all');p.add_argument('--read-seconds',type=int,default=20);p.add_argument('--write-seconds',type=int,default=15);a=p.parse_args();url=urlsplit(a.base);assert url.hostname in ['127.0.0.1','localhost'] and url.port not in [8766,8767,8768,8769];assert a.container.startswith('ccstress');assert 5<=a.read_seconds<=60 and 5<=a.write_seconds<=60
 ws=Path(a.workspace).resolve();assert ws.is_dir() and not ws.is_relative_to(ROOT) and ws.stat().st_mode&0o077==0
 Runner(a).run_all()
if __name__=='__main__':main()
