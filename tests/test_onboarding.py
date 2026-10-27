"""Synthetic-dev onboarding persistence/ACL gates; no production identity claims.

Run in the existing Conda environment: python -m pytest -q tests/test_onboarding.py.
SQLite concurrency below proves demo CAS behavior only; PostgreSQL and Keycloak
remain independent acceptance gates.
"""
from auth_support import login_response
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import select, text
from werkzeug.security import check_password_hash

from cc_api import create_app
from cc_api.models import DoctorPatientLink, User

OB='/api/v1/onboarding'
PASSWORD='Synthetic-only-passphrase-42'


@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev',
        'SECRET_KEY':'isolated-onboarding-tests','DB_PATH':str(tmp_path/'onboarding.sqlite'),
        'PUBLIC_BASE_URL':'https://compass.example'})


@pytest.fixture
def client(app):
    client=app.test_client()
    bootstrap(client)
    return client


def bootstrap(client):
    response=client.get(OB+'/bootstrap')
    assert response.status_code==200,response.json
    if response.json['enabled']:
        assert response.json['csrf_token']
    return response.json


def mutate(client,method,path,payload):
    return client.open(path,method=method,json=payload,
        headers={'X-CSRF-Token':bootstrap(client)['csrf_token'] or ''})


def register(client,email='patient@qa.test',**extra):
    payload={'display_name':'Синтетический новый пациент','email':email,
        'password':PASSWORD,'terms_consent':True,**extra}
    response=mutate(client,'POST',OB+'/register',payload)
    assert response.status_code==201,response.json
    assert response.json['context']['role']=='patient'
    assert response.json['csrf_token']
    return response.json


def actor(app,user='doc_psy'):
    client=app.test_client()
    response=login_response(client,user)
    assert response.status_code==200,response.json
    return client


def issue(doctor,email='patient@qa.test',categories=None):
    response=mutate(doctor,'POST',OB+'/invitations',{'recipient_email':email,
        'categories':categories if categories is not None else ['symptoms'],'ttl_hours':24})
    assert response.status_code==201,response.json
    assert response.json['url']=='/invite/'+response.json['token']
    return response.json


def accept(patient,inv,**extra):
    return mutate(patient,'POST',OB+'/invitations/accept',{'token':inv['token'],
        'consent':True,'consent_version':'clinical-link-v1',**extra})


def assert_empty_own_records(client):
    for path in ('/api/v1/previsit-cases','/api/v1/patients/me/links',
                 '/api/v1/patients/me/check-ins',OB+'/records'):
        response=client.get(path)
        assert response.status_code==200,(path,response.json)
        assert response.json['items']==[],(path,response.json)
    clinical=client.get('/api/v1/patients/me/clinical')
    assert clinical.status_code==200
    assert clinical.json['diagnoses']==[] and clinical.json['medications']==[]


def test_bootstrap_csrf_and_verified_vs_synthetic_capabilities(client):
    boot=bootstrap(client)
    assert boot['enabled'] is True and boot['authenticated'] is False
    assert boot['environment']=='synthetic_dev'
    assert boot['email_verification']=='synthetic_auto'
    assert boot['professional_verification']=='synthetic_auto'
    assert boot['production_verification']=='DEFERRED_BY_PRODUCT_DECISION'
    caps=client.get('/api/v1/p0/auth/capabilities').json
    assert caps['registration_enabled'] is False
    assert caps['synthetic_registration_enabled'] is True
    payload={'display_name':'Новый пациент','email':'csrf@qa.test','password':PASSWORD,'terms_consent':True}
    assert client.post(OB+'/register',json=payload).status_code==403
    assert client.post(OB+'/register',json=payload,headers={'X-CSRF-Token':'invalid'}).status_code==403
    before=boot['csrf_token']
    result=register(client,'csrf@qa.test')
    assert result['csrf_token']!=before
    assert client.get('/api/v1/auth/me').json['user']['id']==result['user']['id']
    assert client.put(OB+'/state',json={'status':'completed'},headers={'X-CSRF-Token':before}).status_code==403


@pytest.mark.parametrize('environment',['development','production','synthetic_development'])
def test_new_local_auth_profile_is_explicit_only(tmp_path,environment):
    app=create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':environment,
        'SECRET_KEY':'profile-disabled','DB_PATH':str(tmp_path/'disabled.sqlite')})
    client=app.test_client()
    boot=bootstrap(client)
    assert boot['enabled'] is False
    for path,payload in [('/register',{'email':'disabled@qa.test'}),('/login',{'email':'disabled@qa.test'}),
                         ('/professional-verification',{})]:
        assert mutate(client,'POST',OB+path,payload).status_code==403
    assert client.get('/api/v1/p0/auth/capabilities').json['registration_enabled'] is False


@pytest.mark.parametrize('changes',[
    {'role':'doctor'},{'organization_id':'org_other'},{'patient_id':'pat_a'},
    {'email':'real@gmail.com'},{'password':'short'},{'password':'a'*129},
    {'terms_consent':False},{'terms_consent':'true'},{'display_name':'X'},
])
def test_registration_rejects_invalid_or_privileged_fields(client,changes):
    response=mutate(client,'POST',OB+'/register',{'display_name':'Новый пациент',
        'email':'validation@qa.test','password':PASSWORD,'terms_consent':True,**changes})
    assert response.status_code==422,response.json
    assert client.get('/api/v1/auth/me').status_code==401


def test_cookie_bound_draft_registration_logout_login_and_restart(app,client):
    draft=client.get(OB+'/journey')
    assert draft.status_code==200
    saved=mutate(client,'PUT',OB+'/journey',{'revision':draft.json['revision'],
        'doctor_id':'doc_ther','subject':'Первое знакомство','message':'Синтетический сохранённый черновик'})
    assert saved.status_code==200,saved.json
    assert saved.json['revision']>draft.json['revision']
    assert client.get(OB+'/journey').json==saved.json
    assert mutate(client,'PUT',OB+'/journey',{'revision':draft.json['revision'],'message':'Stale replacement'}).status_code==409
    stranger=app.test_client()
    bootstrap(stranger)
    other=stranger.get(OB+'/journey').json
    assert other['id']!=saved.json['id'] and other['message']==''
    assert mutate(stranger,'PUT',OB+'/journey',{'id':saved.json['id'],'revision':other['revision'],'message':'Cannot adopt'}).status_code==422
    registered=register(client,'  Restore@QA.TEST  ')
    uid=registered['user']['id']
    assert_empty_own_records(client)
    assert client.get(OB+'/journey').json['message']==saved.json['message']
    with app.extensions['cc_session_factory']() as db:
        identity=db.execute(text('SELECT email,password_hash FROM ob_identities WHERE user_id=:uid'),{'uid':uid}).mappings().one()
        assert identity['email']=='restore@qa.test'
        assert identity['password_hash']!=PASSWORD
        assert check_password_hash(identity['password_hash'],PASSWORD)
        user=db.get(User,uid)
        assert user.patient_id not in ('pat_a','pat_b','pat_c')
        assert user.organization_id=='org_demo'
    state=mutate(client,'PUT',OB+'/state',{'introduction_seen':True,'status':'completed'})
    assert state.status_code==200,state.json
    assert state.json['status']=='completed'
    assert mutate(client,'PUT',OB+'/state',{'patient_id':'pat_a','status':'completed'}).status_code==422
    csrf=bootstrap(client)['csrf_token']
    logout=mutate(client,'POST',OB+'/logout',{})
    assert logout.status_code==200 and logout.json['csrf_token']!=csrf
    assert client.get('/api/v1/auth/me').status_code==401
    assert client.get(OB+'/state').status_code==401
    assert client.get(OB+'/journey').json['message']==''
    bad=mutate(client,'POST',OB+'/login',{'email':'restore@qa.test','password':'incorrect-password'})
    missing=mutate(client,'POST',OB+'/login',{'email':'missing@qa.test','password':'incorrect-password'})
    assert bad.status_code==missing.status_code==401
    assert bad.json['error']==missing.json['error']
    # New app instance and new browser session use the same actual migrated DB.
    restarted=create_app(dict(app.config))
    new_session=restarted.test_client()
    logged=mutate(new_session,'POST',OB+'/login',{'email':'restore@qa.test','password':PASSWORD})
    assert logged.status_code==200,logged.json
    assert logged.json['user']['id']==uid
    assert new_session.get(OB+'/journey').json['message']==saved.json['message']
    assert new_session.get(OB+'/state').json['status']=='completed'
    assert_empty_own_records(new_session)
    assert PASSWORD not in json.dumps(logged.json)


def test_duplicate_registration_and_guest_draft_adoption(app,client):
    register(client,'duplicate@qa.test')
    other=app.test_client()
    duplicate=mutate(other,'POST',OB+'/register',{'display_name':'Другой пациент',
        'email':'DUPLICATE@QA.TEST','password':PASSWORD,'terms_consent':True})
    assert duplicate.status_code==409
    bootstrap(other)
    guest=other.get(OB+'/journey').json
    saved=mutate(other,'PUT',OB+'/journey',{'revision':guest['revision'],'doctor_id':'doc_ther',
        'subject':'Новый черновик','message':'Guest draft adopted only by current login'})
    assert saved.status_code==200
    login=mutate(other,'POST',OB+'/login',{'email':'duplicate@qa.test','password':PASSWORD})
    assert login.status_code==200,login.json
    assert other.get(OB+'/journey').json['message']==saved.json['message']
    assert other.get('/api/v1/previsit-cases').json['items']==[]


def test_invitation_private_storage_preview_and_explicit_scoped_accept(app,client):
    doctor=actor(app)
    inv=issue(doctor,categories=['symptoms','medications'])
    payload=json.dumps(inv)
    with app.extensions['cc_session_factory']() as db:
        stored=db.execute(text('SELECT * FROM ob_invitations WHERE id=:id'),{'id':inv['id']}).mappings().one()
        assert stored['token_hash']==hashlib.sha256(inv['token'].encode()).hexdigest()
        assert stored['recipient_hash']==hashlib.sha256(b'patient@qa.test').hexdigest()
        assert inv['token'] not in json.dumps(dict(stored)) and 'patient@qa.test' not in json.dumps(dict(stored))
    listed=doctor.get(OB+'/invitations')
    assert listed.status_code==200
    assert inv['token'] not in json.dumps(listed.json)
    assert 'recipient_hash' not in json.dumps(listed.json) and 'token_hash' not in json.dumps(listed.json)
    preview=mutate(client,'POST',OB+'/invitations/preview',{'token':inv['token']})
    assert preview.status_code==200,preview.json
    assert preview.json['doctor']['id']=='doc_psy'
    assert preview.json['categories']==['symptoms','medications']
    assert 'patient@qa.test' not in json.dumps(preview.json)
    register(client,invitation_token=inv['token'])
    assert client.get('/api/v1/patients/me/links').json['items']==[]
    assert accept(client,inv,consent=False).status_code==422
    assert accept(client,inv,consent_version='unrecognized').status_code==422
    accepted=accept(client,inv)
    assert accepted.status_code==200,accepted.json
    assert accepted.json['scope']==['symptoms','medications']
    assert accepted.json['clinical_link_created'] is True
    assert [r['id'] for r in client.get('/api/v1/patients/me/links').json['items']]==['doc_psy']
    assert accept(client,inv).status_code in (404,409)
    assert mutate(doctor,'POST',OB+'/invitations/'+inv['id']+'/revoke',{}).status_code==409
    uid=client.get('/api/v1/auth/me').json['user']['id']
    with app.extensions['cc_session_factory']() as db:
        user=db.get(User,uid)
        links=list(db.scalars(select(DoctorPatientLink).where(DoctorPatientLink.patient_id==user.patient_id)))
        assert len(links)==1 and set(links[0].categories.split(','))=={'symptoms','medications'}
        ledger=db.execute(text('SELECT * FROM ob_consents WHERE invitation_id=:id'),{'id':inv['id']}).mappings().one()
        assert ledger['patient_user_id']==uid and ledger['version']=='clinical-link-v1'


@pytest.mark.parametrize('failure',['expired','revoked','wrong_recipient','cross_tenant'])
def test_invitation_negative_lifecycle_and_registration_binding(app,client,failure):
    doctor=actor(app)
    inv=issue(doctor)
    if failure=='expired':
        with app.extensions['cc_session_factory'].begin() as db:
            db.execute(text('UPDATE ob_invitations SET expires_at=:date WHERE id=:id'),{'id':inv['id'],'date':'2020-01-01T00:00:00+00:00'})
    if failure=='revoked':
        assert mutate(doctor,'POST',OB+'/invitations/'+inv['id']+'/revoke',{}).status_code==200
    if failure in ('expired','revoked'):
        denied=404
        assert mutate(client,'POST',OB+'/invitations/preview',{'token':inv['token']}).status_code==denied
        response=mutate(client,'POST',OB+'/register',{'display_name':'Новый пациент','email':'patient@qa.test',
            'password':PASSWORD,'terms_consent':True,'invitation_token':inv['token']})
        assert response.status_code==denied,response.json
        assert client.get('/api/v1/auth/me').status_code==401
        register(client)
        assert accept(client,inv).status_code==denied
    elif failure=='wrong_recipient':
        response=mutate(client,'POST',OB+'/register',{'display_name':'Другой пациент','email':'other@qa.test',
            'password':PASSWORD,'terms_consent':True,'invitation_token':inv['token']})
        assert response.status_code==403,response.json
        register(client,'other@qa.test')
        assert accept(client,inv).status_code==403
    else:
        draft=client.get(OB+'/journey').json
        assert mutate(client,'PUT',OB+'/journey',{'revision':draft['revision'],'doctor_id':'doc_other'}).status_code==200
        registered=register(client)
        assert registered['context']['organization_id']=='org_other'
        assert accept(client,inv).status_code==403
    assert client.get('/api/v1/patients/me/links').json['items']==[]


def test_invitation_and_professional_verification_role_scope_and_ttl_validation(app,client):
    register(client)
    assert mutate(client,'POST',OB+'/professional-verification',{}).status_code==403
    assert mutate(client,'POST',OB+'/invitations',{'recipient_email':'next@qa.test','categories':['symptoms'],'ttl_hours':24}).status_code==403
    doctor=actor(app)
    for payload in ({'categories':['unrestricted']},{'ttl_hours':0},{'ttl_hours':169},{'recipient_email':'real@gmail.com'},
                    {'target_role':'doctor'},{'organization_id':'org_other'}):
        result=mutate(doctor,'POST',OB+'/invitations',{'recipient_email':'next@qa.test','categories':['symptoms'],'ttl_hours':24,**payload})
        assert result.status_code==422,result.json
    verified=mutate(doctor,'POST',OB+'/professional-verification',{})
    assert verified.status_code==200,verified.json
    assert verified.json['grants_roles'] is False and verified.json['mfa_verified'] is False
    assert verified.json['scope']=='synthetic_dev'
    assert doctor.get('/api/v1/auth/me').json['context']['role']=='doctor'
    admin=actor(app,'clinic_01')
    assert mutate(admin,'POST',OB+'/professional-verification',{}).status_code==403


def test_prepared_draft_author_only_separate_sign_publish_and_withdrawal(app,client):
    doctor=actor(app)
    other_doctor=actor(app,'doc_ther')
    inv=issue(doctor)
    created=mutate(doctor,'POST',OB+'/invitations/'+inv['id']+'/drafts',{'content':'Restricted synthetic physician note'})
    assert created.status_code==201,created.json
    draft=created.json
    path=OB+'/drafts/'+draft['id']
    assert draft['state']=='draft'
    register(client,invitation_token=inv['token'])
    assert client.get(OB+'/records').json['items']==[]
    assert client.get(OB+'/drafts').status_code==403
    assert other_doctor.get(OB+'/drafts').json['items']==[]
    for who in (client,other_doctor):
        assert mutate(who,'POST',path+'/sign',{'confirmation':True,'version':draft['version']}).status_code in (403,404)
    assert mutate(doctor,'POST',path+'/sign',{'confirmation':True,'version':draft['version']}).status_code==403
    assert accept(client,inv).status_code==200
    assert client.get(OB+'/records').json['items']==[]
    assert mutate(doctor,'POST',path+'/publish',{'confirmation':True,'version':draft['version']}).status_code==409
    assert mutate(doctor,'POST',path+'/sign',{'confirmation':False,'version':draft['version']}).status_code==422
    assert mutate(doctor,'POST',path+'/sign',{'confirmation':True,'version':0}).status_code==409
    signed=mutate(doctor,'POST',path+'/sign',{'confirmation':True,'version':draft['version']})
    assert signed.status_code==200,signed.json
    assert signed.json['state']=='signed' and signed.json['version']>draft['version']
    assert client.get(OB+'/records').json['items']==[]
    assert mutate(doctor,'POST',path+'/publish',{'confirmation':False,'version':signed.json['version']}).status_code==422
    assert mutate(doctor,'POST',path+'/publish',{'confirmation':True,'version':draft['version']}).status_code==409
    published=mutate(doctor,'POST',path+'/publish',{'confirmation':True,'version':signed.json['version']})
    assert published.status_code==200,published.json
    assert published.json['state']=='published'
    records=client.get(OB+'/records').json['items']
    assert len(records)==1 and records[0]['content']==draft['content']
    stranger=app.test_client()
    register(stranger,'stranger@qa.test')
    assert stranger.get(OB+'/records').json['items']==[]
    assert other_doctor.get(OB+'/records').status_code==403
    uid=client.get('/api/v1/auth/me').json['user']['id']
    with app.extensions['cc_session_factory']() as db:
        patient_id=db.get(User,uid).patient_id
    assert doctor.get('/api/v1/doctors/me/patients/'+patient_id+'/clinical').status_code==200
    revoked=mutate(client,'DELETE','/api/v1/patients/me/clinical-links/doc_psy',{})
    assert revoked.status_code==200,revoked.json
    assert client.get(OB+'/records').json['items']==[]
    assert doctor.get('/api/v1/doctors/me/patients/'+patient_id+'/clinical').status_code==404
    assert mutate(doctor,'POST',path+'/publish',{'confirmation':True,'version':published.json['version']}).status_code in (403,409)
    with app.extensions['cc_session_factory']() as db:
        assert db.execute(text('SELECT revoked_at FROM ob_consents WHERE invitation_id=:id'),{'id':inv['id']}).scalar_one()
        assert db.execute(text('SELECT state FROM ob_prepared_drafts WHERE id=:id'),{'id':draft['id']}).scalar_one()=='published'


def test_concurrent_invitation_accept_is_single_use_sqlite_demo(app,client):
    inv=issue(actor(app))
    registered=register(client,invitation_token=inv['token'])
    second=app.test_client()
    assert mutate(second,'POST',OB+'/login',{'email':'patient@qa.test','password':PASSWORD}).status_code==200
    clients=[client,second]
    tokens=[bootstrap(c)['csrf_token'] for c in clients]
    barrier=Barrier(2)
    def redeem(index):
        barrier.wait(timeout=5)
        return clients[index].post(OB+'/invitations/accept',json={'token':inv['token'],
            'consent':True,'consent_version':'clinical-link-v1'},headers={'X-CSRF-Token':tokens[index]}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(redeem,(0,1)))
    assert results.count(200)==1 and all(code in (200,404,409) for code in results),results
    with app.extensions['cc_session_factory']() as db:
        assert db.execute(text('SELECT COUNT(*) FROM ob_consents WHERE invitation_id=:id'),{'id':inv['id']}).scalar_one()==1
        user=db.get(User,registered['user']['id'])
        assert len(list(db.scalars(select(DoctorPatientLink).where(DoctorPatientLink.patient_id==user.patient_id))))==1


def test_concurrent_invitation_accept_revoke_cannot_both_win_sqlite_demo(app,client):
    doctor=actor(app)
    inv=issue(doctor)
    register(client,invitation_token=inv['token'])
    patient_csrf=bootstrap(client)['csrf_token']
    doctor_csrf=bootstrap(doctor)['csrf_token']
    barrier=Barrier(2)
    def action(which):
        barrier.wait(timeout=5)
        if which=='accept':
            return client.post(OB+'/invitations/accept',json={'token':inv['token'],'consent':True,
                'consent_version':'clinical-link-v1'},headers={'X-CSRF-Token':patient_csrf}).status_code
        return doctor.post(OB+'/invitations/'+inv['id']+'/revoke',json={},headers={'X-CSRF-Token':doctor_csrf}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(action,('accept','revoke')))
    assert results.count(200)==1 and all(code in (200,404,409) for code in results),results
    with app.extensions['cc_session_factory']() as db:
        status=db.execute(text('SELECT status FROM ob_invitations WHERE id=:id'),{'id':inv['id']}).scalar_one()
        count=db.execute(text('SELECT COUNT(*) FROM ob_consents WHERE invitation_id=:id'),{'id':inv['id']}).scalar_one()
        assert status==('accepted' if results[0]==200 else 'revoked')
        assert count==(1 if status=='accepted' else 0)


def test_qr_modules_encode_exact_configured_invitation_link(app):
    """Compare every rendered QR module with the canonical-link encoding.

    This is QR payload equivalence, independent of SVG byte order or metadata;
    no third-party QR service or fixture bitmap stands in for the returned QR.
    """
    import base64
    import re
    from xml.etree import ElementTree
    import qrcode
    inv=issue(actor(app),'qr@qa.test')
    assert inv['absolute_url']=='https://compass.example/#'+inv['url']
    assert inv['qr_data_uri']==inv['qr_svg']
    prefix='data:image/svg+xml;base64,'
    assert inv['qr_data_uri'].startswith(prefix)
    svg=ElementTree.fromstring(base64.b64decode(inv['qr_data_uri'][len(prefix):],validate=True))
    paths=svg.findall('{http://www.w3.org/2000/svg}path')
    assert len(paths)==1
    assert not svg.findall('.//{http://www.w3.org/2000/svg}script')
    starts=re.findall(r'M([\d.]+),([\d.]+)H',paths[0].attrib['d'])
    assert starts
    rendered={(int(float(x)),int(float(y))) for x,y in starts}
    expected=qrcode.QRCode()
    expected.add_data(inv['absolute_url'])
    expected.make(fit=True)
    matrix=expected.get_matrix()
    modules={(x,y) for y,row in enumerate(matrix) for x,on in enumerate(row) if on}
    assert rendered==modules
    assert svg.attrib['viewBox']=='0 0 '+str(len(matrix))+' '+str(len(matrix))


def test_cross_tenant_guest_draft_is_not_adopted_on_login(app,client):
    register(client)
    guest=app.test_client()
    bootstrap(guest)
    draft=guest.get(OB+'/journey').json
    assert mutate(guest,'PUT',OB+'/journey',{'revision':draft['revision'],'doctor_id':'doc_other',
        'message':'Private other-clinic draft'}).status_code==200
    refused=mutate(guest,'POST',OB+'/login',{'email':'patient@qa.test','password':PASSWORD})
    assert refused.status_code==403,refused.json
    assert guest.get('/api/v1/auth/me').status_code==401
    assert guest.get(OB+'/journey').json['message']=='Private other-clinic draft'
    assert client.get(OB+'/journey').json['message']==''


def test_local_session_logout_invalidates_copied_cookie_and_expiry(app,client):
    account=register(client)
    copied=app.test_client()
    cookie=client.get_cookie('session')
    assert cookie
    copied.set_cookie('session',cookie.value)
    assert copied.get('/api/v1/auth/me').status_code==200
    assert mutate(client,'POST',OB+'/logout',{}).status_code==200
    assert copied.get('/api/v1/auth/me').status_code==401
    assert copied.get(OB+'/records').status_code==401
    login=mutate(client,'POST',OB+'/login',{'email':'patient@qa.test','password':PASSWORD})
    assert login.status_code==200
    assert client.get('/api/v1/auth/me').status_code==200
    with app.extensions['cc_session_factory'].begin() as db:
        db.execute(text('UPDATE ob_auth_sessions SET expires_at=:date WHERE user_id=:uid'),
            {'date':'2020-01-01T00:00:00Z','uid':account['user']['id']})
    assert client.get('/api/v1/auth/me').status_code==401
    forged_uid=app.test_client()
    with forged_uid.session_transaction() as session:
        session['uid']=account['user']['id']
    assert forged_uid.get('/api/v1/auth/me').status_code==401


def test_prepared_plain_note_requires_symptoms_scope(app,client):
    doctor=actor(app)
    inv=issue(doctor,categories=['medications'])
    created=mutate(doctor,'POST',OB+'/invitations/'+inv['id']+'/drafts',{'content':'Synthetic plain note outside medication-only scope'})
    assert created.status_code==201,created.json
    register(client,invitation_token=inv['token'])
    assert accept(client,inv).status_code==200
    draft=created.json
    refused=mutate(doctor,'POST',OB+'/drafts/'+draft['id']+'/sign',{'confirmation':True,'version':draft['version']})
    assert refused.status_code==403,refused.json
    assert client.get(OB+'/records').json['items']==[]


def synthetic_patient_signal_fixtures(app,user_id):
    """Persist bounded synthetic legacy records to exercise revocation joins."""
    from cc_api.models import Alert
    from cc_api.extension_models import AISummaryDraft, QuestionnaireAssignment
    with app.extensions['cc_session_factory'].begin() as db:
        patient_id=db.get(User,user_id).patient_id
        db.add(Alert(id='ob_test_alert',assigned_doctor_id='doc_psy',patient_id=patient_id,
            severity='high',status='open',created_at='2026-10-19T09:00:00Z',reason_code='synthetic_test_signal'))
        db.add(AISummaryDraft(id='ob_test_summary',patient_user_id=user_id,recipient_doctor_id='doc_psy',
            content='Synthetic fixture explicitly approved for this recipient',state='approved_for_recipient',
            created_at='2026-10-19T09:00:00Z'))
        db.add(QuestionnaireAssignment(id='ob_test_assignment',patient_id=patient_id,clinician_id='doc_psy',
            instrument_id='PHQ-9',instrument_version='synthetic-test',status='assigned'))
    return patient_id


def assert_legacy_signal_access(doctor,visible):
    for path,identifier in (('/api/v1/doctors/me/alerts','ob_test_alert'),
        ('/api/v1/doctors/me/ai-summaries','ob_test_summary'),
        ('/api/v1/instruments/assignments','ob_test_assignment')):
        response=doctor.get(path)
        assert response.status_code==200,(path,response.json)
        assert (identifier in {r['id'] for r in response.json['items']}) is visible,(path,response.json)


def test_password_login_invalidates_copied_local_identity_cookie(app,client):
    register(client)
    copied=app.test_client()
    copied.set_cookie('session',client.get_cookie('session').value)
    assert copied.get('/api/v1/auth/me').status_code==200
    switched=login_response(client,'doc_psy')
    assert switched.status_code==200,switched.json
    assert switched.json['context']['role']=='doctor'
    assert copied.get('/api/v1/auth/me').status_code==401
    assert copied.get(OB+'/records').status_code==401


def test_latest_scope_replacement_hides_signals_and_attention(app,client):
    doctor=actor(app)
    first=issue(doctor,categories=['symptoms','diagnosis','medications'])
    account=register(client,invitation_token=first['token'])
    assert accept(client,first).status_code==200
    patient_id=synthetic_patient_signal_fixtures(app,account['user']['id'])
    assert_legacy_signal_access(doctor,True)
    row=next(r for r in doctor.get('/api/v1/doctors/me/patients').json['items'] if r['id']==patient_id)
    assert row['attention_level']=='high'
    replacement=issue(doctor,categories=['medications'])
    assert accept(client,replacement).status_code==200
    assert_legacy_signal_access(doctor,False)
    row=next(r for r in doctor.get('/api/v1/doctors/me/patients').json['items'] if r['id']==patient_id)
    assert row['attention_level']=='unknown'
    assert row['attention_reason'] is None
    assert row['trend']=='insufficient_data' and row['last_activity_at'] is None
    assert 'severity_label' not in row and 'diagnosis_label' not in row
    assert mutate(doctor,'POST','/api/v1/alerts/ob_test_alert/acknowledge',{}).status_code==404


def test_clinical_link_withdrawal_hides_existing_legacy_signals(app,client):
    doctor=actor(app)
    inv=issue(doctor,categories=['symptoms','diagnosis','medications'])
    account=register(client,invitation_token=inv['token'])
    assert accept(client,inv).status_code==200
    patient_id=synthetic_patient_signal_fixtures(app,account['user']['id'])
    assert_legacy_signal_access(doctor,True)
    assert mutate(client,'DELETE','/api/v1/patients/me/clinical-links/doc_psy',{}).status_code==200
    assert_legacy_signal_access(doctor,False)
    assert patient_id not in {r['id'] for r in doctor.get('/api/v1/doctors/me/patients').json['items']}
    assert doctor.get('/api/v1/doctors/me/patients/'+patient_id+'/clinical').status_code==404
    assert mutate(doctor,'POST','/api/v1/alerts/ob_test_alert/acknowledge',{}).status_code==404


@pytest.mark.parametrize('target,issuer,recipient,wrong,extra',[
    ('doctor','clinic_01','doc_ther','doc_psy',{'categories':[]}),
    ('patient','doc_ther','pat_03','pat_01',{'categories':['symptoms'],'patient_id':'pat_c'}),
])
def test_legacy_invitation_preview_and_original_accept_remain_compatible(app,target,issuer,recipient,wrong,extra):
    sender=actor(app,issuer)
    issued=mutate(sender,'POST','/api/v1/invitations',{'target_role':target,'recipient_id':recipient,**extra})
    assert issued.status_code==201,issued.json
    token=issued.json['registration_code']
    guest=app.test_client()
    assert mutate(guest,'POST',OB+'/invitations/preview',{'token':token}).status_code==403
    outsider=actor(app,wrong)
    assert mutate(outsider,'POST',OB+'/invitations/preview',{'token':token}).status_code==403
    denied=mutate(outsider,'POST','/api/v1/invitations/accept',{'registration_code':token})
    assert denied.status_code==403,denied.json
    intended=actor(app,recipient)
    preview=mutate(intended,'POST',OB+'/invitations/preview',{'token':token})
    assert preview.status_code==200,preview.json
    issuer_name=sender.get('/api/v1/auth/me').json['user']['display_name']
    assert preview.json=={'legacy':True,'doctor':{'id':issuer,'name':issuer_name},
        'categories':extra['categories'],'organization_id':'org_demo',
        'expires_at':issued.json['expires_at'],'consent_version':'clinical-link-v1'}
    with app.extensions['cc_session_factory']() as db:
        users_before=db.execute(text('SELECT COUNT(*) FROM users')).scalar_one()
        consent_before=db.execute(text('SELECT COUNT(*) FROM ob_consents')).scalar_one()
    accepted=mutate(intended,'POST','/api/v1/invitations/accept',{'registration_code':token,**({'consent':True,'consent_version':'clinical-link-v1'} if target=='patient' else {})})
    assert accepted.status_code==200,accepted.json
    assert accepted.json['clinical_link_created'] is (target=='patient')
    assert intended.get('/api/v1/auth/me').json['context']['role']==target
    assert mutate(intended,'POST','/api/v1/invitations/accept',{'registration_code':token}).status_code==404
    with app.extensions['cc_session_factory']() as db:
        assert db.execute(text('SELECT COUNT(*) FROM users')).scalar_one()==users_before
        assert db.execute(text('SELECT COUNT(*) FROM ob_consents')).scalar_one()==consent_before+int(target=='patient')
        assert db.execute(text('SELECT COUNT(*) FROM ob_staff_verifications')).scalar_one()==0


def test_journey_merged_case_text_length_boundary_preserves_revision(client):
    draft=client.get(OB+'/journey').json
    subject='Тема'
    message='Я'*(2000-len(subject)-2)
    valid=mutate(client,'PUT',OB+'/journey',{'revision':draft['revision'],'doctor_id':'doc_ther',
        'subject':subject,'message':message})
    assert valid.status_code==200,valid.json
    assert len(valid.json['subject']+'\n\n'+valid.json['message'])==2000
    invalid=mutate(client,'PUT',OB+'/journey',{'revision':valid.json['revision'],'message':message+'Я'})
    assert invalid.status_code==422,invalid.json
    after=client.get(OB+'/journey').json
    assert after==valid.json
    assert after['revision']==valid.json['revision']
