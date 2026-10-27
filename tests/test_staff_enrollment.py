"""Invited-staff authorization unit suite; actual IdP evidence is separate."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
import pytest
from flask import Flask,abort,session
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from cc_api.models import Base,User,DoctorPatientLink
from cc_api.onboarding_models import LocalIdentity,StaffVerification
from cc_api.oidc_models import OidcBrowserSession
from cc_api.oidc_browser import now,stamp,digest
from cc_api.staff_enrollment_models import StaffEnrollmentInvitation
from cc_api.staff_enrollment_routes import register_staff_enrollment_routes,BASE


@pytest.fixture
def rig(tmp_path,monkeypatch):
    # No forged token masquerades as actual infrastructure evidence. These
    # persisted session rows exercise domain policy only; real MFA runs via IdP.
    for name,value in {'CC_OIDC_BROWSER_ENABLED':'1','CC_OIDC_ISSUER':'https://identity.test/realms/cc',
        'CC_OIDC_CLIENT_ID':'cc','CC_OIDC_REDIRECT_URI':'https://app.test/api/v1/auth/oidc/callback',
        'CC_OIDC_JWKS_JSON':'{"keys":[]}'}.items():monkeypatch.setenv(name,value)
    engine=create_engine('sqlite:///'+str(tmp_path/'enrollment.sqlite'),connect_args={'timeout':20})
    Base.metadata.create_all(engine);factory=sessionmaker(engine,expire_on_commit=False)
    with factory.begin() as db:
        for id,role,org in [('issuer','clinic_admin','org'),('other','clinic_admin','other'),('patient','patient','org')]:
            db.add(User(id=id,display_name=id,role=role,organization_id=org,external_subject='subject-'+id))
    app=Flask(__name__);app.secret_key='isolated-enrollment';app.config.update(TESTING=True,APP_ENV='synthetic_dev',DEMO_MODE=False)
    def current(db):
        from cc_api.oidc_browser import browser_user
        return browser_user(db) or db.get(User,session.get('unit_actor',''))
    def role(db,expected):
        user=current(db)
        if not user:abort(401)
        if user.role!=expected:abort(403)
        return user
    def error(code,kind,message):return {'error':{'code':kind,'message':message}},code
    register_staff_enrollment_routes(app,factory,current,role,error,lambda:stamp(now()))
    def client(id='issuer',mfa=True,oidc=False):
        c=app.test_client()
        with c.session_transaction() as s:
            s['unit_actor']=id
            if oidc:
                token='opaque-'+id
                s['oidc_session']=token
                with factory.begin() as db:
                    user=db.get(User,id)
                    db.add(OidcBrowserSession(id='s-'+id,token_hash=digest(token),user_id=id,
                        external_subject=user.external_subject,issuer='https://identity.test/realms/cc',
                        auth_time=stamp(now()),created_at=stamp(now()),expires_at=stamp(now()+timedelta(hours=1)),
                        amr_json=json.dumps(['pwd','otp'] if mfa else ['pwd'])))
        return c
    return app,factory,client


def invite(client,**extra):
    payload={'recipient_email':'candidate@reserved.test','display_name':'Синтетический врач',
        'external_subject':'new-subject','specialty':'psychiatry',**extra}
    return client.post(BASE+'/invitations',json=payload)


def candidate(rig,inv,mfa=True):
    id=inv.json['recipient']['id'];return rig[2](id,mfa,True)


def accept(client,inv,**extra):
    return client.post(BASE+'/accept',json={'token':inv.json['token'],'accept':True,**extra})


def test_real_authority_and_explicit_acceptance(rig):
    _,factory,actor=rig;inv=invite(actor());assert inv.status_code==201
    with factory() as db:
        user=db.get(User,inv.json['recipient']['id']);assert user.role=='staff_candidate' and not user.specialty
        assert db.get(LocalIdentity,user.id) is None
    c=candidate(rig,inv)
    preview=c.post(BASE+'/preview',json={'token':inv.json['token']})
    assert preview.status_code==200 and preview.json['requires_explicit_acceptance']
    assert c.get(BASE+'/invitation').status_code==400
    assert inv.json['url'].startswith('/#/register/specialist?token=')
    assert accept(c,inv,accept=False).status_code==422
    result=accept(c,inv);assert result.status_code==200,result.json
    assert result.json['role_authority']=='clinic_admin_invitation'
    provider=result.json['professional_verification'];assert not provider['grants_roles'] and not provider['real_credentials_verified']
    with factory() as db:
        user=db.get(User,inv.json['recipient']['id']);assert user.role=='doctor' and user.specialty=='psychiatry'
        assert db.get(StaffVerification,user.id).status=='verified_synthetic'
        assert db.scalars(select(DoctorPatientLink)).all()==[]
        assert db.get(LocalIdentity,user.id) is None
    assert accept(c,inv).status_code==409


@pytest.mark.parametrize('role',['patient','other'])
def test_invitation_issuer_role_and_tenant(rig,role):
    _,_,actor=rig
    if role=='patient':assert invite(actor(role)).status_code==403
    else:
        inv=invite(actor());assert actor('other').post(BASE+'/invitations/'+inv.json['id']+'/revoke',json={}).status_code==404


def test_existing_subject_never_overwritten(rig):
    _,factory,actor=rig
    for subject in ['subject-patient','subject-issuer']:
        assert invite(actor(),external_subject=subject).status_code==409
    with factory() as db:
        assert db.get(User,'patient').role=='patient' and db.get(User,'issuer').role=='clinic_admin'


@pytest.mark.parametrize('extra',[{'recipient_email':'real@example.com'},{'specialty':'platform_admin'},
    {'external_subject':''},{'ttl_hours':True},{'ttl_hours':0},{'organization_id':'other'},{'role':'doctor'}])
def test_rejects_untrusted_fields(rig,extra):
    assert invite(rig[2](),**extra).status_code==422


def test_mfa_oidc_session_required_and_subject_bound(rig):
    _,factory,actor=rig;inv=invite(actor());id=inv.json['recipient']['id']
    assert accept(actor(id),inv).status_code==401
    assert accept(candidate(rig,inv,mfa=False),inv).status_code==401
    # Restore genuine-assurance unit fixture, not an API-controlled property.
    with factory.begin() as db:db.get(OidcBrowserSession,'s-'+id).amr_json='["pwd","otp"]'
    c=actor(id)
    with c.session_transaction() as s:s['oidc_session']='opaque-'+id
    assert c.post(BASE+'/accept',json={'token':inv.json['token'],'accept':True,'mfa_verified':True}).status_code==422
    assert c.post(BASE+'/accept',json={'token':inv.json['token'],'accept':True},headers={'Authorization':'Bearer anything'}).status_code==403
    with factory.begin() as db:db.get(User,id).external_subject='changed'
    assert accept(c,inv).status_code==401


def test_expiry_revoke_and_wrong_candidate(rig):
    _,factory,actor=rig;inv=invite(actor());c=candidate(rig,inv)
    second=invite(actor(),external_subject='second',recipient_email='other@reserved.test')
    wrong=candidate(rig,second)
    assert accept(wrong,inv).status_code==404
    assert actor().post(BASE+'/invitations/'+inv.json['id']+'/revoke',json={}).status_code==200
    assert accept(c,inv).status_code==409
    with factory.begin() as db:db.get(StaffEnrollmentInvitation,second.json['id']).expires_at='2000-01-01T00:00:00Z'
    assert accept(wrong,second).status_code==410
    with factory() as db:assert db.get(User,second.json['recipient']['id']).role=='staff_candidate'


def test_current_issuer_authority_and_org_rechecked(rig):
    _,factory,actor=rig;inv=invite(actor());c=candidate(rig,inv)
    with factory.begin() as db:db.get(User,'issuer').organization_id='other'
    assert accept(c,inv).status_code==403
    with factory() as db:assert db.get(User,inv.json['recipient']['id']).role=='staff_candidate'


def test_accept_vs_revoke_race_preserves_one_transition(rig):
    app,factory,actor=rig;admin=actor();inv=invite(admin);c=candidate(rig,inv)
    candidate_cookie=c.get_cookie('session').value;admin_cookie=admin.get_cookie('session').value
    barrier=Barrier(2)
    def run(kind):
        client=app.test_client();client.set_cookie('session',candidate_cookie if kind=='accept' else admin_cookie)
        barrier.wait()
        return (kind,accept(client,inv).status_code if kind=='accept' else client.post(BASE+'/invitations/'+inv.json['id']+'/revoke',json={}).status_code)
    with ThreadPoolExecutor(2) as pool:results=dict(pool.map(run,['accept','revoke']))
    assert sorted(results.values())==[200,409],results
    with factory() as db:
        row=db.get(StaffEnrollmentInvitation,inv.json['id']);user=db.get(User,inv.json['recipient']['id'])
        assert bool(row.accepted_at)!=bool(row.revoked_at)
        assert (user.role=='doctor')==bool(row.accepted_at)


def test_profile_capability_never_claims_real_verification(rig):
    app,_,actor=rig
    data=actor().get(BASE+'/capabilities').json
    assert data['synthetic_invited_enrollment_enabled'] and not data['verified_staff_enrollment_enabled']
    app.config['APP_ENV']='production'
    assert not actor().get(BASE+'/capabilities').json['synthetic_invited_enrollment_enabled']
    assert invite(actor()).status_code==403
