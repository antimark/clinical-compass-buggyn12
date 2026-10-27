"""One extra ordinary synthetic physician; no patient links/consents are seeded."""
import argparse,json,os,secrets
from pathlib import Path
from cc_api import create_app
from cc_api.evaluation_launcher import workspace_config
from cc_api.evaluation_workspace import provision_account
p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);args=p.parse_args()
root=Path(args.workspace).resolve();target=root/'jury-second-doctor.json'
if target.exists():print('Private extra physician retained.');raise SystemExit(0)
app=create_app(workspace_config(root))
try:
 email='second-'+secrets.token_hex(6)+'@evaluation.test';password=secrets.token_urlsafe(24)
 uid=provision_account(app,email,password,role='doctor')
 fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'w') as f:json.dump({'email':email,'password':password,'id':uid},f)
finally:
 app.extensions['safety_runtime'].close();app.extensions['cc_session_factory'].kw['bind'].dispose()
print('Extra ordinary physician provisioned privately; no clinical relationship created.')
