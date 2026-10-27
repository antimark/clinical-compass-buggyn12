"""Provision ordinary synthetic roles in an explicitly supplied private QA workspace.
Generated credentials remain mode 0600 outside the source; never print them.
"""
import argparse,json,os,secrets
from pathlib import Path
from cc_api import create_app
from cc_api.evaluation_launcher import workspace_config
from cc_api.evaluation_workspace import provision_account

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);a=p.parse_args()
    root=Path(a.workspace).resolve();cfg=workspace_config(root);target=root/'jury-actors.json'
    if target.exists():
        print('Private synthetic actor file already exists; preserving accounts and passwords.');return
    app=create_app(cfg);actors={}
    try:
        for role in ('doctor','researcher','clinic_admin'):
            email=role+'-'+secrets.token_hex(4)+'@evaluation.test';password=secrets.token_urlsafe(24)
            uid=provision_account(app,email,password,role=role)
            actors[role]={'email':email,'password':password,'id':uid}
        fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as f:json.dump(actors,f)
    finally:
        app.extensions['safety_runtime'].close();app.extensions['cc_session_factory'].kw['bind'].dispose()
    print('Provisioned three ordinary synthetic roles. Credentials saved privately outside source; no grants created.')
if __name__=='__main__':main()
