"""Small localhost-only non-AI read workload, explicit 1/3/5 client batches."""
import argparse,csv,datetime as dt,json,os,subprocess,threading,time,statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import build_opener,ProxyHandler,HTTPRedirectHandler
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

def main():
 p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8768');p.add_argument('--container',default='ccjuryqa20261027-app-1');a=p.parse_args()
 assert urlsplit(a.base).hostname in ('127.0.0.1','localhost','::1')
 out=ROOT/'reports/phase3/raw';out.mkdir(parents=True,exist_ok=True);run=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ');rows=[];lock=threading.Lock();active=0;peak=0
 fields=['run_id','timestamp','users','sample','status','http_status','elapsed_seconds','n','method']
 def request(client,users,index):
  nonlocal active,peak
  start=time.monotonic()
  with lock:active+=1;peak=max(peak,active)
  status='FAIL';code=None
  try:
   with client.open(a.base+'/api/v1/clinical-catalog/search?type=medicine',timeout=10) as response:
    code=response.status;data=json.loads(response.read(1_000_000));assert code==200 and data.get('items');status='PASS'
  finally:
   row=dict(run_id=run,timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),users=users,sample=index,status=status,http_status=code,elapsed_seconds=time.monotonic()-start,n=1,method='real Docker Flask HTTP; no model or mutations')
   with lock:
    active-=1;rows.append(row);path=out/'container-http-latency.csv';new=not path.exists()
    with path.open('a',newline='') as f:
     w=csv.DictWriter(f,fieldnames=fields)
     if new:w.writeheader()
     w.writerow(row);f.flush();os.fsync(f.fileno())
  return row
 summary=[]
 for users in (1,3,5):
  clients=[build_opener(ProxyHandler({}),NoRedirect()) for _ in range(users)];peak=0;started=time.monotonic()
  with ThreadPoolExecutor(max_workers=users) as pool:
   for begin in range(0,20,users):
    batch_start=time.monotonic();indexes=list(range(begin,min(begin+users,20)))
    results=[future.result() for future in [pool.submit(request,clients[i],users,n) for i,n in enumerate(indexes)]]
    assert all(x['status']=='PASS' for x in results)
    with (ROOT/'reports/phase3/PROGRESS.md').open('a') as f:f.write(f'\nContainer load {run}: {users} clients, {min(begin+users,20)}/20 samples flushed; current peak {peak}.\n')
    time.sleep(max(0,len(indexes)/2-(time.monotonic()-batch_start)))
  values=sorted(x['elapsed_seconds'] for x in rows if x['users']==users);n=len(values);i=(n-1)*.95;low=int(i);p95=values[low]+(values[min(low+1,n-1)]-values[low])*(i-low)
  resource=subprocess.check_output(['docker','stats','--no-stream','--format','{{json .}}',a.container],text=True).strip()
  item={'run_id':run,'users':users,'n':n,'failures':0,'p50_ms':statistics.median(values)*1000,'p95_ms':p95*1000,'actual_peak_inflight':peak,'wall_seconds':time.monotonic()-started,'resource':json.loads(resource),'global_average_cap_rps':2,'method':'20 reads per population; batches of <=users, paced average <=2RPS; exploratory p95, not saturation'};summary.append(item)
  with (out/'container-load-batches.jsonl').open('a') as f:f.write(json.dumps(item)+'\n');f.flush();os.fsync(f.fileno())
 (out/('container-load-summary-'+run+'.json')).write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
