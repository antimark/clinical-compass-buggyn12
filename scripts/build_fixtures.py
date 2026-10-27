"""Idempotent reproducible *synthetic demo only* invitation fixture builder.

Produces deterministic code for demos; NEVER enable outside CC_DEMO_MODE=1.
Do not paste output into diagnostic logs. Use ephemeral demo databases.
"""
import argparse, hashlib, hmac, os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from cc_api import create_app
from cc_api.extension_models import Invitation

p=argparse.ArgumentParser()
p.add_argument('--print-code',action='store_true',help='Show synthetic demo code once in terminal')
args=p.parse_args()
if os.environ.get('CC_DEMO_MODE')!='1':
    raise SystemExit('Refusing fixture registration outside explicit synthetic demo mode')
if not os.environ.get('CC_DB_PATH'):
    raise SystemExit('Set CC_DB_PATH to an isolated synthetic fixture database')
app=create_app()
key=os.environ.get('CC_FIXTURE_SEED','Clinical-Compass-SYNTHETIC-v08-not-secret')
code='CC-DEMO-'+hmac.new(key.encode(),b'doc_ther/pat_03/pat_c/symptoms',hashlib.sha256).hexdigest()[:22]
with app.extensions['cc_session_factory'].begin() as db:
    match=db.query(Invitation).filter_by(code_hash=hashlib.sha256(code.encode()).hexdigest()).first()
    if not match:
        row=Invitation(id='synthetic_persistent_invitation_01',code_hash=hashlib.sha256(code.encode()).hexdigest(),
            issuer_id='doc_ther',recipient_id='pat_03',patient_id='pat_c',target_role='patient',categories='symptoms',
            organization_id='org_demo',expires_at=(datetime.now(timezone.utc)+timedelta(days=7)).isoformat(),status='pending')
        db.add(row)
if args.print_code:
    print(code)
else:
    print('Synthetic fixture installed; add --print-code to reveal the deterministic registration code.')
