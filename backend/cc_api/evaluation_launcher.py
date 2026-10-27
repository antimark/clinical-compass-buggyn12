"""Operator evaluation launcher. Existing runtime/auth only; never resets or installs."""
import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
import stat
from urllib.request import build_opener,ProxyHandler
from .evaluation_workspace import provision_account,WARNING


def workspace_config(workspace):
    root=Path(workspace).expanduser().resolve()
    if root.is_relative_to(Path(__file__).resolve().parents[2]):raise ValueError('Choose an evaluation workspace outside the source/distribution folder')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not root.is_dir():raise ValueError('Workspace must be a directory')
    if stat.S_IMODE(root.stat().st_mode)&0o077:raise ValueError('Evaluation workspace must be private (chmod700)')
    key=root/'session.secret'
    try:
        fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:pass
    else:
        with os.fdopen(fd,'w') as file:file.write(secrets.token_urlsafe(48))
    if key.is_symlink() or not key.is_file():raise ValueError('Session secret must be an ordinary private file')
    if stat.S_IMODE(key.stat().st_mode)&0o077:raise ValueError('Session secret permissions must be0600; do not share it')
    # Stable, private local encryption key for optional patient-controlled
    # administrative identity fields. Flags/policies stay OFF until explicit consent.
    pii_key=root/'identity-fernet.key'
    from cryptography.fernet import Fernet
    try:
        pii_fd=os.open(pii_key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:pass
    else:
        with os.fdopen(pii_fd,'wb') as file:file.write(Fernet.generate_key())
    if pii_key.is_symlink() or not pii_key.is_file() or stat.S_IMODE(pii_key.stat().st_mode)&0o077:
        raise ValueError('Private identity encryption key must be a regular mode0600 file')
    try:
        Fernet(pii_key.read_bytes().strip())
    except (ValueError,TypeError):
        raise ValueError('Invalid identity encryption key')
    os.environ['CC_PII_ENCRYPTION_KEY']=pii_key.read_text().strip()
    secret=key.read_text().strip()
    if len(secret)<32:raise ValueError('Session secret invalid; preserve a valid stable operator secret')
    if os.environ.get('CC_DATABASE_URL'):raise ValueError('Unset CC_DATABASE_URL: evaluation launcher owns an isolated SQLite workspace')
    return dict(APP_ENV='evaluation_sandbox',DEMO_MODE=True,EVALUATION_ACKNOWLEDGED=True,
        EVALUATION_TENANT='evaluation_sandbox',SECRET_KEY=secret,DB_PATH=str(root/'organizer-evaluation.sqlite'),SEED_PATIENT_PERSONAS=False)


def check_runtime():
    """Bounded loopback health, no prompt or external request, no model pull."""
    model=os.environ.get('CC_CI_NLP_MODEL','qwen3:4b-instruct')
    from cc_nlp.providers.ollama import _DenyRedirect
    opener=build_opener(ProxyHandler({}),_DenyRedirect())
    try:
        with opener.open('http://127.0.0.1:11434/api/tags',timeout=5) as response:
            data=json.loads(response.read(100000))
        found=any(row.get('name')==model or row.get('model')==model for row in data.get('models',[]))
    except Exception:
        return dict(local_ollama='unavailable',configured_model=model,model_installed=False)
    return dict(local_ollama='available',configured_model=model,model_installed=found)


def main():
    parser=argparse.ArgumentParser(description='Isolated Evaluation MVP; no model/package installation or data reset')
    parser.add_argument('command',choices=['check','doctor','account','privacy-setup','serve'])
    parser.add_argument('--workspace',required=True,help='Private persistent directory OUTSIDE the source/distribution folder')
    parser.add_argument('--email',help='Physician account .test/.example email; required only for doctor')
    parser.add_argument('--role',choices=['doctor','clinic_admin','researcher'],default='doctor',help='Operator account command only; no clinical grants or verified credentials')
    parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('Invalid port')
    if args.command in ('doctor','account') and not args.email:parser.error('--email is required for doctor provisioning')
    config=workspace_config(args.workspace)
    if args.command=='check':
        from importlib import import_module
        for name in ('flask','sqlalchemy','alembic','jsonschema'):import_module(name)
        health=check_runtime()
        print(json.dumps(dict(environment='evaluation_sandbox',database='isolated_persistent_sqlite',**health)))
        if not health['model_installed']:raise SystemExit(2)
        return
    from . import create_app
    config['PUBLIC_BASE_URL']='http://127.0.0.1:'+str(args.port)
    app=create_app(config)
    if args.command == 'privacy-setup':
        # Operator opt-in exclusively in the isolated evaluation workspace.
        # No patient's consent or protected value is auto-created or disclosed.
        import uuid
        from sqlalchemy import select
        from .admin_privacy_models import AdminPrivacyFlag, AdminPrivacyTemplate
        from .utilities import utc_now
        import json as _json
        SessionLocal=app.extensions['cc_session_factory']
        with SessionLocal.begin() as db:
            for scope in ('GLOBAL','org:evaluation_sandbox'):
                flag=db.get(AdminPrivacyFlag,scope)
                if flag is None:db.add(AdminPrivacyFlag(scope=scope,enabled=True))
                else:flag.enabled=True
            existing=db.scalar(select(AdminPrivacyTemplate).where(
                AdminPrivacyTemplate.organization_id=='evaluation_sandbox',
                AdminPrivacyTemplate.template_key=='patient_name_only',
                AdminPrivacyTemplate.version==1))
            if existing is None:
                db.add(AdminPrivacyTemplate(id='apt_'+uuid.uuid4().hex,
                    organization_id='evaluation_sandbox',template_key='patient_name_only',
                    version=1,read_fields_json=_json.dumps(['first_name','last_name','middle_name']),
                    created_at=utc_now()))
        print('Optional identity display enabled for evaluation_sandbox. It remains empty/hidden UNTIL each linked patient explicitly saves values and accepts the template. No clinical data disclosed.')
        return
    if args.command in ('doctor','account'):
        password=getpass.getpass('New evaluation account password (12+ characters): ')
        if password!=getpass.getpass('Repeat password: '):raise ValueError('Passwords do not match')
        provision_account(app,args.email,password,role='doctor' if args.command=='doctor' else args.role)
        print('Evaluation account created; no clinical grants or professional/email/MFA verification established. '+WARNING)
    else:
        print(WARNING)
        print('Evaluation UI: '+config['PUBLIC_BASE_URL']+' — private local test inbox only; no emergency monitoring')
        app.run(host='127.0.0.1',port=args.port,debug=False,use_reloader=False)

if __name__=='__main__':main()
