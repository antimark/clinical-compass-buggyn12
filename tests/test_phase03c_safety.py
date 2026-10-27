"""Independent deterministic signal/outbox/receiver/ACK technical gates."""
import json,time
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select,func
from cc_api import create_app
from cc_api.models import User
from cc_api.extension_models import PrevisitCase,Audit
from cc_api.safety_models import SafetyDetection,SafetyOutbox,SafetyInbox,SafetyAttempt
from cc_api.safety_rules import evaluate,urgent_notice
from cc_api.safety_service import ingest
from test_phase03b import PID
from test_phase02a import doctor
from test_onboarding import mutate
from auth_support import login_response
B='/api/v1/safety-signals'

@pytest.fixture
def app(tmp_path):
    app=create_app(dict(TESTING=True,DEMO_MODE=True,APP_ENV='synthetic_dev',SEED_PATIENT_PERSONAS=True,SECRET_KEY='03c-safety-tests',DB_PATH=str(tmp_path/'safety.sqlite'),CI_SAFETY_V1=True))
    yield app
    app.extensions['safety_runtime'].close()
    app.extensions['cc_session_factory'].kw['bind'].dispose()

def patient(app):
    c=app.test_client();assert login_response(c,'pxu_history_02').status_code==200
    return c

def source(app,text='Сейчас хочу навредить себе.'):
    c=patient(app)
    r=mutate(c,'POST','/api/v1/previsit-cases',dict(doctor_id='doc_psy',text=text,symptoms=[],conditions=[],case_consent=True))
    assert r.status_code==201,r.json
    return r.json['id']

def scalar(app,model):
    with app.extensions['cc_session_factory']() as db:return db.scalar(select(func.count()).select_from(model))

def signal(app):
    c=doctor(app);r=c.get(B);assert r.status_code==200,r.json
    return c,r.json['items'][0]

def test_saved_source_delivery_seen_ack_and_distinct_states(app):
    source(app);assert scalar(app,SafetyDetection)==1 and scalar(app,SafetyOutbox)==1
    c,s=signal(app);assert s['critical'] and s['workflow_status']=='unseen' and s['transport']['status']=='queued'
    assert app.extensions['safety_runtime'].run_once()
    saved=c.get(B+'/'+s['id']).json
    inbox=c.get('/api/v1/safety-inbox').json['items'];assert len(inbox)==1
    assert inbox[0]['receipt']==saved['transport']['receipt']
    assert set(inbox[0]['envelope'])=={'event_ref','version','created_at','deep_link'}
    assert 'навредить' not in json.dumps(inbox,ensure_ascii=False)
    assert saved['workflow_status']=='unseen'
    seen=mutate(c,'POST',B+'/'+s['id']+'/seen',{'revision':1});assert seen.status_code==200
    assert seen.json['workflow_status']=='seen' and seen.json['revision']==2
    body=dict(revision=2,confirmed=True,idempotency_key=str(uuid4()))
    assert c.post(B+'/'+s['id']+'/ack',json=body).status_code==403
    ack=mutate(c,'POST',B+'/'+s['id']+'/ack',body);assert ack.status_code==200,ack.json
    assert ack.json['workflow_status']=='acknowledged' and ack.json['revision']==3
    assert mutate(c,'POST',B+'/'+s['id']+'/ack',body).json==ack.json
    assert mutate(c,'POST',B+'/'+s['id']+'/ack',{**body,'idempotency_key':str(uuid4())}).status_code==409
    assert c.get(B+'/'+s['id']).json==ack.json
    with app.extensions['cc_session_factory']() as db:
        assert db.scalar(select(Audit.id).where(Audit.action=='safety_acknowledged'))
    assert doctor(app,'doc_ther').get(B+'/'+s['id']).status_code==404
    assert patient(app).get(B).status_code==403
    assert c.get('/api/v1/doctor-experience/signals/'+s['id']).status_code==404

@pytest.mark.parametrize('text',['Не хочу навредить себе.','Вчера сейчас хочу навредить себе.','Друг сказал: сейчас хочу навредить себе.','Если сейчас хочу навредить себе.','Сон обычный.','«Сейчас хочу навредить себе»','Нет мыслей. Сейчас хочу навредить себе.','Неправда, что сейчас хочу навредить себе.','Я не говорю, что сейчас хочу навредить себе.','Пациент сообщил: сейчас хочу навредить себе.'])
def test_negative_ambiguous_never_critical(app,text):
    source(app,text);assert scalar(app,SafetyOutbox)==0
    assert evaluate(text)==[]

def test_noncritical_dedupe_atomic_and_rollback(app):
    cid=source(app,'Тревога мешает работать.');_,s=signal(app)
    assert s['severity']=='concern' and not s['critical']
    assert s['rule']['referral_obligation']=='not_assessed' and s['rule']['urgency']=='not_assessed'
    with app.extensions['cc_session_factory'].begin() as db:ingest(app,db,db.get(PrevisitCase,cid))
    assert scalar(app,SafetyDetection)==1 and scalar(app,SafetyOutbox)==1
    with pytest.raises(RuntimeError):
        with app.extensions['cc_session_factory'].begin() as db:
            case=db.get(PrevisitCase,cid);case.intake_json=json.dumps({'text':'Сейчас хочу навредить себе.'});ingest(app,db,case)
            raise RuntimeError('rollback')
    assert scalar(app,SafetyDetection)==1

def test_revoke_before_receive_and_read_does_not_leak_counts(app):
    source(app);c,s=signal(app)
    from test_phase02a import consent
    with app.extensions['cc_session_factory'].begin() as db:consent(db).revoked_at='2026-10-26T00:00:00+00:00'
    assert app.extensions['safety_runtime'].run_once()
    assert scalar(app,SafetyInbox)==0
    assert c.get(B+'/'+s['id']).status_code==404
    assert c.get(B).json['items']==[] and c.get('/api/v1/safety-inbox').json['items']==[]

def test_source_edit_before_send_invalidates(app):
    cid=source(app);c,s=signal(app)
    with app.extensions['cc_session_factory'].begin() as db:db.get(PrevisitCase,cid).intake_json=json.dumps({'text':'Новый текст.'})
    app.extensions['safety_runtime'].run_once()
    assert scalar(app,SafetyInbox)==0 and c.get(B+'/'+s['id']).status_code==404

def test_crash_after_receive_restart_at_least_once_idempotent_receiver(app):
    source(app);runtime=app.extensions['safety_runtime']
    def crash(_):raise SystemExit('crash-after-receipt')
    app.extensions['safety_after_receive']=crash
    with pytest.raises(SystemExit):runtime.run_once(at=time.time())
    assert scalar(app,SafetyInbox)==1
    del app.extensions['safety_after_receive']
    from cc_api.safety_worker import SafetyRuntime
    restarted=SafetyRuntime(app,app.extensions['cc_session_factory']);assert restarted.run_once(at=time.time()+31)
    _,s=signal(app);assert s['transport']['status']=='delivered' and s['transport']['attempts']==2
    assert scalar(app,SafetyInbox)==1 and scalar(app,SafetyAttempt)==2

def test_retry_deadletter_and_two_workers(app):
    source(app);runtime=app.extensions['safety_runtime'];base=time.time()
    def fail(_):raise OSError('transport unavailable')
    app.extensions['safety_before_receive']=fail
    for n in range(5):assert runtime.run_once(at=base+n*100)
    _,s=signal(app);assert s['transport']['status']=='dead_letter' and s['transport']['attempts']==5
    del app.extensions['safety_before_receive'];source(app,'Тревога мешает работать.')
    from cc_api.safety_worker import SafetyRuntime
    other=SafetyRuntime(app,app.extensions['cc_session_factory'])
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda r:r.run_once(),[runtime,other]))
    assert scalar(app,SafetyInbox)==1

def test_patient_notice_independent_broader_than_classifier():
    for text in ['Я хочу умереть.','Не хочу спать, сейчас хочу навредить себе.','Убью себя.']:
        assert urgent_notice(text)['code']=='seek_human_help'
    assert urgent_notice('Просто вопрос о каталоге') is None

def test_actual_safety_dtos_validate_current_contract(app):
    import yaml
    from pathlib import Path
    from jsonschema import Draft202012Validator
    spec=yaml.safe_load(Path('contracts/openapi.yaml').read_text())
    source(app);app.extensions['safety_runtime'].run_once();c,s=signal(app)
    for name,value in [('SafetySignal',s),('SafetySignalList',c.get(B).json),('SafetyInboxList',c.get('/api/v1/safety-inbox').json)]:
        document={**spec,'$ref':'#/components/schemas/'+name}
        Draft202012Validator(document).validate(value)

def test_missing_grant_keeps_source_without_recipient_or_outbox(app):
    from test_phase02a import consent
    with app.extensions['cc_session_factory'].begin() as db:consent(db).revoked_at='2026-10-26T00:00:00+00:00'
    cid=source(app)
    with app.extensions['cc_session_factory']() as db:
        assert db.get(PrevisitCase,cid)
        row=db.scalar(select(SafetyDetection));assert row.status=='no_authorized_recipient' and row.signal_id is None
    assert scalar(app,SafetyOutbox)==0

def test_revoke_during_send_and_after_delivered_keeps_envelope_opaque(app):
    from test_phase02a import consent
    source(app);c,s=signal(app)
    def revoke(_):
        with app.extensions['cc_session_factory'].begin() as db:consent(db).revoked_at='2026-10-26T00:00:00+00:00'
    app.extensions['safety_after_receive']=revoke
    app.extensions['safety_runtime'].run_once()
    assert scalar(app,SafetyInbox)==1
    assert c.get('/api/v1/safety-inbox').json['items']==[]
    assert mutate(c,'POST',B+'/'+s['id']+'/ack',dict(revision=1,confirmed=True,idempotency_key=str(uuid4()))).status_code==404

def test_expired_case_and_role_tenant_denied_before_evidence(app):
    cid=source(app);c,s=signal(app)
    for uid in ['researcher_01','clinic_01','pat_02']:
        with app.extensions['cc_session_factory']() as db:exists=db.get(User,uid)
        assert exists
        assert doctor(app,uid).get(B+'/'+s['id']).status_code in (403,404)
    with app.extensions['cc_session_factory'].begin() as db:db.get(PrevisitCase,cid).allowed_until='2000-01-01T00:00:00+00:00'
    assert c.get(B+'/'+s['id']).status_code==404 and c.get(B).json['items']==[]
