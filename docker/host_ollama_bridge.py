"""Reviewed Mac-only fixed host-gateway adapter; no arbitrary proxy capability.
Listens only on the app's shared loopback. Host Ollama remains bound to Mac loopback.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.request import build_opener,ProxyHandler,Request
from urllib.error import HTTPError,URLError
from cc_nlp.providers.ollama import _DenyRedirect

UPSTREAM='http://host.docker.internal:11434'
MODEL='qwen3:4b-instruct'
DIGEST='0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0'
MAX_REQUEST=128*1024
MAX_RESPONSE=1_000_000
GATE=threading.BoundedSemaphore(1)


def upstream(path,data=None):
    # Fixed destination + exact path whitelist; never follow redirects or env proxies.
    if path not in ('/api/tags','/api/chat'):raise ValueError('path_forbidden')
    request=Request(UPSTREAM+path,data=data,method='POST' if data is not None else 'GET',headers={'Content-Type':'application/json'})
    with build_opener(ProxyHandler({}),_DenyRedirect()).open(request,timeout=60 if data is not None else 5) as response:
        if response.status!=200:raise ValueError('upstream_unavailable')
        body=response.read(MAX_RESPONSE+1)
        if len(body)>MAX_RESPONSE:raise ValueError('upstream_response_too_large')
        return body


def verified_tags():
    blob=upstream('/api/tags');data=json.loads(blob)
    item=next((x for x in data.get('models',[]) if x.get('name')==MODEL or x.get('model')==MODEL),None)
    if not item or item.get('digest')!=DIGEST:raise ValueError('pinned_host_model_unavailable')
    # Do not expose unrelated host model inventory to the container application.
    return json.dumps({'models':[item]},ensure_ascii=False).encode()


def validate_payload(data):
    if not isinstance(data,dict) or set(data)-{'model','stream','format','messages','options','think'}:raise ValueError('invalid_fields')
    if data.get('model')!=MODEL or data.get('stream') is not False:raise ValueError('model_or_stream_forbidden')
    messages=data.get('messages')
    if not isinstance(messages,list) or not 1<=len(messages)<=16:raise ValueError('invalid_messages')
    for message in messages:
        if not isinstance(message,dict) or set(message)!={'role','content'} or message['role'] not in ('system','user','assistant') or not isinstance(message['content'],str) or len(message['content'])>64000:
            raise ValueError('invalid_messages')
    options=data.get('options',{})
    if not isinstance(options,dict) or set(options)-{'temperature','num_predict','num_ctx'}:raise ValueError('invalid_options')
    if type(options.get('num_predict')) is not int or not 1<=options['num_predict']<=1024:raise ValueError('generation_limit')
    if 'num_ctx' in options and (type(options['num_ctx']) is not int or not 1<=options['num_ctx']<=4096):raise ValueError('context_limit')
    if 'temperature' in options and (type(options['temperature']) not in (int,float) or not 0<=options['temperature']<=1):raise ValueError('temperature_limit')
    if 'think' in data and type(data['think']) is not bool:raise ValueError('invalid_think')
    # Match the verified native 4096-token context; never let a new host default
    # silently allocate a larger context. The app's source/role guards remain upstream.
    return {**data,'options':{**options,'num_ctx':options.get('num_ctx',4096)}}


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass  # No prompts, headers, cookies or model prose in logs.
    def reply(self,status,body):
        if isinstance(body,dict):body=json.dumps(body).encode()
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.send_header('Connection','close');self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
        self.close_connection=True
    def do_GET(self):
        if self.path=='/health':return self.reply(200,{'status':'ok','role':'fixed_local_host_ollama_adapter','model_readiness':'checked_separately'})
        if self.path!='/api/tags':return self.reply(404,{'error':'path_forbidden'})
        try:return self.reply(200,verified_tags())
        except (OSError,ValueError,HTTPError,URLError):return self.reply(503,{'error':'pinned_local_host_model_unavailable'})
    def do_POST(self):
        if self.path!='/api/chat':return self.reply(404,{'error':'path_forbidden'})
        if self.headers.get('Transfer-Encoding') or self.headers.get('Expect'):return self.reply(400,{'error':'unsupported_transfer'})
        try:length=int(self.headers.get('Content-Length','-1'))
        except ValueError:return self.reply(400,{'error':'invalid_length'})
        if not 1<=length<=MAX_REQUEST:return self.reply(413,{'error':'request_limit'})
        if self.headers.get_content_type()!='application/json':return self.reply(415,{'error':'json_required'})
        try:data=validate_payload(json.loads(self.rfile.read(length)))
        except (ValueError,TypeError):return self.reply(422,{'error':'invalid_or_forbidden_request'})
        if not GATE.acquire(blocking=False):return self.reply(503,{'error':'local_inference_busy'})
        try:
            verified_tags()  # Pin actual native model before any source prose is forwarded.
            return self.reply(200,upstream('/api/chat',json.dumps(data,ensure_ascii=False).encode()))
        except (OSError,ValueError,HTTPError,URLError):return self.reply(503,{'error':'local_host_inference_unavailable'})
        finally:GATE.release()
    def do_PUT(self):self.reply(405,{'error':'method_forbidden'})
    do_DELETE=do_PUT
    do_PATCH=do_PUT


if __name__=='__main__':
    print(json.dumps({'adapter':'fixed_local_host_ollama','listener':'127.0.0.1:11434','upstream':UPSTREAM,'model':MODEL,'digest':DIGEST,'public_model_port':False}),flush=True)
    ThreadingHTTPServer(('127.0.0.1',11434),Handler).serve_forever()
