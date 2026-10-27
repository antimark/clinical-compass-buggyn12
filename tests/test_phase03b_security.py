"""Adversarial bounded 03B gates; provider injection is synthetic unit-test only."""
import json
import time
from threading import Event
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from cc_api import create_app
from cc_api.clinical_copilot_models import CopilotThread,CopilotMessage,CopilotJob,Referral
from cc_api.clinical_copilot_services import now
from cc_api.models import User
from cc_api.onboarding_models import LocalIdentity
from cc_api.evaluation_workspace import provision_physician
from cc_api import copilot_catalog
from test_phase03b import app,doctor,consent,mutate,versions,new_thread,message,wait_job,count,create_ref,payload,B,PID,CID,list_url

@pytest.mark.parametrize('bad',['unknown_citation','missing_citation','invalid_quote','extra_tool','malformed','timeout','unavailable'])
def test_untrusted_model_output_cannot_become_answer_or_order(app,bad):
    def provider(config,messages,refs,source_text,cancelled):
        answer=dict(answer='<img src=x onerror=alert(1)>',citation_ids=[refs[0]['citation_id']],evidence_quotes=[])
        if bad=='unknown_citation':answer['citation_ids']=['javascript:alert(1)']
        elif bad=='missing_citation':answer['citation_ids']=[]
        elif bad=='invalid_quote':answer['evidence_quotes']=['PRIVATE_DIARY_NOT_IN_SOURCE']
        elif bad=='extra_tool':answer['tool_calls']=[dict(name='create_referral')]
        elif bad=='malformed':answer['answer']=None
        elif bad=='timeout':raise TimeoutError()
        else:raise ValueError('provider_unavailable')
        return answer,dict(mode='test_injected_provider',model='unit-only')
    app.extensions['copilot_provider']=provider
    c=doctor(app);thread=new_thread(c);response=message(c,thread)
    terminal=wait_job(c,response.json)
    assert terminal['status'] in ('failed','timeout')
    assert count(app,Referral)==0
    history=c.get(B+'/threads/'+thread['id']).json
    assert len(history['messages'])==1 and history['messages'][0]['role']=='user'
    assert 'PRIVATE_DIARY_NOT_IN_SOURCE' not in json.dumps(history)


def test_cancel_running_job_then_close_purges_content_and_cannot_repopulate(app):
    entered=Event();release=Event()
    def provider(config,messages,refs,source_text,cancelled):
        entered.set();assert release.wait(8)
        return dict(answer='Must not persist after cancel/purge',citation_ids=[refs[0]['citation_id']],evidence_quotes=[]),dict(mode='test',model='test')
    app.extensions['copilot_provider']=provider
    c=doctor(app);thread=new_thread(c);response=message(c,thread)
    assert entered.wait(5)
    try:
        cancel=mutate(c,'POST',B+'/jobs/'+response.json['id']+'/cancel',{'confirmed':True})
        assert cancel.status_code==200 and cancel.json['status']=='cancelled'
        latest=c.get(B+'/threads/'+thread['id']).json
        assert mutate(c,'DELETE',B+'/threads/'+thread['id'],dict(revision=latest['revision'],confirmed=False)).status_code==422
        closed=mutate(c,'DELETE',B+'/threads/'+thread['id'],dict(revision=latest['revision'],confirmed=True))
        assert closed.status_code==200 and closed.json['retention_state']=='purged'
        assert c.get(B+'/threads/'+thread['id']).status_code==410
        assert c.get(list_url('threads')).json['items']==[]
    finally:release.set()
    time.sleep(.1)
    with app.extensions['cc_session_factory']() as db:
        assert all(not x.content and x.provenance_json=='{}' for x in db.scalars(select(CopilotMessage)))


def test_job_restart_marks_interrupted_and_preserves_user_history(app):
    c=doctor(app);t=new_thread(c)
    with app.extensions['cc_session_factory'].begin() as db:
        msg=CopilotMessage(id='restart_input',thread_id=t['id'],ordinal=1,role='user',content='F41.1',provenance_json='{}',created_at=now())
        db.add(msg);db.flush()
        db.add(CopilotJob(id='interrupted_job',thread_id=t['id'],input_id=msg.id,status='running',safe_error_code='',queued_at=now(),started_at=now(),finished_at='',timings_json='{}'))
    restarted=create_app(dict(app.config))
    try:
        renewed=doctor(restarted);r=renewed.get(B+'/jobs/interrupted_job')
        assert r.status_code==200 and r.json['status']=='failed' and r.json['safe_error_code']=='worker_restarted'
        assert len(renewed.get(B+'/threads/'+t['id']).json['messages'])==1
    finally:restarted.extensions['cc_session_factory'].kw['bind'].dispose()


def test_catalog_update_during_model_and_forged_highlight_fail_closed(app,monkeypatch):
    c=doctor(app);t=new_thread(c)
    def provider(config,messages,refs,source_text,cancelled):
        monkeypatch.setattr(copilot_catalog,'revalidate',lambda refs:False)
        return dict(answer='Stale catalog answer',citation_ids=[refs[0]['citation_id']],evidence_quotes=[]),dict(mode='test',model='test')
    app.extensions['copilot_provider']=provider
    result=wait_job(c,message(c,t).json)
    assert result['status']=='failed' and result['safe_error_code']=='catalog_changed'
    assert len(c.get(B+'/threads/'+t['id']).json['messages'])==1
    ref=copilot_catalog.citation('diagnosis','F41.1')
    endpoint='/api/v1/clinical-catalog/diagnosis/F41.1/fragments/'
    assert c.get(endpoint+ref['citation_id']).json['valid'] is True
    for false_id in ('javascript:alert(1)','stale','..%2Ffake'):
        response=c.get(endpoint+false_id)
        assert response.status_code==404 or response.json['valid'] is False
    assert copilot_catalog.citation('instrument','gad7') is None


def test_manual_referral_final_transaction_recheck_rolls_back_all(app):
    c=doctor(app);data=payload(c)
    def revoke(db):consent(db).revoked_at='2020-01-01T00:00:00Z'
    app.extensions['copilot_before_commit']=revoke
    response=create_ref(c,data)
    assert response.status_code in (404,409)
    assert count(app,Referral)==0


def test_thread_idempotency_payload_collision_and_csrf(app):
    c=doctor(app);data=dict(encounter_id=CID,**versions(c),idempotency_key=str(uuid4()))
    uri=f'{B}/patients/{PID}/threads'
    first=mutate(c,'POST',uri,data);again=mutate(c,'POST',uri,data)
    assert first.status_code==201 and again.status_code==200 and first.json==again.json
    assert c.post(uri,json=data).status_code==403
    assert mutate(c,'POST',uri,{**data,'unknown_source':'fake'}).status_code==422
    assert mutate(c,'POST',uri,{**data,'source_version':'f'*64}).status_code==409
    assert doctor(app,'doc_ther').get(B+'/threads/'+first.json['id']).status_code==404


def test_evaluation_requires_isolated_explicit_environment_and_no_dev_auto_identity(tmp_path):
    with pytest.raises(RuntimeError):create_app(dict(APP_ENV='evaluation_sandbox',DEMO_MODE=True,DB_PATH=str(tmp_path/'x.sqlite'),SECRET_KEY='isolated'))
    app=create_app(dict(TESTING=True,APP_ENV='evaluation_sandbox',DEMO_MODE=True,EVALUATION_ACKNOWLEDGED=True,
        EVALUATION_TENANT='evaluation_sandbox',DB_PATH=str(tmp_path/'evaluation-owned.sqlite'),SECRET_KEY='isolated'))
    try:
        with app.extensions['cc_session_factory']() as db:assert db.scalar(select(func.count()).select_from(User))==0
        uid=provision_physician(app,'operator@evaluation.test','Disposable-operator-pass-42')
        with pytest.raises(ValueError):provision_physician(app,'operator@evaluation.test','Another-disposable-pass-42')
        with app.extensions['cc_session_factory']() as db:assert db.get(LocalIdentity,uid).email_status=='not_verified'
        client=doctor(app,uid);caps=client.get(B+'/capabilities').json
        assert caps['chat_enabled'] and caps['referrals_enabled'] and caps['environment']=='evaluation_sandbox'
        assert client.get('/api/v1/onboarding/bootstrap').json['professional_verification']=='not_verified'
        public=client.get('/api/v1/public/doctors').json['items']
        assert next(x for x in public if x['id']==uid)['verified']=='self_reported'
        assert mutate(client,'PUT','/api/v1/onboarding/journey',dict(revision=0,message='Мой телефон +7 999 123-45-67')).status_code==422
        rejected=mutate(client,'POST','/api/v1/previsit-cases',dict(doctor_id=uid,text='Мой телефон +7 999 123-45-67 и тревога',case_consent=True))
        assert rejected.status_code==422 and rejected.json['error']['code']=='IDENTIFIABLE_DATA_NOT_ALLOWED'
        assert client.post('/api/v1/dev/switch-user',json={'user_id':uid}).status_code in (403,404)
    finally:app.extensions['cc_session_factory'].kw['bind'].dispose()

def test_actual_referral_and_chat_dtos_validate_openapi(app):
    from pathlib import Path
    import yaml
    from jsonschema import Draft202012Validator
    spec=yaml.safe_load((Path(__file__).resolve().parents[1]/'contracts/openapi.yaml').read_text())
    c=doctor(app);ref=create_ref(c).json;t=new_thread(c)
    for name,value in (('ManualReferral',ref),('DoctorChatThread',t)):
        Draft202012Validator({'$ref':'#/components/schemas/'+name,'components':spec['components']}).validate(value)
    app.extensions['copilot_provider']=lambda config,messages,refs,source_text,cancelled:(dict(answer='Справка',citation_ids=[refs[0]['citation_id']],evidence_quotes=[]),dict(mode='test',model='test'))
    job=message(c,t).json;Draft202012Validator({'$ref':'#/components/schemas/DoctorChatJob','components':spec['components']}).validate(job)
    assert wait_job(c,job)['status']=='completed'
    latest=c.get(B+'/threads/'+t['id']).json
    Draft202012Validator({'$ref':'#/components/schemas/DoctorChatThread','components':spec['components']}).validate(latest)

@pytest.mark.parametrize('narrative,category',[('Тревога перед работой. Хочу обсудить Авиандр.','desired'),('Постоянная тревога. Не могу работать.','mandatory'),('Нет тревоги и нет беспокойства.',None)])
def test_unseen_evaluation_cases_use_real_source_pipeline_without_fixture_ids(tmp_path,narrative,category):
    from cc_api.onboarding_models import LocalIdentity
    from test_onboarding import register,issue,accept
    from cc_api.models import User
    from pathlib import Path
    import yaml
    from jsonschema import Draft202012Validator
    evalapp=create_app(dict(TESTING=True,APP_ENV='evaluation_sandbox',DEMO_MODE=True,EVALUATION_ACKNOWLEDGED=True,EVALUATION_TENANT='evaluation_sandbox',DB_PATH=str(tmp_path/'unseen.sqlite'),SECRET_KEY='isolated-unseen'))
    try:
        uid=provision_physician(evalapp,'unseen-doctor@evaluation.test','Disposable-evaluation-pass-42')
        dc=doctor(evalapp,uid);pc=evalapp.test_client();registered=register(pc,'new-unseen@evaluation.test')
        with evalapp.extensions['cc_session_factory']() as db:pid=db.get(User,registered['user']['id']).patient_id
        inv=issue(dc,'new-unseen@evaluation.test');assert accept(pc,inv).status_code==200
        case=mutate(pc,'POST','/api/v1/previsit-cases',dict(doctor_id=uid,text=narrative,case_consent=True));assert case.status_code==201
        r=dc.get(f'{B}/patients/{pid}/proposals?encounter_id='+case.json['id']);assert r.status_code==200,r.json
        d=r.json;spec=yaml.safe_load((Path(__file__).resolve().parents[1]/'contracts/openapi.yaml').read_text())
        Draft202012Validator({'$ref':'#/components/schemas/GovernedClinicalProposals','components':spec['components']}).validate(d)
        assert d['technical_status']=='implemented' and d['clinical_review_status']=='experimental_needs_validation'
        if category:
            proposal=next(x for x in d['proposals'] if x['type']=='referral')
            assert (proposal['category'],proposal['urgency'],proposal['critical'])==(category,'planned',False)
            for ev in d['evidence']:assert narrative[ev['start']:ev['end']]==ev['quote']
        else:assert d['proposals']==[] and d['proposal_status']=='no_relevant_proposal'
    finally:evalapp.extensions['cc_session_factory'].kw['bind'].dispose()

@pytest.mark.parametrize('answer',['Авиандр содержит аминапорил.','Назначаю Авиандр 20 мг.','Начните принимать препарат.'])
def test_observed_hallucinated_medicine_claim_or_action_is_rejected(answer):
    refs=copilot_catalog.retrieve('Авиандр','')
    assert not copilot_catalog.answer_supported(answer,refs)
    assert copilot_catalog.answer_supported('В карточке указан МНН маритупирдин. Полные показания и пригодность требуют проверки врача.',refs)

def test_catalog_retrieval_on_unseen_nonfixture_code_question():
    refs=copilot_catalog.retrieve('Напомни справочные сведения для F32','Новый случай без подготовленных идентификаторов')
    assert refs and any(r['catalog_id'].startswith('F32') for r in refs)
    assert all(r['kind']!='instrument' for r in refs)
