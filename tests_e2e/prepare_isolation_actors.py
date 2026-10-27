"""Explicit operator-only foreign-tenant fixtures; no patient links or consent grants."""
import argparse,json,os,secrets
from pathlib import Path
from cc_api import create_app
from cc_api.evaluation_launcher import workspace_config
from cc_api.evaluation_workspace import provision_account
from cc_api.models import User
p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);a=p.parse_args()
root=Path(a.workspace).resolve();target=root/'jury-isolation-actors.json'
if target.exists():print('Existing private tenant-isolation actors retained.');raise SystemExit(0)
app=create_app(workspace_config(root));actors={}
try:
    for role in ('doctor','clinic_admin'):
        email='isolation-'+role+'-'+secrets.token_hex(4)+'@evaluation.test';password=secrets.token_urlsafe(24)
        uid=provision_account(app,email,password,role=role)
        # Operator creates a second synthetic organization, without any clinical
        # relationship, study grant, identity permission or patient role change.
        with app.extensions['cc_session_factory'].begin() as db:db.get(User,uid).organization_id='jury_foreign_clinic'
        actors[role]={'email':email,'password':password,'id':uid}
    fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as f:json.dump(actors,f)
finally:
    app.extensions['safety_runtime'].close();app.extensions['cc_session_factory'].kw['bind'].dispose()
print('Two ordinary foreign-tenant test accounts provisioned privately; no patient access or consent granted.')
