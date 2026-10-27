"""Real server clinical document lifecycle; signing is distinct from publication."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import select
from cc_api import create_app
from cc_api.models import DoctorPatientLink,User
from cc_api.onboarding_models import PatientConsent
from test_onboarding import actor,mutate
from test_patient_experience import login

CW='/api/v1/clinical-workflow'

@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev','SEED_PATIENT_PERSONAS':True,
        'SECRET_KEY':'phase4b-tests','DB_PATH':str(tmp_path/'clinical.sqlite')})

def participants(app,scopes='symptoms,diagnosis,medications'):
    patient,identity=login(app)
    with app.extensions['cc_session_factory']() as db:
        pid=db.get(User,identity['id']).patient_id
        db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.patient_id==pid,DoctorPatientLink.doctor_id=='doc_psy')).categories=scopes
        db.scalar(select(PatientConsent).where(PatientConsent.patient_user_id==identity['id'],PatientConsent.doctor_id=='doc_psy')).categories=scopes
        db.commit()
    return patient,actor(app),pid

def create(doctor,pid,kind='encounter',content=None,mode='quick'):
    response=mutate(doctor,'POST',CW+'/patients/'+pid+'/documents',{'kind':kind,'mode':mode,
        'content':{'narrative':'Синтетическая врачебная запись'} if content is None else content})
    assert response.status_code==201,response.json
    return response.json

def transition(doctor,doc,action,**extra):
    return mutate(doctor,'POST',CW+'/documents/'+doc['id']+'/'+action,{'revision':doc['revision'],**extra})

def documents(client,pid):
    response=client.get(CW+'/patients/'+pid+'/documents')
    assert response.status_code==200,response.json
    return response.json['items']

def test_draft_sign_explicit_release_amendment_and_restart(app):
    patient,doctor,pid=participants(app)
    draft=create(doctor,pid)
    assert draft['status']=='draft' and draft['signed_at'] is None and draft['published_at'] is None
    assert patient.get(CW+'/documents/'+draft['id']).status_code in (403,404)
    assert documents(patient,pid)==[]
    assert transition(doctor,draft,'publish').status_code==409
    signed=transition(doctor,draft,'sign')
    assert signed.status_code==200,signed.json
    signed=signed.json
    assert signed['status']=='signed' and signed['signed_at'] and signed['published_at'] is None
    assert documents(patient,pid)==[]
    assert patient.get(CW+'/documents/'+draft['id']).status_code in (403,404)
    assert mutate(doctor,'PUT',CW+'/documents/'+draft['id'],{'revision':signed['revision'],'mode':'quick','content':{'narrative':'Attempt rewrite'}}).status_code==409
    released=transition(doctor,signed,'publish')
    assert released.status_code==200,released.json
    released=released.json
    assert released['status']=='published' and released['published_at']
    own=patient.get(CW+'/documents/'+released['id'])
    assert own.status_code==200 and own.json['content']==draft['content']
    chart=patient.get('/api/v1/patient-experience/chart')
    assert chart.status_code==200 and 'Синтетическая врачебная запись' in json.dumps(chart.json,ensure_ascii=False)
    amended=transition(doctor,released,'amend',reason='Синтетическое уточнение')
    assert amended.status_code==201,amended.json
    amendment=amended.json
    assert amendment['id']!=released['id'] and amendment['parent_id']==released['id'] and amendment['status']=='draft'
    assert len(documents(patient,pid))==1
    saved=mutate(doctor,'PUT',CW+'/documents/'+amendment['id'],{'revision':amendment['revision'],'mode':'extended','content':{'narrative':'Синтетическое уточнение записи'}})
    assert saved.status_code==200,saved.json
    signed_new=transition(doctor,saved.json,'sign')
    assert signed_new.status_code==200,signed_new.json
    assert transition(doctor,signed_new.json,'publish').status_code==200
    assert len(documents(patient,pid))==2
    old=patient.get(CW+'/documents/'+released['id']).json
    assert old['content']==released['content'] and old['revision']==released['revision']
    restarted=create_app(dict(app.config))
    renewed,_=login(restarted)
    assert len(documents(renewed,pid))==2
    authored=actor(restarted).get(CW+'/documents/'+released['id']).json
    assert len(authored['versions'])>=3
    assert {'create','sign','publish'}<={v['action'] for v in authored['versions']}


def test_icd10_is_limited_versioned_clinician_only_and_server_validated(app):
    patient,doctor,pid=participants(app)
    response=doctor.get(CW+'/icd10?q=F32')
    assert response.status_code==200,response.json
    data=response.json
    assert data['coverage']=='limited_verified_subset' and data['version'] and data['limitation']
    entry=next(item for item in data['items'] if item['code']=='F32')
    assert entry['label'] and entry['version']==data['version'] and entry['source_url'].startswith('https://')
    assert patient.get(CW+'/icd10?q=F32').status_code==403
    for status in ('preliminary','confirmed'):
        doc=create(doctor,pid,content={'narrative':'Синтетическая запись','diagnoses':[{'code':'F32','version':entry['version'],'status':status}]})
        diagnosis=doc['content']['diagnoses'][0]
        assert diagnosis['code']=='F32' and diagnosis['status']==status and diagnosis['label']==entry['label']
    for diagnosis in ({'code':'UNSUPPORTED','version':entry['version'],'status':'confirmed'},
        {'code':'F32','version':'wrong','status':'confirmed'},{'code':'F32','version':entry['version'],'status':'automatic'},
        {'code':'F32','version':entry['version'],'status':'confirmed','label':'Client supplied fake title'}):
        response=mutate(doctor,'POST',CW+'/patients/'+pid+'/documents',{'kind':'encounter','mode':'quick','content':{'narrative':'Synthetic','diagnoses':[diagnosis]}})
        assert response.status_code==422,response.json


def test_optional_modular_treatment_orders_publication_and_append_only_adherence(app):
    patient,doctor,pid=participants(app)
    content={'items':[{'item_type':'medication','title':'Синтетическое назначение врача','notes':'Технический пример'},
        {'item_type':'behavioral','title':'Синтетическая согласованная активность'}]}
    draft=create(doctor,pid,'treatment',content)
    assert len(draft['orders'])==1
    order=draft['orders'][0]
    assert order['title']==content['items'][0]['title']
    assert order['reference_id'] is None and order['reference_version'] is None
    assert patient.get(CW+'/patients/'+pid+'/medication-orders').json['items']==[]
    assert mutate(patient,'POST',CW+'/medication-orders/'+order['id']+'/report',{'outcome':'completed'}).status_code in (403,404)
    signed=transition(doctor,draft,'sign').json
    published=transition(doctor,signed,'publish')
    assert published.status_code==200,published.json
    assert transition(doctor,signed,'publish').status_code==409
    orders=patient.get(CW+'/patients/'+pid+'/medication-orders').json['items']
    assert len(orders)==1 and orders[0]['id']==order['id']
    for outcome in ('completed','missed'):
        response=mutate(patient,'POST',CW+'/medication-orders/'+order['id']+'/report',{'outcome':outcome,'note':'Синтетический самоотчёт'})
        assert response.status_code==201,response.json
    after=patient.get(CW+'/patients/'+pid+'/medication-orders').json['items'][0]
    assert [r['outcome'] for r in after['reports']]==['completed','missed']
    assert after['regimen']==order['regimen'] and after['title']==order['title']
    assert mutate(doctor,'POST',CW+'/medication-orders/'+order['id']+'/report',{'outcome':'completed'}).status_code==403
    assert mutate(patient,'POST',CW+'/medication-orders/'+order['id']+'/report',{'outcome':'invented'}).status_code==422
    dashboard=patient.get('/api/v1/patient-experience/dashboard').json
    assert any(plan['id']==draft['id'] for plan in dashboard['plans'])
    assert mutate(patient,'DELETE','/api/v1/patients/me/clinical-links/doc_psy',{}).status_code==200
    assert patient.get(CW+'/patients/'+pid+'/medication-orders').json['items']==[]
    assert mutate(patient,'POST',CW+'/medication-orders/'+order['id']+'/report',{'outcome':'completed'}).status_code==404


@pytest.mark.parametrize('identity',['pat_02','doc_other','doc_ther','clinic_01','researcher_01','platform_01'])
def test_private_document_author_tenant_role_boundaries(app,identity):
    patient,doctor,pid=participants(app)
    doc=create(doctor,pid)
    other=actor(app,identity)
    assert other.get(CW+'/documents/'+doc['id']).status_code in (403,404)
    assert other.get(CW+'/patients/'+pid+'/documents').status_code in (403,404)
    assert transition(other,doc,'sign').status_code in (403,404)
    assert mutate(other,'PUT',CW+'/documents/'+doc['id'],{'revision':doc['revision'],'mode':'quick','content':{'narrative':'Unauthorized'}}).status_code in (403,404)


@pytest.mark.parametrize('removed',['diagnosis','medications','symptoms','tenant','ledger'])
def test_all_required_scopes_and_current_consent_rechecked_for_reads_and_sign(app,removed):
    patient,doctor,pid=participants(app)
    version=doctor.get(CW+'/icd10?q=F32').json['version']
    doc=create(doctor,pid,'treatment',{'diagnoses':[{'code':'F32','version':version,'status':'preliminary'}],
        'items':[{'item_type':'medication','title':'Синтетическое назначение'}]})
    with app.extensions['cc_session_factory']() as db:
        link=db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.patient_id==pid,DoctorPatientLink.doctor_id=='doc_psy'))
        if removed=='tenant':db.get(User,'doc_psy').organization_id='foreign_org'
        elif removed=='ledger':
            db.scalar(select(PatientConsent).where(PatientConsent.doctor_id=='doc_psy',PatientConsent.patient_user_id==db.scalar(select(User.id).where(User.patient_id==pid)))).revoked_at='2026-05-01T10:00:00Z'
        else:link.categories=','.join(s for s in ('symptoms','diagnosis','medications') if s!=removed)
        db.commit()
    assert doctor.get(CW+'/documents/'+doc['id']).status_code==404
    assert transition(doctor,doc,'sign').status_code==404
    assert all(item['id']!=doc['id'] for item in documents(patient,pid))


def test_concurrent_draft_cas_and_sign_prevent_lost_update(app):
    _,doctor,pid=participants(app)
    doc=create(doctor,pid)
    clients=[actor(app),actor(app)]
    barrier=Barrier(2)
    def save(index):
        barrier.wait()
        return mutate(clients[index],'PUT',CW+'/documents/'+doc['id'],{'revision':doc['revision'],'mode':'quick','content':{'narrative':'Synthetic edit '+str(index)}}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save,range(2)))==[200,409]
    current=doctor.get(CW+'/documents/'+doc['id']).json
    barrier=Barrier(2)
    def sign(index):
        barrier.wait()
        return transition(clients[index],current,'sign').status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(sign,range(2)))==[200,409]


@pytest.mark.parametrize('content',[{}, {'narrative':''},{'narrative':'x','patient_id':'pat_b'},
    {'narrative':'x','diagnoses':[{'code':'F32'}]}, {'narrative':'x','unknown':True},
    {'narrative':'x','items':[{'item_type':'medication','title':'Test','reference_id':'invented','reference_version':'1'}]},
    {'narrative':'x','items':[{'item_type':'automated_prescription','title':'Test'}]}])
def test_strict_content_validation_never_creates_implicit_orders(app,content):
    _,doctor,pid=participants(app)
    response=mutate(doctor,'POST',CW+'/patients/'+pid+'/documents',{'kind':'encounter','mode':'quick','content':content})
    assert response.status_code==422,response.json
    assert documents(doctor,pid)==[]


def test_new_account_has_no_clinical_documents_or_orders(app):
    from test_onboarding import register
    patient=app.test_client()
    identity=register(patient,'phase4-no-seeded-orders@qa.test')
    with app.extensions['cc_session_factory']() as db:pid=db.get(User,identity['user']['id']).patient_id
    assert documents(patient,pid)==[]
    assert patient.get(CW+'/patients/'+pid+'/medication-orders').json['items']==[]


def test_published_treatment_amendment_supersedes_active_plan_without_deleting_order_history(app):
    from cc_api.p0_models import CarePlan
    from cc_api.clinical_workflow_models import MedicationOrder,MedicationAdherence
    patient,doctor,pid=participants(app)
    draft=create(doctor,pid,'treatment',{'items':[{'item_type':'medication','title':'Синтетический первый план'}]})
    signed=transition(doctor,draft,'sign').json
    old=transition(doctor,signed,'publish').json
    oid=old['orders'][0]['id']
    assert mutate(patient,'POST',CW+'/medication-orders/'+oid+'/report',{'outcome':'completed'}).status_code==201
    amendment=transition(doctor,old,'amend',reason='Синтетическая согласованная корректировка').json
    edited=mutate(doctor,'PUT',CW+'/documents/'+amendment['id'],{'revision':amendment['revision'],'mode':'quick',
        'content':{'items':[{'item_type':'medication','title':'Синтетический уточнённый план'}]}})
    assert edited.status_code==200,edited.json
    signed_new=transition(doctor,edited.json,'sign').json
    new=transition(doctor,signed_new,'publish')
    assert new.status_code==200,new.json
    with app.extensions['cc_session_factory']() as db:
        assert db.get(CarePlan,old['id']).status=='superseded'
        assert db.get(CarePlan,new.json['id']).status=='active'
        assert db.get(MedicationOrder,oid) is not None
        assert len(db.scalars(select(MedicationAdherence).where(MedicationAdherence.order_id==oid)).all())==1
    dashboard=patient.get('/api/v1/patient-experience/dashboard').json
    active_ids={plan['id'] for plan in dashboard['plans']}
    assert new.json['id'] in active_ids and old['id'] not in active_ids
    assert patient.get(CW+'/documents/'+old['id']).json['content']==old['content']


@pytest.mark.parametrize('operation',['clinical_sign','physician_priority'])
def test_committing_revocation_wins_over_mutation_waiting_for_consent_lock(app,operation):
    """Hold the real revocation transaction; waiting mutations must recheck grants.

    SQL events control interleaving only. Real identity, SQL locks, HTTP mutation,
    commit, and authorization all execute normally against the shared SQLite file.
    """
    from threading import Event
    from sqlalchemy import event
    patient,doctor,pid=participants(app)
    draft=create(doctor,pid)
    engine=app.extensions['cc_session_factory'].kw['bind']
    revocation_holds_lock=Event()
    mutation_attempts_lock=Event()
    allow_revoke_commit=Event()
    def after_execute(conn,cursor,statement,parameters,context,executemany):
        if 'update ob_consents set revoked_at' in statement.lower():
            revocation_holds_lock.set()
            assert allow_revoke_commit.wait(10),'Test coordinator did not release real revocation transaction'
    def before_execute(conn,cursor,statement,parameters,context,executemany):
        if revocation_holds_lock.is_set() and 'update ob_consents set version' in statement.lower():
            mutation_attempts_lock.set()
    event.listen(engine,'after_cursor_execute',after_execute)
    event.listen(engine,'before_cursor_execute',before_execute)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            revoke=pool.submit(mutate,patient,'DELETE','/api/v1/patients/me/clinical-links/doc_psy',{})
            assert revocation_holds_lock.wait(10),'Revocation never acquired its real SQL write lock'
            if operation=='clinical_sign':
                mutation=pool.submit(transition,doctor,draft,'sign')
            else:
                mutation=pool.submit(mutate,doctor,'PUT','/api/v1/doctor-experience/patients/'+pid+'/priority',
                    {'priority':3,'revision':0,'note':'Must not persist after revocation'})
            try:
                assert mutation_attempts_lock.wait(10),'Clinical mutation did not acquire consent lock before access'
            finally:
                allow_revoke_commit.set()
            assert revoke.result(timeout=15).status_code==200
            denied=mutation.result(timeout=15)
            assert denied.status_code==404,denied.json
        assert doctor.get(CW+'/documents/'+draft['id']).status_code==404
        from cc_api.clinical_workflow_models import ClinicalDocument
        with app.extensions['cc_session_factory']() as db:
            assert db.get(ClinicalDocument,draft['id']).status=='draft'
    finally:
        allow_revoke_commit.set()
        event.remove(engine,'after_cursor_execute',after_execute)
        event.remove(engine,'before_cursor_execute',before_execute)


@pytest.mark.parametrize('revocation',['medication_scope','entire_link'])
def test_released_treatment_compatibility_views_and_reports_respect_revocation(app,revocation):
    patient,doctor,pid=participants(app)
    marker='DISTINCT SYNTHETIC MEDICATION RELEASE'
    draft=create(doctor,pid,'treatment',{'items':[{'item_type':'medication','title':marker}]})
    signed=transition(doctor,draft,'sign').json
    released=transition(doctor,signed,'publish')
    assert released.status_code==200,released.json
    plan_id=released.json['id']
    p0=patient.get('/api/v1/p0/care-plans')
    assert p0.status_code==200
    plan=next(p for p in p0.json['items'] if p['id']==plan_id)
    item_id=plan['items'][0]['id']
    assert marker in json.dumps(p0.json)
    assert marker in json.dumps(patient.get('/api/v1/patient-experience/dashboard').json)
    assert mutate(patient,'POST','/api/v1/p0/plan-items/'+item_id+'/report',{'outcome':'completed'}).status_code==201
    # Compatibility creation also requires explicit signature and release.
    legacy=mutate(doctor,'POST','/api/v1/p0/care-plans',{'patient_id':pid,
        'items':[{'item_type':'action','title':'Separate synthetic legacy action'}]})
    assert legacy.status_code==201,legacy.json
    legacy_id=legacy.json['id']
    assert legacy.json['status']=='draft'
    assert legacy_id not in {p['id'] for p in patient.get('/api/v1/p0/care-plans').json['items']}
    legacy_signed=transition(doctor,legacy.json,'sign').json
    assert legacy_id not in {p['id'] for p in patient.get('/api/v1/p0/care-plans').json['items']}
    assert transition(doctor,legacy_signed,'publish').status_code==200
    legacy_plan=next(p for p in patient.get('/api/v1/p0/care-plans').json['items'] if p['id']==legacy_id)
    if revocation=='entire_link':
        assert mutate(patient,'DELETE','/api/v1/patients/me/clinical-links/doc_psy',{}).status_code==200
    else:
        with app.extensions['cc_session_factory']() as db:
            link=db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.doctor_id=='doc_psy',DoctorPatientLink.patient_id==pid))
            link.categories='symptoms,diagnosis'
            db.commit()
    for response in (patient.get('/api/v1/p0/care-plans'),patient.get('/api/v1/patient-experience/dashboard')):
        assert response.status_code==200
        assert marker not in json.dumps(response.json)
        assert plan_id not in {p['id'] for p in response.json.get('items',response.json.get('plans',[]))}
    assert patient.get(CW+'/documents/'+plan_id).status_code==404
    assert doctor.get(CW+'/documents/'+plan_id).status_code==404
    assert mutate(patient,'POST','/api/v1/p0/plan-items/'+item_id+'/report',{'outcome':'completed'}).status_code==404
    remaining=patient.get('/api/v1/p0/care-plans').json['items']
    assert (legacy_id in {p['id'] for p in remaining}) == (revocation=='medication_scope')
    assert mutate(patient,'POST','/api/v1/p0/plan-items/'+legacy_plan['items'][0]['id']+'/report',{'outcome':'completed'}).status_code==(201 if revocation=='medication_scope' else 404)
