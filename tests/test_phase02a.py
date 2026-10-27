"""Source-scoped CI tests use real Flask/session/SQLite and the existing NLP validator."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from sqlalchemy import select, func
from cc_api import create_app
from cc_api.models import User, DoctorPatientLink, Checkin
from cc_api.extension_models import PrevisitCase, Message, Audit
from cc_api.onboarding_models import PatientConsent, PatientInvitation
from cc_nlp.providers.mock import DeterministicMockProvider
from cc_nlp.errors import ProviderUnavailable
from auth_support import login_response
from test_onboarding import mutate, register, issue, accept

CI = '/api/v1/clinical-intelligence'
PID = 'pxp_history_02'
CID = 'dx_fixture_incoming_case'
SOURCE = 'Плохо сплю. Тревожусь из-за работы.'


def path(pid=PID, cid=CID):
    return CI+'/patients/'+pid+'/snapshot?encounter_id='+cid


@pytest.fixture
def app(tmp_path):
    app = create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev',
        'SEED_PATIENT_PERSONAS':True,'SECRET_KEY':'phase02a-disposable-tests',
        'CI_API_V1':True,'CI_NLP_PROVIDER':'mock','CI_NLP_TIMEOUT':5,
        'DB_PATH':str(tmp_path/'ci.sqlite')})
    with app.extensions['cc_session_factory'].begin() as db:
        db.get(PrevisitCase,CID).intake_json=json.dumps({'text':SOURCE},ensure_ascii=False)
    yield app
    app.extensions['cc_session_factory'].kw['bind'].dispose()


def doctor(app, uid='doc_psy'):
    client=app.test_client(); login_response(client,uid); return client


def start(client, body=None, url=None):
    url=url or path()
    if body is None:
        snapshot=client.get(url)
        assert snapshot.status_code==200,snapshot.json
        body={key:snapshot.json[key] for key in ('source_revision','source_version')}
    return mutate(client,'POST',url,body)


def consent(db):
    return db.scalar(select(PatientConsent).where(PatientConsent.patient_user_id=='pxu_history_02',PatientConsent.doctor_id=='doc_psy'))


def test_metadata_get_no_extraction_mock_evidence_and_no_clinical_writes(app):
    client=doctor(app)
    class Counting(DeterministicMockProvider):
        calls=0
        def extract(self,*args):
            self.calls+=1; return super().extract(*args)
    provider=Counting(); app.extensions['ci_runtime'].provider_factory=lambda config:provider
    with app.extensions['cc_session_factory']() as db:
        counts={table.name:db.scalar(select(func.count()).select_from(table)) for table in User.metadata.sorted_tables}
    metadata=client.get(path()); assert metadata.status_code==200,metadata.json
    assert metadata.json['analysis_status']=='unavailable' and metadata.json['tags']==[]
    assert provider.calls==0
    result=start(client).json
    assert result['schema_version']=='ci-v1' and result['analysis_status']=='needs_review'
    assert result['mode']=='deterministic_mock' and result['model_version']=='lexical-fixture-baseline-v0.1'
    assert result['tags'] and result['evidence'] and result['routing']==[]
    assert result['permissions']['clinical_action_enabled'] is False
    for evidence in result['evidence']:
        assert SOURCE[evidence['start']:evidence['end']]==evidence['quote']
        assert evidence['scope']=='symptoms'
    for tag in result['tags']:
        assert tag['frequency']['numerator']==1 and tag['frequency']['denominator']==1
        assert tag['frequency']['unit']=='authorized_notes'
        assert tag['review_status']=='proposed'
    assert all(s['status']=='proposed' for s in result['draft_suggestions'])
    cached=client.get(path()).json
    assert cached['snapshot_version']==result['snapshot_version'] and provider.calls==1
    with app.extensions['cc_session_factory']() as db:
        assert counts=={table.name:db.scalar(select(func.count()).select_from(table)) for table in User.metadata.sorted_tables}


@pytest.mark.parametrize('uid',['doc_ther','doc_other','pat_02','clinic_01','researcher_01'])
def test_wrong_role_and_unlinked_no_source_leak(app,uid):
    client=doctor(app,uid)
    for method in ('GET','POST'):
        response=client.get(path()) if method=='GET' else start(client,{'source_revision':1,'source_version':'0'*64})
        assert response.status_code in (403,404)
        assert SOURCE not in response.get_data(as_text=True) and 'source_version' not in response.json


def test_anonymous_and_client_override_csrf_and_stale(app):
    assert app.test_client().get(path()).status_code in (401,403)
    client=doctor(app); meta=client.get(path()).json
    body={k:meta[k] for k in ('source_revision','source_version')}
    assert client.post(path(),json=body).status_code==403
    for key,value in [('text','arbitrary text'),('patient_ref','pat_02'),('provider','ollama'),('doctor_id','doc_other')]:
        assert start(client,{**body,key:value}).status_code in (400,422)
    assert start(client,{**body,'source_revision':body['source_revision']+1}).status_code==409
    assert start(client,{**body,'source_version':'0'*64}).status_code==409
    assert client.get(path(cid='foreign-case')).status_code==404
    assert client.get(path(pid='other-patient')).status_code==404


@pytest.mark.parametrize('change',['revoke','scope','case_withdraw','case_expire','case_consent','case_doctor','tenant','invitation','recipient'])
def test_acl_revoked_before_and_after_cache(app,change):
    client=doctor(app); assert start(client).status_code==200
    with app.extensions['cc_session_factory'].begin() as db:
        grant=consent(db); invitation=db.get(PatientInvitation,grant.invitation_id)
        case=db.get(PrevisitCase,CID)
        if change=='revoke': grant.revoked_at='2020-01-01T00:00:00Z'
        elif change=='scope': grant.categories='medications'
        elif change=='case_withdraw': case.status='withdrawn'
        elif change=='case_expire': case.allowed_until='2020-01-01T00:00:00Z'
        elif change=='case_consent': case.consent_version='unaccepted'
        elif change=='case_doctor': case.doctor_id='doc_ther'
        elif change=='tenant': db.get(User,'pxu_history_02').organization_id='foreign-org'
        elif change=='invitation': invitation.status='pending'
        elif change=='recipient': invitation.patient_user_id='pat_02'
    for response in (client.get(path()),start(client,{'source_revision':1,'source_version':'0'*64})):
        assert response.status_code==404,response.json
        assert SOURCE not in response.get_data(as_text=True)


@pytest.mark.parametrize('change',['revoke','case_expire','scope','source'])
def test_reauthorize_after_generation(app,change):
    client=doctor(app)
    class Changing(DeterministicMockProvider):
        def extract(self,*args):
            result=super().extract(*args)
            with app.extensions['cc_session_factory'].begin() as db:
                if change=='revoke': consent(db).revoked_at='2020-01-01T00:00:00Z'
                elif change=='case_expire': db.get(PrevisitCase,CID).allowed_until='2020-01-01T00:00:00Z'
                elif change=='scope': consent(db).categories='medications'
                else: db.get(PrevisitCase,CID).intake_json=json.dumps({'text':'Совершенно другой текст.'})
            return result
    app.extensions['ci_runtime'].provider_factory=lambda config:Changing()
    response=start(client)
    assert response.status_code==(409 if change=='source' else 404),response.json
    assert SOURCE not in response.get_data(as_text=True)
    if change=='source': assert client.get(path()).json['analysis_status']=='unavailable'


def test_forbidden_content_does_not_change_hash_frequency_topics(app):
    client=doctor(app); first=start(client).json
    with app.extensions['cc_session_factory'].begin() as db:
        db.add(Message(id='ci_forbidden_message',thread_type='previsit',context_id=CID,sender_id='pxu_history_02',recipient_id='doc_psy',text='Суицидальные мысли. Секретные лекарства.',created_at='2026-01-01T00:00:00Z'))
        db.add(Checkin(id='ci_private_diary',patient_id=PID,mood_score=1,comparison='worse',note='Приватный запрещённый источник: суицидальные мысли.',recorded_at='2026-01-01T00:00:00Z'))
        db.get(PrevisitCase,CID).intake_json=json.dumps({'text':SOURCE,'medications':'Запрещённые лекарства','private_diary':'Суицидальные мысли.'})
    second=client.get(path()).json
    assert first['source_version']==second['source_version']
    assert first['tags']==second['tags'] and first['evidence']==second['evidence']
    assert 'Суицидальные' not in json.dumps(second,ensure_ascii=False)


@pytest.mark.parametrize('fault',['invalid_json','bad_evidence','absent_quote','bad_schema','timeout','exception'])
def test_pipeline_failure_is_safe_and_provenance_visible(app,fault,caplog):
    class Faulty(DeterministicMockProvider):
        name='local_llm'; model_id='synthetic-fault-test'
        def extract(self,*args):
            if fault=='invalid_json': return 'invalid JSON containing '+SOURCE
            if fault=='timeout': raise ProviderUnavailable('local_transport_failure')
            if fault=='exception': raise RuntimeError(SOURCE)
            result=super().extract(*args)
            if fault=='absent_quote': result['facts'][0]['evidence']['quote']='Несуществующая дословная цитата'
            elif fault=='bad_schema': result['facts'][0]['review_status']='approved'
            else: result['facts'][0]['evidence']['start']=999
            return result
    app.extensions['ci_runtime'].provider_factory=lambda config:Faulty()
    result=start(doctor(app))
    assert result.status_code==200,result.json
    data=result.json
    assert data['analysis_status']=='needs_review' and data['permissions']['clinical_action_enabled'] is False
    assert data['error_code'] and data['mode'] in ('local_llm','deterministic_mock_fallback')
    assert data['primary_model_version']=='synthetic-fault-test'
    assert SOURCE not in caplog.text
    if data['mode']=='local_llm': assert data['tags']==[] and data['evidence']==[]


def test_real_registration_invitation_consent_case_to_scoped_snapshot(app):
    patient=app.test_client(); identity=register(patient,email='ci-new@demo.test')['user']
    client=doctor(app); inv=issue(client,'ci-new@demo.test',['symptoms'])
    assert accept(patient,inv).status_code==200
    submitted=mutate(patient,'POST','/api/v1/previsit-cases',{'doctor_id':'doc_psy','text':SOURCE,'case_consent':True})
    assert submitted.status_code==201,submitted.json
    with app.extensions['cc_session_factory']() as db: pid=db.get(User,identity['id']).patient_id
    url=path(pid,submitted.json['id']); result=start(client,url=url)
    assert result.status_code==200 and result.json['evidence']
    assert patient.get(url).status_code==403
    assert doctor(app,'doc_ther').get(url).status_code==404


def test_concurrent_start_is_bounded_and_rate_limited(app):
    first=doctor(app); second=doctor(app)
    entered=Event(); release=Event()
    class Blocking(DeterministicMockProvider):
        def extract(self,*args):
            entered.set(); assert release.wait(10); return super().extract(*args)
    app.extensions['ci_runtime'].provider_factory=lambda config:Blocking()
    body={k:first.get(path()).json[k] for k in ('source_revision','source_version')}
    with ThreadPoolExecutor(max_workers=1) as executor:
        future=executor.submit(start,first,body)
        assert entered.wait(5)
        try:
            assert second.get(path()).json['analysis_status']=='pending'
            assert start(second,body).status_code==429
        finally: release.set()
        assert future.result().status_code==200
    app.extensions['ci_runtime'].provider_factory=lambda config:DeterministicMockProvider()
    statuses=[start(first,body).status_code for _ in range(6)]
    assert 429 in statuses


def test_sources_metadata_and_missing_ledger_fail_closed(app):
    client=doctor(app)
    response=client.get(CI+'/patients/'+PID+'/sources')
    assert response.status_code==200 and CID in [s['encounter_ref'] for s in response.json['items']]
    assert SOURCE not in response.get_data(as_text=True)
    assert all(set(s)=={'encounter_ref','source_type','created_at'} for s in response.json['items'])
    with app.extensions['cc_session_factory'].begin() as db: db.delete(consent(db))
    assert client.get(path()).status_code==404
    assert client.get(CI+'/patients/'+PID+'/sources').status_code==404


@pytest.mark.parametrize('body',['','x'*4001,None,{'raw':'unsupported'}])
def test_input_length_and_type_fail_closed(app,body):
    client=doctor(app)
    with app.extensions['cc_session_factory'].begin() as db: db.get(PrevisitCase,CID).intake_json=json.dumps({'text':body})
    assert client.get(path()).status_code==422


def test_feature_disabled_and_nondemo_fail_closed(app):
    client=doctor(app)
    app.config['CI_API_V1']=False
    assert client.get(path()).status_code==404
    assert client.get(CI+'/capabilities').json['enabled'] is False
    app.config['CI_API_V1']=True; app.config['APP_ENV']='production'
    assert client.get(path()).status_code==404
    assert client.get(CI+'/capabilities').json['enabled'] is False


def test_cache_ttl_bounded_and_no_store(app):
    client=doctor(app); assert start(client).status_code==200
    runtime=app.extensions['ci_runtime']
    assert runtime.capacity==64 and runtime.ttl==300
    with runtime.lock:
        for cached in runtime.cache.values(): cached['at']-=301
    response=client.get(path())
    assert response.json['analysis_status']=='unavailable' and response.headers['Cache-Control']=='no-store'
    assert runtime.cache=={}


def test_start_body_limit_with_and_without_content_length(app):
    client=doctor(app)
    token=client.get('/api/v1/onboarding/bootstrap').json['csrf_token']
    payload=b'{"source_revision":1,"source_version":"'+b'a'*2048+b'"}'
    for overrides in ({},{'CONTENT_LENGTH':'','wsgi.input_terminated':True}):
        response=client.post(path(),data=payload,content_type='application/json',
            headers={'X-CSRF-Token':token},environ_overrides=overrides)
        assert response.status_code==413
    assert app.extensions['ci_runtime'].cache=={}
