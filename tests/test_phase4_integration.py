"""Cross-flow Phase 4 acceptance: opt-in personas, release/privacy and audit history.

Actual HTTP process replacement is separately reproducible with
scripts/check_doctor_experience_restart.py; no test substitutes mocked storage.
"""
import json
import pytest
from sqlalchemy import select
from cc_api import create_app
from cc_api.models import User,DoctorPatientLink
from cc_api.p0_models import AdverseEvent
from test_onboarding import actor,mutate,register
from test_patient_experience import login,observation

PX='/api/v1/patient-experience'
CW='/api/v1/clinical-workflow'

@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev','SEED_PATIENT_PERSONAS':True,
        'SECRET_KEY':'phase4-cross-flow','DB_PATH':str(tmp_path/'crossflow.sqlite')})


@pytest.mark.parametrize('key,count',[('clinical_care',10),('clinical_history',15)])
def test_opt_in_clinical_personas_connect_real_history_result_plan_and_private_documents(app,key,count):
    patient,identity=login(app,key)
    pid=identity['user']['patient_id'] if 'user' in identity else identity['patient_id']
    dashboard=patient.get(PX+'/dashboard')
    assert dashboard.status_code==200
    assert dashboard.json['state']=='history' and dashboard.json['plans']
    own=patient.get(CW+'/patients/'+pid+'/documents')
    assert own.status_code==200
    docs=own.json['items']
    assert len(docs)==2 and {d['kind'] for d in docs}=={'encounter','treatment'}
    assert all(d['status']=='published' and d['signed_at'] and d['published_at'] for d in docs)
    assert patient.get(CW+'/documents/cdoc_fixture_'+key+'_signed').status_code==404
    assert patient.get(CW+'/documents/cdoc_fixture_'+key+'_draft').status_code==404
    doctor=actor(app)
    authored=doctor.get(CW+'/patients/'+pid+'/documents')
    assert authored.status_code==200
    assert {'draft','signed','published'}<={d['status'] for d in authored.json['items']}
    assignment=patient.get(PX+'/questionnaires/assignments').json['items'][0]
    result=patient.get(PX+'/questionnaires/assignments/'+assignment['id']+'/result')
    assert result.status_code==200
    assert len(result.json['answers'])==count
    assert result.json['score']==sum(item['value'] for item in result.json['answers'])
    assert doctor.get(PX+'/questionnaires/assignments/'+assignment['id']+'/result').json==result.json
    plans=patient.get(CW+'/patients/'+pid+'/medication-orders').json['items']
    assert plans and all(p['reference_id'] and p['reference_version'] for p in plans)
    assert any(p['reports'] for p in plans)
    for other in ('doc_other','clinic_01','researcher_01','platform_01'):
        assert actor(app,other).get(CW+'/documents/'+docs[0]['id']).status_code in (403,404)
    assert mutate(patient,'DELETE','/api/v1/patients/me/clinical-links/doc_psy',{}).status_code==200
    assert patient.get(CW+'/patients/'+pid+'/documents').json['items']==[]
    assert doctor.get(CW+'/patients/'+pid+'/documents').status_code==404
    assert doctor.get(PX+'/questionnaires/assignments/'+assignment['id']+'/result').status_code==404
    assert patient.get(PX+'/questionnaires/assignments/'+assignment['id']+'/result').json==result.json


def test_seed_once_never_restores_revoked_grants_or_resets_patient_additions_and_new_account_empty(app):
    patient,identity=login(app,'clinical_care')
    pid=identity.get('patient_id')
    assert pid
    response=observation(patient,'phase4-retained-real-addition',value=4,observed_at='2026-05-01T10:00:00Z')
    assert response.status_code==201,response.json
    before=patient.get(PX+'/observations').json
    assert mutate(patient,'DELETE','/api/v1/patients/me/clinical-links/doc_psy',{}).status_code==200
    # Existing Phase 3 identities/grants must remain as the user left them.
    with app.extensions['cc_session_factory']() as db:
        old=db.get(User,'pxu_trend_one')
        previous_identity=(old.id,old.patient_id,old.display_name)
        old_link=db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.doctor_id=='doc_psy',DoctorPatientLink.patient_id==old.patient_id))
        old_link.categories='medications'
        db.commit()
    restarted=create_app(dict(app.config))
    renewed,_=login(restarted,'clinical_care')
    assert renewed.get(PX+'/observations').json==before
    assert renewed.get(CW+'/patients/'+pid+'/documents').json['items']==[]
    with restarted.extensions['cc_session_factory']() as db:
        old=db.get(User,'pxu_trend_one')
        assert (old.id,old.patient_id,old.display_name)==previous_identity
        assert db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.doctor_id=='doc_psy',DoctorPatientLink.patient_id==old.patient_id)).categories=='medications'
        assert db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.doctor_id=='doc_psy',DoctorPatientLink.patient_id==pid)) is None
    fresh=restarted.test_client()
    register(fresh,'phase4-new-stays-empty@qa.test')
    empty=fresh.get(PX+'/dashboard').json
    assert empty['state']=='empty' and empty['plans']==[] and empty['series']==[] and empty['assignments']==[]


def test_adverse_review_append_history_preserves_legacy_review_and_hides_internal_patient_notes(app):
    from cc_api.physician_history_models import AdverseEventReviewRevision
    patient,identity=login(app,'clinical_care')
    pid=identity['patient_id']
    doctor=actor(app)
    response=mutate(patient,'POST','/api/v1/p0/adverse-events',{'description':'Синтетическое сообщение для аудита'})
    assert response.status_code==201,response.json
    eid=response.json['id']
    # Model an existing assessment made before append-history migration. First
    # new review must preserve this old assessment rather than overwrite it.
    with app.extensions['cc_session_factory']() as db:
        row=db.get(AdverseEvent,eid)
        row.status='assessed';row.review_text='PREVIOUS PRIVATE PHYSICIAN ASSESSMENT'
        row.reviewer_id='doc_psy';row.reviewed_at='2026-04-01T10:00:00Z'
        db.commit()
    for status,note in [('assessed','SECOND PRIVATE PHYSICIAN ASSESSMENT'),('closed','FINAL PRIVATE PHYSICIAN ASSESSMENT')]:
        reviewed=mutate(doctor,'POST','/api/v1/p0/adverse-events/'+eid+'/review',{'status':status,'review_text':note})
        assert reviewed.status_code==200,reviewed.json
    clinician=doctor.get('/api/v1/p0/adverse-events?patient_id='+pid)
    assert clinician.status_code==200
    item=next(item for item in clinician.json['items'] if item['id']==eid)
    assert [r['review_text'] for r in item['reviews']]==[
        'PREVIOUS PRIVATE PHYSICIAN ASSESSMENT','SECOND PRIVATE PHYSICIAN ASSESSMENT','FINAL PRIVATE PHYSICIAN ASSESSMENT']
    assert [r['version'] for r in item['reviews']]==[1,2,3]
    own=patient.get('/api/v1/p0/adverse-events')
    assert own.status_code==200
    assert 'PRIVATE PHYSICIAN' not in json.dumps(own.json)
    assert all('reviews' not in item and 'review_text' not in item for item in own.json['items'])
    with app.extensions['cc_session_factory']() as db:
        assert len(db.scalars(select(AdverseEventReviewRevision).where(AdverseEventReviewRevision.event_id==eid)).all())==3
    assert mutate(patient,'DELETE','/api/v1/patients/me/clinical-links/doc_psy',{}).status_code==200
    assert doctor.get('/api/v1/p0/adverse-events?patient_id='+pid).status_code==404
    assert mutate(doctor,'POST','/api/v1/p0/adverse-events/'+eid+'/review',{'status':'closed','review_text':'Must not append after revocation'}).status_code==404
    with app.extensions['cc_session_factory']() as db:
        assert len(db.scalars(select(AdverseEventReviewRevision).where(AdverseEventReviewRevision.event_id==eid)).all())==3


@pytest.mark.parametrize('field',['raw_original_json','structured_json'])
def test_reference_reseed_fails_closed_for_tampered_raw_or_structured_content(app,field):
    from cc_api.reference_models import DrugReference
    from cc_api.medical_references import seed_medical_references
    factory=app.extensions['cc_session_factory']
    with factory() as db:
        row=db.scalar(select(DrugReference))
        key=(row.id,row.version)
        original=getattr(row,field)
        altered=json.loads(original)
        altered['product']['name']='SYNTHETIC TAMPER TEST ONLY'
        tampered=json.dumps(altered,ensure_ascii=False)
        setattr(row,field,tampered)
        db.commit()
    with pytest.raises(ValueError,match='immutable reference differs'):
        seed_medical_references(factory)
    with factory() as db:
        assert getattr(db.get(DrugReference,key),field)==tampered,'Fail-closed verification must not silently rewrite stored versions'
        assert len(db.scalars(select(DrugReference)).all())==8


def test_legacy_adverse_event_paths_require_medications_scope_and_current_ledger(app):
    from cc_api.onboarding_models import PatientConsent
    patient,identity=login(app,'clinical_care')
    pid=identity['patient_id']
    doctor=actor(app)
    created=mutate(patient,'POST','/api/v1/p0/adverse-events',{'description':'Синтетическая проверка отдельного доступа к переносимости'})
    assert created.status_code==201,created.json
    eid=created.json['id']
    def set_scope(scope):
        with app.extensions['cc_session_factory']() as db:
            db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.doctor_id=='doc_psy',DoctorPatientLink.patient_id==pid)).categories=scope
            db.commit()
    set_scope('symptoms')
    assert doctor.get('/api/v1/p0/adverse-events?patient_id='+pid).status_code==404
    assert mutate(doctor,'POST','/api/v1/p0/adverse-events/'+eid+'/review',
        {'status':'assessed','review_text':'Must not read medication concern with symptoms-only grant'}).status_code==404
    set_scope('medications')
    assert doctor.get('/api/v1/p0/adverse-events?patient_id='+pid).status_code==200
    reviewed=mutate(doctor,'POST','/api/v1/p0/adverse-events/'+eid+'/review',
        {'status':'assessed','review_text':'PRIVATE MEDICATION SCOPE REVIEW'})
    assert reviewed.status_code==200,reviewed.json
    own=patient.get('/api/v1/p0/adverse-events')
    assert own.status_code==200 and 'PRIVATE MEDICATION SCOPE REVIEW' not in json.dumps(own.json)
    with app.extensions['cc_session_factory']() as db:
        consent=db.scalar(select(PatientConsent).where(PatientConsent.doctor_id=='doc_psy',PatientConsent.patient_user_id==identity['id']))
        consent.revoked_at='2026-06-01T10:00:00Z'
        assert db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.doctor_id=='doc_psy',DoctorPatientLink.patient_id==pid)) is not None
        db.commit()
    assert doctor.get('/api/v1/p0/adverse-events?patient_id='+pid).status_code==404
    assert mutate(doctor,'POST','/api/v1/p0/adverse-events/'+eid+'/review',
        {'status':'closed','review_text':'Must not append after ledger withdrawal with stale link'}).status_code==404
