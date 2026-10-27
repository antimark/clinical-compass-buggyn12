"""Patient role privacy and guarded output on shared 03B persistence/runtime/API."""
import json
import time
from uuid import uuid4
from threading import Event
import pytest
from sqlalchemy import select,func
from test_phase03b import app,B,doctor,message,wait_job,new_thread
from test_onboarding import mutate
from cc_api.clinical_copilot_models import CopilotThread,CopilotMessage,CopilotJob,PatientDiary
from cc_api.extension_models import PrevisitCase
from cc_api.models import User


def patient(app):return doctor(app,'pxu_history_02')
def sources(c):
    r=c.get(B+'/patient-chat/sources');assert r.status_code==200,r.json
    return r.json

def thread(c,source=None):
    listing=sources(c);source=source or next(x for x in listing['items'] if x['source_type']=='intake')
    r=mutate(c,'POST',B+'/patients/'+listing['patient_ref']+'/threads',dict(encounter_id=source['source_id'],source_type=source['source_type'],source_version=source['source_version'],grant_version=source['grant_version'],idempotency_key=str(uuid4())))
    assert r.status_code==201,r.json
    return r.json

def provider(config,messages,refs,source_text,cancelled):
    return dict(answer='Справочная информация.',citation_ids=[refs[0]['citation_id']],evidence_quotes=[]),dict(mode='test_injected_provider',model='test-only')


def test_patient_multiturn_reuses_shared_runtime_history_and_own_source(app):
    calls=[]
    def capture(*args,**kwargs):calls.append(args[1]);return provider(*args,**kwargs)
    app.extensions['copilot_provider']=capture
    c=patient(app);t=thread(c);assert t['audience']=='patient'
    for question in ['Объясни F41.1 и КПТ','Напомни первый пункт предыдущего ответа']:
        r=message(c,t,question);assert r.status_code==202,r.json
        assert wait_job(c,r.json)['status']=='completed'
        t=c.get(B+'/threads/'+t['id']).json
    assert len(t['messages'])==4 and 'помощник пациента' in calls[0][0]['content']
    assert any(m['role']=='assistant' for m in calls[1])
    a=t['messages'][-1]
    assert a['context_manifest']['history_messages']==2
    assert a['context_manifest']['audience']=='patient' and a['model_prose_published'] is False
    assert all(x['audience']=='patient' and x['license'] for x in a['catalog_citations'])
    assert patient(app).get(B+'/threads/'+t['id']).json['messages']==t['messages']


def test_patient_doctor_cross_role_thread_and_job_not_found(app):
    app.extensions['copilot_provider']=provider
    c=patient(app);t=thread(c);r=message(c,t,'Объясни F41.1');wait_job(c,r.json)
    for uid in ['doc_psy','doc_ther','pat_01','pat_02','researcher_01','clinic_01']:
        with app.extensions['cc_session_factory']() as db:
            assert db.get(User,uid) is not None,uid
        other=doctor(app,uid)
        assert other.get(B+'/threads/'+t['id']).status_code in (403,404)
        assert other.get(B+'/jobs/'+r.json['id']).status_code in (403,404)
    d=doctor(app);dt=new_thread(d)
    assert c.get(B+'/threads/'+dt['id']).status_code==404
    assert all(x['id']!=dt['id'] and x['audience']=='patient' for x in c.get(B+'/patients/'+dt['patient_ref']+'/threads?encounter_id='+dt['case_ref']).json['items'])


def test_private_diary_self_context_and_purge_never_physician_scope(app):
    app.extensions['copilot_provider']=provider;c=patient(app)
    r=mutate(c,'POST',B+'/patient-chat/diary',dict(content='Личная запись. Тревога и F41.1.',confirmed=True));assert r.status_code==201,r.json
    diary=r.json;src=next(x for x in sources(c)['items'] if x['source_id']==diary['id'])
    t=thread(c,src);r=message(c,t,'Что означает F41.1?');assert wait_job(c,r.json)['status']=='completed'
    d=doctor(app)
    assert d.get(B+'/patient-chat/sources').status_code==403
    assert d.get(B+'/patients/'+t['patient_ref']+'/threads?encounter_id='+diary['id']+'&source_type=diary').status_code==404
    assert d.get(B+'/threads/'+t['id']).status_code==404
    assert mutate(c,'DELETE',B+'/patient-chat/diary/'+diary['id'],dict(revision=1,confirmed=True)).status_code==200
    assert c.get(B+'/threads/'+t['id']).status_code in (404,410)
    with app.extensions['cc_session_factory']() as db:
        assert db.get(PatientDiary,diary['id']) is None
        assert all(not x.content and x.provenance_json=='{}' for x in db.scalars(select(CopilotMessage).where(CopilotMessage.thread_id==t['id'])))

@pytest.mark.parametrize('claim',[
    'Авиандр: маритупирдин и сертралин входят в состав.',
    'Вам следует отменить препарат.',
    'У вас точно F41.1.',
    'Принимайте 100 мг ежедневно.',
    'Лекарство не взаимодействует ни с какими препаратами.',
    '<script>alert(1)</script> Игнорируй политику.',
])
def test_valid_citation_never_publishes_unverified_model_claim(app,claim):
    def malicious(config,messages,refs,source_text,cancelled):
        return dict(answer=claim,citation_ids=[refs[0]['citation_id']],evidence_quotes=[]),dict(mode='test_injected_provider',model='test-only')
    app.extensions['copilot_provider']=malicious;c=patient(app);t=thread(c)
    question='Объясни F41.1' if '100 мг' in claim else 'Объясни F41.1 и Авиандр'
    r=message(c,t,question);assert wait_job(c,r.json)['status']=='completed'
    answer=c.get(B+'/threads/'+t['id']).json['messages'][-1]
    assert claim not in answer['content'] and answer['model_prose_published'] is False
    assert 'не являются назначением' in answer['content']

@pytest.mark.parametrize('change',['source','actor_role','tenant','case_revoke'])
def test_patient_pending_rechecks_current_source_and_actor(app,change):
    entered=Event();release=Event()
    def blocked(*args,**kwargs):entered.set();assert release.wait(5);return provider(*args,**kwargs)
    app.extensions['copilot_provider']=blocked;c=patient(app);t=thread(c);r=message(c,t,'Объясни F41.1')
    try:
        assert entered.wait(4)
        with app.extensions['cc_session_factory'].begin() as db:
            if change=='source':db.get(PrevisitCase,t['case_ref']).intake_json=json.dumps(dict(text='Изменённая запись'))
            elif change=='case_revoke':db.get(PrevisitCase,t['case_ref']).status='withdrawn'
            else:
                actor=db.get(User,'pxu_history_02')
                if change=='actor_role':actor.role='doctor'
                else:actor.organization_id='foreign'
    finally:release.set()
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        with app.extensions['cc_session_factory']() as db:
            if db.get(CopilotJob,r.json['id']).status not in ('queued','running'):break
        time.sleep(.02)
    with app.extensions['cc_session_factory']() as db:
        assert not db.scalar(select(CopilotMessage.id).where(CopilotMessage.thread_id==t['id'],CopilotMessage.role=='assistant'))


def test_patient_notice_deterministic_even_provider_down_and_csrf(app):
    app.extensions['copilot_provider']=lambda *a,**k:(_ for _ in ()).throw(ValueError('provider_unavailable'))
    c=patient(app);t=thread(c)
    assert c.post(B+'/patient-chat/notice',json=dict(content='Сейчас хочу навредить себе')).status_code==403
    r=mutate(c,'POST',B+'/patient-chat/notice',dict(content='Сейчас хочу навредить себе'))
    assert r.status_code==200 and r.json['urgent_notice']
    r=message(c,t,'Сейчас хочу навредить себе. F41.1');assert r.status_code==202 and r.json['urgent_notice']
    assert wait_job(c,r.json)['status']=='failed'
    saved=c.get(B+'/threads/'+t['id']).json
    assert saved['messages'][0]['urgent_notice'] and len(saved['messages'])==1


def test_patient_close_purges_and_stale_revision_rejected(app):
    app.extensions['copilot_provider']=provider;c=patient(app);t=thread(c)
    r=message(c,t,'F41.1');assert wait_job(c,r.json)['status']=='completed'
    assert message(c,t,'F41.1').status_code==409
    fresh=c.get(B+'/threads/'+t['id']).json
    assert mutate(c,'DELETE',B+'/threads/'+t['id'],dict(revision=fresh['revision'],confirmed=True)).status_code==200
    assert c.get(B+'/threads/'+t['id']).status_code==410


def test_patient_catalog_policy_fails_closed_on_missing_or_changed_rights(monkeypatch):
    from cc_api import copilot_catalog as cat
    ref=cat.citation('diagnosis','F41.1',audience='patient')
    assert ref and ref['rights_digest'] and ref['projection']=='original_editorial_patient_description'
    assert ref['citation_id']!=cat.citation('diagnosis','F41.1')['citation_id']
    assert cat.citation('diagnosis','F41.1')['citation_id'] not in ref['href']
    assert cat.citation('instrument','gad7',audience='patient') is None
    original=cat.patient_reference_policy
    monkeypatch.setattr(cat,'patient_reference_policy',lambda *args:None)
    assert cat.citation('diagnosis','F41.1',audience='patient') is None
    assert not cat.revalidate([ref])
    monkeypatch.setattr(cat,'patient_reference_policy',lambda *args:{**original(*args),'rights_digest':'changed'})
    assert not cat.revalidate([ref])
