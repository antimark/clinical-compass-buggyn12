"""One benign local model readiness generation; exports metadata only."""
import datetime as dt,json,time
from urllib.request import build_opener,ProxyHandler,Request
from cc_nlp.providers.ollama import _DenyRedirect
start=time.monotonic();payload={'model':'qwen3:4b-instruct','stream':False,'think':False,'prompt':'Техническая синтетическая проверка. Напиши только ОК.','options':{'temperature':0,'num_predict':8,'num_ctx':4096},'keep_alive':'10m'}
request=Request('http://127.0.0.1:11434/api/generate',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'},method='POST')
with build_opener(ProxyHandler({}),_DenyRedirect()).open(request,timeout=180) as response:data=json.loads(response.read(100000))
result={k:data.get(k) for k in ('model','done','done_reason','total_duration','load_duration','prompt_eval_count','prompt_eval_duration','eval_count','eval_duration')}
result.update(timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),status='PASS' if data.get('done') and data.get('response') else 'FAIL',wall_seconds=time.monotonic()-start,n=1,method='one benign direct loopback generation; not application journey acceptance')
print(json.dumps(result));raise SystemExit(0 if result['status']=='PASS' else 1)
