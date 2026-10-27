"""Read-only loopback model readiness; no prompt, source text or cloud request."""
import json,os
from urllib.request import build_opener,ProxyHandler
from cc_nlp.providers.ollama import _DenyRedirect
model=os.environ.get('CC_CI_NLP_MODEL','qwen3:4b-instruct')
with build_opener(ProxyHandler({}),_DenyRedirect()).open('http://127.0.0.1:11434/api/tags',timeout=5) as response:
    tags=json.loads(response.read(100000))
item=next((r for r in tags.get('models',[]) if r.get('name')==model or r.get('model')==model),None)
print(json.dumps({'transport':'loopback namespace','configured_model':model,'installed':item is not None,'digest':item.get('digest') if item else None}))
raise SystemExit(0 if item else 2)
