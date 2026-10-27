"""Container-only WSGI factory; native evaluation launcher remains loopback-only."""
import os
from urllib.parse import urlsplit
from cc_api import create_app
from cc_api.evaluation_launcher import workspace_config
config=workspace_config(os.environ.get('CC_WORKSPACE','/workspace'))
base=os.environ.get('CC_PUBLIC_BASE_URL','http://127.0.0.1:8766')
url=urlsplit(base)
if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost','::1') or url.username or url.password or url.query or url.fragment or url.path not in ('','/'):
    raise RuntimeError('Jury public origin must remain loopback HTTP')
config['PUBLIC_BASE_URL']=base.rstrip('/')
app=create_app(config)
