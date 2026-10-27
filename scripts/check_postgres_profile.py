"""Validate migrations, persistence and ACL in a disposable PostgreSQL database.

Requires a trusted *synthetic-development-only* CC_TEST_PG_ADMIN_URL with
CREATE DATABASE permission. Creates cc_test_<random>; deletes it in finally.
"""
import os
import secrets
from urllib.parse import unquote
from sqlalchemy.engine import make_url
import psycopg
from psycopg import sql

ADMIN=os.environ.get('CC_TEST_PG_ADMIN_URL')
if not ADMIN:raise SystemExit('Set CC_TEST_PG_ADMIN_URL (PostgreSQL administration DSN)')
url=make_url(ADMIN)
if url.get_backend_name()!='postgresql':raise SystemExit('PostgreSQL only')
if url.host not in ('127.0.0.1','localhost','::1'):
    raise SystemExit('Only local synthetic PostgreSQL allowed by this script')
name='cc_test_'+secrets.token_hex(7)
connect_args={'host':url.host,'port':url.port or 5432,'dbname':url.database or 'postgres',
              'user':unquote(url.username or ''),'password':unquote(url.password or '')}
with psycopg.connect(**connect_args,autocommit=True) as admin:
    with admin.cursor() as cur:cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    try:
        new_url=url.set(database=name,drivername='postgresql+psycopg')
        os.environ['CC_DATABASE_URL']=new_url.render_as_string(hide_password=False)
        os.environ['CC_DEMO_MODE']='1'
        os.environ['CC_AI_MODE']='disabled'
        from sqlalchemy import inspect
        from cc_api import create_app
        app=create_app({'TESTING':True,'DEMO_MODE':True,'SECRET_KEY':'test_disposable_postgres'})
        c=app.test_client()
        assert c.get('/api/v1/health').status_code==200
        auth=c.post('/api/v1/dev/switch-user',json={'user_id':'clinic_01'})
        assert auth.status_code==200
        assert c.get('/api/v1/p0/clinic/patients').status_code==200
        assert c.get('/api/v1/p1/clinic/staff').status_code==200
        assert c.get('/api/v1/doctors/me/patients').status_code==403
        # Two independent HTTP-session clients race the exact same single-use invite.
        # The database compare-and-set must allow exactly one redemption.
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        issuer=app.test_client()
        doctor_login=issuer.post('/api/v1/dev/switch-user',json={'user_id':'doc_ther'})
        assert doctor_login.status_code==200
        invite=issuer.post('/api/v1/invitations',json={'target_role':'patient',
            'recipient_id':'pat_03','patient_id':'pat_c','categories':['symptoms']},
            headers={'X-CSRF-Token':doctor_login.json['csrf_token']})
        assert invite.status_code==201
        code=invite.json['registration_code']
        gate=Barrier(2)
        def redeem(_):
            independent=app.test_client()
            auth=independent.post('/api/v1/dev/switch-user',json={'user_id':'pat_03'})
            assert auth.status_code==200
            gate.wait(timeout=10)
            return independent.post('/api/v1/invitations/accept',json={'registration_code':code,'consent':True,'consent_version':'clinical-link-v1'},
                headers={'X-CSRF-Token':auth.json['csrf_token']}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            concurrent=list(pool.map(redeem,[1,2]))
        assert sorted(concurrent)[0]==200 and sorted(concurrent)[1] in (404,409),concurrent
        engine=app.extensions['cc_session_factory'].kw['bind']
        tables=set(inspect(engine).get_table_names())
        assert 'alembic_version' in tables and 'p0_care_plans' in tables and 'users' in tables
        engine.dispose()
        print(f'PostgreSQL test passed on disposable database {name}: Flask boot/migrations/roles')
    finally:
        with admin.cursor() as cur:
            cur.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(name)))
