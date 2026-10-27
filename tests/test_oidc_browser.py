"""Focused real-cryptography tests; IdP exchanges stubbed only in this unit suite."""
import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import Flask, session
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from cc_api.models import Base, User
from cc_api.oidc_models import OidcLoginAttempt, OidcBrowserSession
from cc_api import oidc_browser as ob


@pytest.fixture
def rig(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()));jwk['kid']='unit-key'
    for name,value in {'CC_OIDC_BROWSER_ENABLED':'1','CC_OIDC_ISSUER':'https://id.example/realms/cc',
        'CC_OIDC_CLIENT_ID':'browser','CC_OIDC_AUDIENCE':'api','CC_OIDC_JWKS_JSON':json.dumps({'keys':[jwk]}),
        'CC_OIDC_REDIRECT_URI':'https://app.example'+ob.PREFIX+'/callback'}.items(): monkeypatch.setenv(name,value)
    engine=create_engine('sqlite:///'+str(tmp_path/'oidc.sqlite'))
    Base.metadata.create_all(engine);factory=sessionmaker(engine,expire_on_commit=False)
    with factory.begin() as db:
        for id,role in [('patient','patient'),('doctor','doctor'),('admin','clinic_admin')]:
            db.add(User(id=id,display_name=id,role=role,organization_id='org',external_subject='sub-'+id))
    app=Flask(__name__);app.secret_key='isolated-oidc-test';app.config['TESTING']=True
    ob.register_oidc_browser(app,factory)
    @app.get('/who')
    def who():
        with factory() as db:
            user=ob.browser_user(db)
            return {'user':user.id if user else None,'csrf':session.get('csrf_token')}
    @app.post('/logout')
    def logout():
        with factory.begin() as db: ob.revoke_browser_session(db)
        session.clear();return {}
    def start(client):
        response=client.get(ob.PREFIX+'/login?return_to=/%23/doctor')
        assert response.status_code==302
        return {k:v[0] for k,v in parse_qs(urlsplit(response.location).query).items()}
    def token(params,subject='sub-doctor',**changes):
        claims={'iss':'https://id.example/realms/cc','aud':'browser','sub':subject,
            'iat':int(time.time()),'exp':int(time.time())+600,'nonce':params['nonce'],'amr':['pwd','otp']}
        claims.update(changes)
        return jwt.encode(claims,key,algorithm='RS256',headers={'kid':'unit-key'})
    return app,factory,start,token,monkeypatch


def exchange(rig,params,token):
    monkeypatch=rig[4]
    def fake(issuer,client,target,code,verifier):
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        assert challenge==params['code_challenge'];assert params['code_challenge_method']=='S256'
        return {'id_token':token}
    monkeypatch.setattr(ob,'exchange_code',fake)


def callback(client,params,**extra):
    return client.get(ob.PREFIX+'/callback',query_string={'state':params['state'],'code':'one-use-code',**extra})


def test_success_opaque_revocable_and_replay(rig):
    app,factory,start,token,_=rig;client=app.test_client();params=start(client)
    exchange(rig,params,token(params));response=callback(client,params)
    assert response.status_code==302 and response.location=='/#/doctor'
    assert client.get('/who').json['user']=='doctor'
    with client.session_transaction() as cookie:
        assert set(cookie)=={'oidc_session','csrf_token'};opaque=cookie['oidc_session']
    with factory() as db:
        row=db.scalar(select(OidcBrowserSession));assert row.token_hash==ob.digest(opaque)
        attempt=db.scalar(select(OidcLoginAttempt));assert attempt.consumed_at and attempt.verifier==''
    assert callback(client,params).status_code==400
    client.post('/logout');assert client.get('/who').json['user'] is None
    with client.session_transaction() as cookie:cookie['oidc_session']=opaque
    assert client.get('/who').json['user'] is None


@pytest.mark.parametrize('changes',[{'nonce':'wrong'},{'iss':'https://evil.test'}, {'aud':'other'},
    {'exp':1},{'iat':'future'},{'sub':'not-provisioned'}, {'amr':['pwd'],'acr':'1'},
    {'azp':'other'},{'aud':['browser','other']}, {'amr':'mfa'}])
def test_token_fail_closed(rig,changes):
    # Collection can precede this test by minutes on the Linux/container suite.
    # Keep the negative token genuinely in the future at execution time.
    if changes.get('iat') == 'future':
        changes = {**changes, 'iat': int(time.time()) + 300}
    app,_,start,token,_=rig;client=app.test_client();params=start(client)
    exchange(rig,params,token(params,**changes));assert callback(client,params).status_code==401
    assert client.get('/who').json['user'] is None


def test_patient_without_mfa_and_no_role_autogrant(rig):
    app,factory,start,token,_=rig;client=app.test_client();params=start(client)
    exchange(rig,params,token(params,'sub-patient',amr=['pwd'],realm_access={'roles':['admin']}))
    assert callback(client,params).status_code==302
    assert client.get('/who').json['user']=='patient'
    with factory.begin() as db:db.get(User,'patient').role='clinic_admin'
    assert client.get('/who').json['user'] is None


def test_browser_binding_expiry_and_external_subject_change(rig):
    app,factory,start,token,_=rig;client=app.test_client();params=start(client)
    exchange(rig,params,token(params))
    assert callback(app.test_client(),params).status_code==400
    with factory.begin() as db:db.scalar(select(OidcLoginAttempt)).expires_at='2000-01-01T00:00:00Z'
    assert callback(client,params).status_code==400
    params=start(client);exchange(rig,params,token(params));assert callback(client,params).status_code==302
    with factory.begin() as db:db.get(User,'doctor').external_subject='changed'
    assert client.get('/who').json['user'] is None


@pytest.mark.parametrize('target',['//evil.test','https://evil.test','/\\evil','/%0aevil','/#/doctor\nInjected'])
def test_open_redirect_denied(rig,target):
    assert rig[0].test_client().get(ob.PREFIX+'/login',query_string={'return_to':target}).status_code==422


def test_decline_is_consumed(rig):
    app,factory,start,_,_=rig;client=app.test_client();params=start(client)
    assert callback(client,params,error='access_denied').status_code==400
    with factory() as db:assert db.scalar(select(OidcLoginAttempt)).consumed_at


def test_persisted_session_expiry_and_audit(rig):
    app,factory,start,token,_=rig;client=app.test_client();params=start(client)
    exchange(rig,params,token(params));assert callback(client,params).status_code==302
    from cc_api.extension_models import Audit
    with factory.begin() as db:
        assert db.scalar(select(Audit)).action=='oidc.login'
        db.scalar(select(OidcBrowserSession)).expires_at='2000-01-01T00:00:00Z'
    assert client.get('/who').json['user'] is None


def test_real_logout_endpoint_csrf_and_revocation(rig):
    app,factory,start,token,_=rig;client=app.test_client();params=start(client)
    exchange(rig,params,token(params));assert callback(client,params).status_code==302
    assert client.post(ob.PREFIX+'/logout').status_code==403
    csrf=client.get('/who').json['csrf']
    assert client.post(ob.PREFIX+'/logout',headers={'X-CSRF-Token':csrf}).status_code==200
    with factory() as db: assert db.scalar(select(OidcBrowserSession)).revoked_at


def test_wrong_signing_key_rejected(rig):
    app,_,start,token,_=rig;client=app.test_client();params=start(client)
    claims=jwt.decode(token(params),options={'verify_signature':False})
    wrong=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    exchange(rig,params,jwt.encode(claims,wrong,algorithm='RS256',headers={'kid':'unit-key'}))
    assert callback(client,params).status_code==401


def test_disabled_profile_and_https_configuration(rig):
    app,_,_,_,monkeypatch=rig;monkeypatch.setenv('CC_OIDC_BROWSER_ENABLED','0')
    assert app.test_client().get(ob.PREFIX+'/capabilities').json['enabled'] is False
    assert app.test_client().get(ob.PREFIX+'/login').status_code==404
    monkeypatch.setenv('CC_OIDC_BROWSER_ENABLED','1');monkeypatch.setenv('CC_OIDC_ISSUER','http://evil.test/realms/x')
    with pytest.raises(RuntimeError):ob.settings()


def test_concurrent_state_consumption_exactly_once(rig):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    app,factory,start,token,monkeypatch=rig;origin=app.test_client();params=start(origin)
    exchange(rig,params,token(params));cookie=origin.get_cookie('session').value
    barrier=Barrier(2)
    def race(_):
        client=app.test_client();client.set_cookie('session',cookie);barrier.wait()
        return callback(client,params).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(race,range(2)))
    assert sorted(results)==[302,400]
    with factory() as db:assert len(db.scalars(select(OidcBrowserSession)).all())==1


def test_real_app_demo_cookie_prefers_oidc_and_never_falls_back(rig,tmp_path):
    from cc_api import create_app
    from datetime import timedelta
    from cc_api.oidc_browser import digest,stamp,now
    app=create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev',
        'SECRET_KEY':'isolated-oidc-realapp','DB_PATH':str(tmp_path/'realapp.sqlite')})
    factory=app.extensions['cc_session_factory'];token='realapp-opaque'
    with factory.begin() as db:
        db.add(User(id='oidc-actor',display_name='Синтетический врач',role='doctor',
            organization_id='oidc-org',external_subject='subject-realapp'))
        db.flush()
        db.add(OidcBrowserSession(id='realapp-session',token_hash=digest(token),user_id='oidc-actor',
            external_subject='subject-realapp',issuer='https://id.example/realms/cc',
            auth_time=stamp(now()),created_at=stamp(now()),expires_at=stamp(now()+timedelta(minutes=10)),
            amr_json='["pwd","otp"]'))
    client=app.test_client()
    with client.session_transaction() as cookie:
        cookie['oidc_session']=token;cookie['uid']='doc_psy'
    result=client.get('/api/v1/auth/me')
    assert result.status_code==200 and result.json['user']['id']=='oidc-actor'
    with client.session_transaction() as cookie:cookie['oidc_session']='invalid'
    assert client.get('/api/v1/auth/me').status_code==401
