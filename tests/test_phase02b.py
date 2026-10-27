"""Durable physician review and explicit native-draft transfer, real Flask + SQLite."""
import json
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import select, func
from cc_api import create_app
from cc_api.models import User
from cc_api.extension_models import PrevisitCase, Audit
from cc_api.clinical_workflow_models import ClinicalDocument, ClinicalDocumentRevision, MedicationOrder
from test_phase02a import CI, PID, CID, SOURCE, path, doctor, start, consent
from test_onboarding import mutate

CW='/api/v1/clinical-workflow'

@pytest.fixture
def app(tmp_path):
    app=create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev',
        'SEED_PATIENT_PERSONAS':True,'SECRET_KEY':'disposable-review-test',
        'CI_API_V1':True,'CI_REVIEW_V1':True,'CI_NLP_PROVIDER':'mock',
        'DB_PATH':str(tmp_path/'review.sqlite')})
    with app.extensions['cc_session_factory'].begin() as db:
        db.get(PrevisitCase,CID).intake_json=json.dumps({'text':SOURCE},ensure_ascii=False)
    yield app
    app.extensions['cc_session_factory'].kw['bind'].dispose()

def reviews(client):return client.get(CI+'/patients/'+PID+'/reviews?encounter_id='+CID)
def review_path(sid):return CI+'/suggestions/'+sid+'/reviews'
def extract(app,client=None):
    client=client or doctor(app)
    response=start(client);assert response.status_code==200,response.json
    tag=response.json['tags'][0];assert tag['suggestion_id']
    return client,response.json,tag['suggestion_id']
def payload(snapshot,**extra):
    return dict(review_revision=0,source_version=snapshot['source_version'],correctness='supported',
        relevance='relevant',correction='',note='',idempotency_key=str(uuid4()),**extra)
def save(client,sid,data):return mutate(client,'POST',review_path(sid),data)
def counts(app):
    with app.extensions['cc_session_factory']() as db:
        return {t.name:db.scalar(select(func.count()).select_from(t)) for t in User.metadata.sorted_tables
            if t.name.startswith('ci_') or t.name in ('cc_audit','cd_document_revisions','cd_medication_orders')}
def native(client,kind='encounter'):
    response=mutate(client,'POST',CW+'/patients/'+PID+'/documents',{'kind':kind,'mode':'quick',
        'content':{'narrative':'Существующая синтетическая запись'} if kind=='encounter' else {'items':[{'item_type':'behavioral','title':'Синтетическая контрольная запись'}]}})
    assert response.status_code==201,response.json
    return response.json

def transfer(client,doc,sid,snapshot,**extra):
    transfer=dict(suggestion_id=sid,review_revision=1,source_version=snapshot['source_version'],
        target_field='narrative',text='Проверенный и отредактированный врачом текст.',idempotency_key=str(uuid4()))
    transfer.update(extra)
    return mutate(client,'PUT',CW+'/documents/'+doc['id'],dict(revision=doc['revision'],mode=doc['mode'],content=doc['content'],ci_transfer=transfer))

def test_durable_claim_anchors_no_raw_quote_and_stable_identity(app):
    client,snap,sid=extract(app)
    listed=reviews(client);assert listed.status_code==200,listed.json
    item=next(x for x in listed.json['items'] if x['suggestion_id']==sid)
    assert item['source_version']==snap['source_version'] and item['source_revision']==snap['source_revision']
    assert item['evidence'] and item['model_version']==snap['model_version'] and item['mode']=='deterministic_mock'
    for evidence in item['evidence']:assert SOURCE[evidence['start']:evidence['end']]==evidence['quote']
    app.extensions['ci_runtime'].cache.clear()
    second=start(client);assert second.status_code==200
    assert {x['suggestion_id'] for x in second.json['tags']}=={x['suggestion_id'] for x in snap['tags']}
    with app.extensions['cc_session_factory']() as db:
        for table in User.metadata.sorted_tables:
            if table.name.startswith('ci_'):
                assert SOURCE not in str(db.execute(select(table)).all())

def test_independent_dimensions_version_history_idempotency_and_restart(app):
    client,snap,sid=extract(app);body=payload(snap)
    first=save(client,sid,body);assert first.status_code==200,first.json
    assert first.json['review']['revision']==1
    before=counts(app);retry=save(client,sid,body)
    assert retry.status_code==200 and retry.json==first.json and counts(app)==before
    assert save(client,sid,{**body,'relevance':'not_relevant'}).status_code==409
    second=save(client,sid,{**body,'review_revision':1,'relevance':'not_relevant','idempotency_key':str(uuid4())})
    assert second.status_code==200,second.json
    assert second.json['review']['correctness']=='supported' and second.json['review']['relevance']=='not_relevant'
    assert len(second.json['history'])==2
    app.extensions['ci_runtime'].cache.clear()
    restarted=create_app(dict(app.config))
    try:
        renewed=doctor(restarted);items=reviews(renewed).json['items']
        current=next(i for i in items if i['suggestion_id']==sid)
        assert current['review']==second.json['review'] and len(current['history'])==2
        assert current['evidence'] and restarted.extensions['ci_runtime'].cache=={}
    finally:restarted.extensions['cc_session_factory'].kw['bind'].dispose()

@pytest.mark.parametrize('uid',['doc_ther','doc_other','pat_02','clinic_01','researcher_01','platform_01'])
def test_role_tenant_and_physician_private_review_fences(app,uid):
    client,snap,sid=extract(app);assert save(client,sid,{**payload(snap),'note':'PRIVATE_REVIEW_CANARY'}).status_code==200
    other=doctor(app,uid);before=counts(app)
    for response in (reviews(other),save(other,sid,payload(snap))):
        assert response.status_code in (403,404)
        assert 'PRIVATE_REVIEW_CANARY' not in response.get_data(as_text=True) and SOURCE not in response.get_data(as_text=True)
    assert counts(app)==before

@pytest.mark.parametrize('change',['revoke','scope','expiry','source','grant','tenant','case_doctor'])
def test_review_read_and_write_revalidate_durable_source(app,change):
    client,snap,sid=extract(app);assert save(client,sid,payload(snap)).status_code==200
    before=counts(app)
    with app.extensions['cc_session_factory'].begin() as db:
        if change=='revoke':consent(db).revoked_at='2020-01-01T00:00:00Z'
        elif change=='scope':consent(db).categories='medications'
        elif change=='expiry':db.get(PrevisitCase,CID).allowed_until='2020-01-01T00:00:00Z'
        elif change=='source':db.get(PrevisitCase,CID).intake_json=json.dumps({'text':'Другой текст.'})
        elif change=='grant':consent(db).accepted_at='2025-01-01T00:00:00Z'
        elif change=='tenant':db.get(User,'doc_psy').organization_id='foreign_org'
        else:db.get(PrevisitCase,CID).doctor_id='doc_ther'
    read=reviews(client)
    if change in ('source','grant'):
        assert read.status_code==200 and read.json['items']==[],read.json
    else:assert read.status_code==404,read.json
    response=save(client,sid,{**payload(snap),'review_revision':1})
    assert response.status_code==(409 if change in ('source','grant') else 404),response.json
    assert SOURCE not in read.get_data(as_text=True) and SOURCE not in response.get_data(as_text=True)
    assert counts(app)==before

def test_review_race_revocation_between_check_and_write_no_mutation(app):
    client,snap,sid=extract(app);before=counts(app)
    def revoke():
        with app.extensions['cc_session_factory'].begin() as db:consent(db).revoked_at='2020-01-01T00:00:00Z'
    app.extensions['ci_review_before_write']=revoke
    response=save(client,sid,payload(snap))
    assert response.status_code==404,response.json
    assert counts(app)==before

def test_review_cas_concurrent_one_success_one_conflict(app):
    _,snap,sid=extract(app);clients=[doctor(app),doctor(app)];barrier=Barrier(2)
    def run(client):barrier.wait();return save(client,sid,payload(snap)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(run,clients))
    assert sorted(outcomes)==[200,409]
    item=next(i for i in reviews(clients[0]).json['items'] if i['suggestion_id']==sid)
    assert item['review']['revision']==1 and len(item['history'])==1

@pytest.mark.parametrize('override',[{'correctness':'diagnosed'},{'relevance':'urgent'},{'review_revision':True},
    {'review_revision':-1},{'source_version':'0'*64},{'idempotency_key':'bad'},
    {'correctness':'needs_correction','correction':''},{'quote':'fake evidence'},
    {'evidence':[{'start':0,'end':10,'quote':'injected'}]},{'note':'x'*4001}])
def test_validation_client_evidence_and_stale_input_no_write(app,override):
    client,snap,sid=extract(app);before=counts(app)
    response=save(client,sid,{**payload(snap),**override})
    assert response.status_code in (409,422),response.json
    assert counts(app)==before

def test_csrf_anonymous_feature_flag_and_body_bound(app):
    client,snap,sid=extract(app);before=counts(app)
    assert client.post(review_path(sid),json=payload(snap)).status_code==403
    assert app.test_client().get(CI+'/patients/'+PID+'/reviews?encounter_id='+CID).status_code in (401,403)
    assert save(client,'fabricated-server-claim',payload(snap)).status_code==404
    token=client.get('/api/v1/onboarding/bootstrap').json['csrf_token']
    assert client.post(review_path(sid),data=b'x'*20000,content_type='application/json',headers={'X-CSRF-Token':token}).status_code==413
    app.config['CI_REVIEW_V1']=False
    assert reviews(client).status_code==404 and save(client,sid,payload(snap)).status_code==404
    assert counts(app)==before

def test_native_transfer_appends_after_review_and_readback_no_clinical_transition(app):
    client,snap,sid=extract(app);doc=native(client)
    with app.extensions['cc_session_factory']() as db: prior_orders=db.scalar(select(func.count()).select_from(MedicationOrder))
    assert transfer(client,doc,sid,snap).status_code==409
    saved=save(client,sid,payload(snap));assert saved.status_code==200
    response=transfer(client,doc,sid,snap);assert response.status_code==200,response.json
    committed=client.get(CW+'/documents/'+doc['id']).json
    assert committed['revision']==doc['revision']+1 and committed['status']=='draft'
    assert committed['content']['narrative'].startswith(doc['content']['narrative'])
    assert committed['content']['narrative'].endswith('Проверенный и отредактированный врачом текст.')
    assert committed['signed_at'] is None and committed['published_at'] is None
    assert response.json['ci_transfer']['status']=='native_draft_saved'
    with app.extensions['cc_session_factory']() as db:
        assert db.scalar(select(func.count()).select_from(MedicationOrder))==prior_orders
        assert db.get(ClinicalDocument,doc['id']).revision==committed['revision']
    assert doctor(app,'pat_02').get(CW+'/documents/'+doc['id']).status_code==404

def test_transfer_idempotency_conflict_hidden_overwrite_and_signed_fence(app):
    client,snap,sid=extract(app);assert save(client,sid,payload(snap)).status_code==200
    doc=native(client);key=str(uuid4());first=transfer(client,doc,sid,snap,idempotency_key=key)
    assert first.status_code==200,first.json
    before=counts(app);again=transfer(client,doc,sid,snap,idempotency_key=key)
    assert again.status_code==200 and again.json==first.json and counts(app)==before
    assert transfer(client,doc,sid,snap,idempotency_key=key,text='changed').status_code==409
    assert transfer(client,doc,sid,snap).status_code==409
    current=client.get(CW+'/documents/'+doc['id']).json
    forged={**current,'content':{'narrative':'Hidden replacement'}}
    assert transfer(client,forged,sid,snap).status_code==409
    signed=mutate(client,'POST',CW+'/documents/'+doc['id']+'/sign',{'revision':current['revision']})
    assert signed.status_code==200,signed.json
    assert transfer(client,signed.json,sid,snap).status_code==409

@pytest.mark.parametrize('target',['diagnoses','items','medications','routing','signed_at'])
def test_transfer_only_permitted_native_text_fields(app,target):
    client,snap,sid=extract(app);assert save(client,sid,payload(snap)).status_code==200
    doc=native(client);before=counts(app)
    assert transfer(client,doc,sid,snap,target_field=target).status_code==422
    assert counts(app)==before
    assert client.get(CW+'/documents/'+doc['id']).json['content']==doc['content']

def test_transfer_revocation_race_no_document_or_audit_changes(app):
    client,snap,sid=extract(app);assert save(client,sid,payload(snap)).status_code==200
    doc=native(client);before=counts(app)
    def revoke():
        with app.extensions['cc_session_factory'].begin() as db:consent(db).revoked_at='2020-01-01T00:00:00Z'
    app.extensions['ci_review_before_write']=revoke
    assert transfer(client,doc,sid,snap).status_code==404
    assert counts(app)==before
    with app.extensions['cc_session_factory']() as db:
        row=db.get(ClinicalDocument,doc['id']);assert row.revision==doc['revision'] and json.loads(row.content_json)==doc['content']

def test_correction_does_not_replace_original_and_transfer_requires_verified_correctness(app):
    client,snap,sid=extract(app);doc=native(client)
    first=save(client,sid,{**payload(snap),'correctness':'unsupported','relevance':'relevant'})
    assert first.status_code==200,first.json
    assert transfer(client,doc,sid,snap).status_code==422
    correction='Синтетическое врачебное уточнение.'
    second=save(client,sid,{**payload(snap),'review_revision':1,'correctness':'needs_correction','relevance':'low_priority','correction':correction})
    assert second.status_code==200,second.json
    assert second.json['review']['correction']==correction
    assert second.json['evidence']==first.json['evidence']
    response=transfer(client,doc,sid,snap,review_revision=2,text=correction)
    assert response.status_code==200,response.json
    with app.extensions['cc_session_factory']() as db:
        assert json.loads(db.get(PrevisitCase,CID).intake_json)['text']==SOURCE
    assert client.get(CW+'/documents/'+doc['id']).json['content']['narrative'].endswith(correction)

def test_final_transaction_acl_recheck_rolls_back_review_and_transfer(app):
    client,snap,sid=extract(app);before=counts(app)
    def revoke_in_transaction(db):consent(db).revoked_at='2020-01-01T00:00:00Z';db.flush()
    app.extensions['ci_review_before_commit']=revoke_in_transaction
    assert save(client,sid,payload(snap)).status_code==404
    assert counts(app)==before
    with app.extensions['cc_session_factory']() as db:assert consent(db).revoked_at is None
    app.extensions.pop('ci_review_before_commit')
    assert save(client,sid,payload(snap)).status_code==200
    doc=native(client);before=counts(app)
    app.extensions['ci_review_before_commit']=revoke_in_transaction
    assert transfer(client,doc,sid,snap).status_code==404
    assert counts(app)==before
    with app.extensions['cc_session_factory']() as db:
        assert consent(db).revoked_at is None
        assert db.get(ClinicalDocument,doc['id']).revision==doc['revision']

def test_physician_b_independent_authorized_case_same_fact_no_a_note(app):
    from cc_api.onboarding_models import LocalIdentity
    from test_onboarding import issue, accept
    client,snap,sid=extract(app)
    assert save(client,sid,{**payload(snap),'note':'PHYSICIAN_A_PRIVATE_CANARY'}).status_code==200
    patient=doctor(app,'pxu_history_02');other=doctor(app,'doc_ther')
    with app.extensions['cc_session_factory']() as db:email=db.get(LocalIdentity,'pxu_history_02').email
    invitation=issue(other,email,['symptoms']);assert accept(patient,invitation).status_code==200
    submitted=mutate(patient,'POST','/api/v1/previsit-cases',{'doctor_id':'doc_ther','text':SOURCE,'case_consent':True})
    assert submitted.status_code==201,submitted.json
    cid=submitted.json['id'];new=start(other,url=path(PID,cid));assert new.status_code==200,new.json
    other_sid=new.json['tags'][0]['suggestion_id'];assert other_sid!=sid
    saved=save(other,other_sid,{**payload(new.json),'correctness':'unsupported','relevance':'not_relevant'})
    assert saved.status_code==200,saved.json
    own=other.get(CI+'/patients/'+PID+'/reviews?encounter_id='+cid)
    assert own.status_code==200 and 'PHYSICIAN_A_PRIVATE_CANARY' not in own.get_data(as_text=True)
    assert save(other,sid,payload(snap)).status_code==404
    a=next(i for i in reviews(client).json['items'] if i['suggestion_id']==sid)
    assert a['review']['correctness']=='supported' and a['review']['relevance']=='relevant'

def test_transfer_wrong_kind_role_and_no_csrf_no_mutation(app):
    client,snap,sid=extract(app);assert save(client,sid,payload(snap)).status_code==200
    treatment=native(client,'treatment');before=counts(app)
    assert transfer(client,treatment,sid,snap).status_code in (409,422)
    assert counts(app)==before
    doc=native(client)
    for uid in ('doc_ther','pat_02','clinic_01','researcher_01'):
        other=doctor(app,uid);before=counts(app)
        assert transfer(other,doc,sid,snap).status_code in (403,404)
        assert counts(app)==before
    assert client.put(CW+'/documents/'+doc['id'],json={'revision':doc['revision'],'mode':doc['mode'],'content':doc['content'],'ci_transfer':{}}).status_code==403

def test_review_error_telemetry_has_no_source_or_private_note(app,caplog):
    client,snap,sid=extract(app);private='PRIVATE_REVIEW_ERROR_CANARY'
    assert save(client,sid,{**payload(snap),'note':private}).status_code==200
    response=save(client,sid,{**payload(snap),'source_version':'0'*64,'note':private})
    assert response.status_code==409
    assert private not in response.get_data(as_text=True) and SOURCE not in response.get_data(as_text=True)
    assert private not in caplog.text and SOURCE not in caplog.text
    assert response.headers['Cache-Control']=='no-store'

def test_rate_limit_and_cache_expiry_do_not_duplicate_review(app):
    client,snap,sid=extract(app);body=payload(snap)
    assert save(client,sid,body).status_code==200;before=counts(app)
    runtime=app.extensions['ci_runtime']
    with runtime.lock:
        for item in runtime.cache.values():item['at']-=301
    assert client.get(path()).json['analysis_status']=='unavailable'
    assert save(client,sid,body).status_code==200
    statuses=[save(client,sid,body).status_code for _ in range(61)]
    assert 429 in statuses and set(statuses)<={200,429}
    assert counts(app)==before
    assert reviews(client).json['items']

def test_internal_failure_rolls_back_and_never_reports_saved(app):
    client,snap,sid=extract(app);before=counts(app)
    def fail():raise RuntimeError('synthetic_test_failure')
    app.extensions['ci_review_before_write']=fail
    app.config['PROPAGATE_EXCEPTIONS']=False
    response=save(client,sid,payload(snap))
    assert response.status_code==500 and 'native_draft_saved' not in response.get_data(as_text=True)
    assert SOURCE not in response.get_data(as_text=True) and counts(app)==before

def test_new_model_claims_do_not_silently_inherit_old_reviews(app):
    from cc_nlp.providers.mock import DeterministicMockProvider
    client,snap,sid=extract(app);assert save(client,sid,payload(snap)).status_code==200
    class Versioned(DeterministicMockProvider):model_id='different-synthetic-model-version'
    app.extensions['ci_runtime'].provider_factory=lambda config:Versioned()
    next_snapshot=start(client);assert next_snapshot.status_code==200
    next_ids={t['suggestion_id'] for t in next_snapshot.json['tags']}
    assert sid not in next_ids and next_snapshot.json['model_version']=='different-synthetic-model-version'
    listed=reviews(client).json['items'];old=next(i for i in listed if i['suggestion_id']==sid)
    assert old['model_version']==snap['model_version'] and old['review']['revision']==1
    assert all(i['review'] is None for i in listed if i['suggestion_id'] in next_ids)

@pytest.mark.parametrize('change',['source','grant'])
def test_changed_source_or_grant_at_commit_rolls_back(app,change):
    client,snap,sid=extract(app);before=counts(app)
    def alter(db):
        if change=='source':db.get(PrevisitCase,CID).intake_json=json.dumps({'text':'Иной синтетический текст.'})
        else:consent(db).accepted_at='2025-01-01T00:00:00Z'
        db.flush()
    app.extensions['ci_review_before_commit']=alter
    assert save(client,sid,payload(snap)).status_code==409
    assert counts(app)==before
    with app.extensions['cc_session_factory']() as db:
        assert json.loads(db.get(PrevisitCase,CID).intake_json)['text']==SOURCE

def test_review_limit_without_content_length_and_final_failure_atomicity(app):
    client,snap,sid=extract(app);before=counts(app)
    token=client.get('/api/v1/onboarding/bootstrap').json['csrf_token']
    response=client.post(review_path(sid),data=b'x'*17000,content_type='application/json',
        headers={'X-CSRF-Token':token},environ_overrides={'CONTENT_LENGTH':'','wsgi.input_terminated':True})
    assert response.status_code==413 and counts(app)==before
    def fail(db):raise RuntimeError('synthetic_final_transaction_failure')
    app.extensions['ci_review_before_commit']=fail;app.config['PROPAGATE_EXCEPTIONS']=False
    response=save(client,sid,payload(snap));assert response.status_code==500
    assert counts(app)==before

def test_historical_transfer_receipt_retry_current_native_state_and_revocation(app):
    client,snap,sid=extract(app);assert save(client,sid,payload(snap)).status_code==200
    doc=native(client);key=str(uuid4());first=transfer(client,doc,sid,snap,idempotency_key=key)
    assert first.status_code==200;receipt=first.json['ci_transfer']
    changed_review=save(client,sid,{**payload(snap),'review_revision':1,'correctness':'unsupported'})
    assert changed_review.status_code==200
    before=counts(app);retry=transfer(client,doc,sid,snap,idempotency_key=key)
    assert retry.status_code==200 and retry.json['ci_transfer']==receipt and counts(app)==before
    latest=client.get(CW+'/documents/'+doc['id']).json
    changed_native=mutate(client,'PUT',CW+'/documents/'+doc['id'],{'revision':latest['revision'],'mode':latest['mode'],
        'content':{**latest['content'],'narrative':latest['content']['narrative']+'\nПоследующее ручное изменение.'}})
    assert changed_native.status_code==200
    before=counts(app);retry=transfer(client,doc,sid,snap,idempotency_key=key)
    assert retry.status_code==200 and retry.json['ci_transfer']==receipt
    assert retry.json['revision']==changed_native.json['revision'] and counts(app)==before
    signed=mutate(client,'POST',CW+'/documents/'+doc['id']+'/sign',{'revision':changed_native.json['revision']})
    assert signed.status_code==200
    before=counts(app);retry=transfer(client,doc,sid,snap,idempotency_key=key)
    assert retry.status_code==200 and retry.json['status']=='signed' and retry.json['ci_transfer']==receipt and counts(app)==before
    assert transfer(client,signed.json,sid,snap,review_revision=2).status_code in (409,422)
    with app.extensions['cc_session_factory'].begin() as db:consent(db).revoked_at='2020-01-01T00:00:00Z'
    before=counts(app);assert transfer(client,doc,sid,snap,idempotency_key=key).status_code==404
    assert counts(app)==before

@pytest.mark.parametrize('operation',['claim','review','transfer'])
def test_sql_failure_is_redacted_and_atomic(app,caplog,operation):
    from sqlalchemy.exc import OperationalError
    client=doctor(app)
    if operation=='claim':snap=sid=doc=None
    else:
        client,snap,sid=extract(app,client)
        if operation=='transfer':
            assert save(client,sid,payload(snap)).status_code==200
            doc=native(client)
    before=counts(app)
    def fail(db):raise OperationalError('synthetic SQL',{'private':'SQL_PRIVATE_CANARY'},Exception('SQL_PRIVATE_CANARY'))
    app.extensions['ci_review_before_commit']=fail
    response=start(client) if operation=='claim' else (save(client,sid,payload(snap)) if operation=='review' else transfer(client,doc,sid,snap))
    assert response.status_code==503,response.json
    assert 'SQL_PRIVATE_CANARY' not in response.get_data(as_text=True) and 'SQL_PRIVATE_CANARY' not in caplog.text
    assert SOURCE not in response.get_data(as_text=True) and counts(app)==before
    if operation=='transfer':
        with app.extensions['cc_session_factory']() as db:assert db.get(ClinicalDocument,doc['id']).revision==doc['revision']
