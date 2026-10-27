"""Mac operator preflight: pinned local Qwen, one harmless token, bounded warmup."""
import json
import time
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError

MODEL='qwen3:4b-instruct'
DIGEST='0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0'


def main():
    from urllib.request import HTTPRedirectHandler
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=build_opener(ProxyHandler({}),NoRedirect())
    with opener.open('http://127.0.0.1:11434/api/tags',timeout=5) as response:
        models=json.load(response)['models']
    assert any(m.get('name')==MODEL and m.get('digest')==DIGEST for m in models),'Pinned model missing; see Docker jury runbook'
    start=time.monotonic()
    data=json.dumps({'model':MODEL,'stream':False,'think':False,'keep_alive':'30m',
        'messages':[{'role':'user','content':'Reply OK.'}],
        'options':{'num_predict':1,'num_ctx':4096,'temperature':0}}).encode()
    request=Request('http://127.0.0.1:11434/api/chat',data=data,headers={'Content-Type':'application/json'})
    with opener.open(request,timeout=60) as response:result=json.load(response)
    assert result.get('model')==MODEL and result.get('done') is True
    print(json.dumps({'status':'ready','model':MODEL,'digest':DIGEST,'warmup_seconds':round(time.monotonic()-start,3),'keep_alive':'30m'}))


if __name__=='__main__':main()
