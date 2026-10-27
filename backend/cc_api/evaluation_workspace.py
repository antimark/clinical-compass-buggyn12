"""Explicit isolated Evaluation MVP deployment, normal local credentials, no reset API.
CLI: python -m cc_api.evaluation_workspace --db /absolute/separate.sqlite --email expert@evaluation.test
Password is read using getpass; no default credential and nothing sensitive printed.
"""
import argparse
import getpass
import os
import re
import secrets
from pathlib import Path
from werkzeug.security import generate_password_hash
from .verification import evaluation_enabled,normalize_synthetic_email
from .models import User
from .onboarding_models import LocalIdentity
from .utilities import utc_now

WARNING='Не загружайте персональные медицинские сведения. Используйте синтетический или надлежащим образом обезличенный клинический случай.'


def provision_physician(app,email,password,*,user_id=None):
    return provision_account(app,email,password,role='doctor',user_id=user_id)

def provision_account(app,email,password,*,role='doctor',user_id=None):
    """Operator-only provisioning, not an HTTP role elevation or auto credential verification."""
    if not evaluation_enabled(app.config):raise ValueError('Explicit evaluation workspace required')
    if role not in ('doctor','clinic_admin','researcher'):raise ValueError('Unsupported evaluation account role')
    email=normalize_synthetic_email(email)
    if not isinstance(password,str) or not 12<=len(password)<=128:raise ValueError('Strong evaluation password required')
    from sqlalchemy import select
    from .clinical_workflow_services import uid
    with app.extensions['cc_session_factory'].begin() as db:
        if db.scalar(select(LocalIdentity).where(LocalIdentity.email==email)):raise ValueError('Account already exists; never overwrite credentials')
        user=User(id=user_id or uid('eval_'),display_name={'doctor':'Врач Evaluation MVP','clinic_admin':'Администратор Evaluation MVP','researcher':'Исследователь Evaluation MVP'}[role],role=role,specialty='psychiatry' if role=='doctor' else None,organization_id='evaluation_sandbox')
        db.add(user);db.flush()
        db.add(LocalIdentity(user_id=user.id,email=email,password_hash=generate_password_hash(password),email_provider='evaluation_operator',email_status='not_verified',created_at=utc_now()))
        return user.id


def register_evaluation_policy(app):
    if not evaluation_enabled(app.config):return
    from flask import request
    @app.before_request
    def reject_obvious_identifiers():
        # This is a conservative input filter, NOT a proof of anonymization.
        # Actual identifying-data authorization is deliberately absent from this deployment.
        if request.method not in ('POST','PUT','PATCH') or not request.path.startswith('/api/v1/'):return
        if '/profile' in request.path:return
        if request.content_length and request.content_length>20000:return {'error':{'code':'EVALUATION_INPUT_LIMIT','message':WARNING}},413
        data=request.get_json(silent=True)
        if not isinstance(data,dict):return
        fields={'text','content','clinical_reason','reason','message','narrative','assessment','follow_up','note','notes'}
        def clinical_strings(value,key=''):
            if isinstance(value,str):return [value] if key in fields else []
            if isinstance(value,dict):return [x for k,v in value.items() for x in clinical_strings(v,k)]
            if isinstance(value,list):return [x for v in value for x in clinical_strings(v,key)]
            return []
        content=' '.join(clinical_strings(data))
        if re.search(r'\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b|(?:\+7|\b8)[\s(.-]*\d{3}[\s)./-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}\b|\b\d{3}-\d{3}-\d{3}\s?\d{2}\b|\bпаспорт\s*\d',content,re.I):
            return {'error':{'code':'IDENTIFIABLE_DATA_NOT_ALLOWED','message':WARNING}},422


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--db',required=True);parser.add_argument('--email',required=True);parser.add_argument('--port',type=int,default=8766);parser.add_argument('--serve',action='store_true')
    args=parser.parse_args()
    db=Path(args.db).resolve()
    if not db.is_absolute() or db.name in ('dev.sqlite','evaluation.sqlite'):raise ValueError('Choose a dedicated, explicitly named evaluation DB')
    from . import create_app
    # Stable deployment secret supplied by operator; never generate a new one on every restart.
    secret=os.environ.get('CC_SECRET_KEY')
    if not secret or len(secret)<32:raise ValueError('Set CC_SECRET_KEY to a unique >=32-character deployment secret')
    app=create_app(dict(APP_ENV='evaluation_sandbox',DEMO_MODE=True,EVALUATION_ACKNOWLEDGED=True,
        EVALUATION_TENANT='evaluation_sandbox',DB_PATH=str(db),SECRET_KEY=secret))
    if args.serve:
        app.run(host='127.0.0.1',port=args.port,debug=False)
    else:
        provision_physician(app,args.email,getpass.getpass('Evaluation account password: '))
        print('Evaluation physician provisioned. Email/credentials not externally verified. '+WARNING)

if __name__=='__main__':main()
