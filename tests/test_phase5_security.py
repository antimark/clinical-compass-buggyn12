"""Public-API regressions for current scopes and repaired legacy boundaries.

Authentication uses real application synthetic-dev sessions and CSRF. Database
fixtures model legacy corruption only; no ACL or identity function is patched.
"""
from auth_support import login_response
import json
from datetime import datetime,timedelta,timezone
import pytest
from sqlalchemy import delete,event,func,select
from cc_api import create_app
from cc_api.models import DoctorPatientLink,User
from cc_api.extension_models import AISummaryDraft,Appointment,Invitation,PrevisitCase
from cc_api.onboarding_models import PatientConsent,PatientInvitation

ALL_SCOPES=['symptoms','diagnosis','medications']


@pytest.fixture
def app(tmp_path,monkeypatch):
    monkeypatch.setenv('CC_AI_MODE','deterministic_mock')
    return create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev',
        'SECRET_KEY':'phase5-legacy-security-tests','DB_PATH':str(tmp_path/'security.sqlite')})


def actor(app,user):
    client=app.test_client();response=login_response(client,user)
    assert response.status_code==200,response.json
    return client


def mutate(client,method,path,data=None):
    me=client.get('/api/v1/auth/me');assert me.status_code==200
    return client.open(path,method=method,json=data or {},headers={'X-CSRF-Token':me.json['csrf_token']})


def issue(doctor,scopes=None):
    result=mutate(doctor,'POST','/api/v1/invitations',{'target_role':'patient','recipient_id':'pat_01',
        'patient_id':'pat_a','categories':ALL_SCOPES if scopes is None else scopes})
    assert result.status_code==201,result.json
    return result.json


def accept(patient,invitation,**extra):
    return mutate(patient,'POST','/api/v1/invitations/accept',{
        'registration_code':invitation['registration_code'],'consent':True,
        'consent_version':'clinical-link-v1',**extra})


def granted(app,scopes=None):
    doctor,patient=actor(app,'doc_psy'),actor(app,'pat_01')
    invitation=issue(doctor,scopes);assert accept(patient,invitation).status_code==200
    return doctor,patient,invitation


def statements_during(app,operation):
    engine=app.extensions['cc_session_factory'].kw['bind'];statements=[]
    def capture(_connection,_cursor,statement,_parameters,_context,_many):
        statements.append(statement.lower())
    event.listen(engine,'before_cursor_execute',capture)
    try:return operation(),statements
    finally:event.remove(engine,'before_cursor_execute',capture)


@pytest.mark.parametrize('removed_scope',['diagnosis','medications'])
def test_legacy_approved_freeform_summary_requires_every_current_scope_before_content_read(app,removed_scope):
    doctor,patient,_=granted(app)
    created=mutate(patient,'POST','/api/v1/ai/summary-drafts',{'recipient_doctor_id':'doc_psy'})
    assert created.status_code==201,created.json
    draft_id=created.json['id'];private='Синтетический диагноз и препарат: PRIVATE_SCOPE_MARKER'
    edited=mutate(patient,'POST','/api/v1/p0/summary-drafts/'+draft_id+'/edit',{'content':private})
    assert edited.status_code==200
    assert mutate(patient,'POST','/api/v1/ai/summary-drafts/'+draft_id+'/approve',{'approve':True}).status_code==200
    visible=doctor.get('/api/v1/doctors/me/ai-summaries')
    assert visible.status_code==200 and any(x['id']==draft_id and x['content']==private for x in visible.json['items'])
    narrowed=issue(doctor,[scope for scope in ALL_SCOPES if scope!=removed_scope])
    assert accept(patient,narrowed).status_code==200
    # The relationship and symptoms remain valid; hiding the summary must result
    # from its removed category, rather than removing the patient entirely.
    assert doctor.get('/api/v1/p0/observations/pat_a').status_code==200
    response,statements=statements_during(app,lambda:doctor.get('/api/v1/doctors/me/ai-summaries'))
    assert response.status_code==200 and draft_id not in {x['id'] for x in response.json['items']}
    assert private not in response.get_data(as_text=True)
    assert not any('cc_ai_summary_drafts.content' in statement for statement in statements)
    with app.extensions['cc_session_factory']() as db:
        assert db.get(AISummaryDraft,draft_id).content==private
    restored=issue(doctor);assert accept(patient,restored).status_code==200
    assert draft_id in {x['id'] for x in doctor.get('/api/v1/doctors/me/ai-summaries').json['items']}


def test_legacy_case_creation_rejects_other_tenant_without_persisting(app):
    patient=actor(app,'pat_01')
    with app.extensions['cc_session_factory']() as db:before=db.scalar(select(func.count()).select_from(PrevisitCase))
    result=mutate(patient,'POST','/api/v1/previsit-cases',{'doctor_id':'doc_other','text':'Synthetic cross-tenant case',
        'symptoms':[],'conditions':[],'case_consent':True})
    assert result.status_code==404,result.json
    with app.extensions['cc_session_factory']() as db:
        assert db.scalar(select(func.count()).select_from(PrevisitCase))==before


@pytest.mark.parametrize('user',['pat_01','doc_other'])
def test_legacy_corrupt_cross_tenant_case_hidden_before_intake_or_messages_read(app,user):
    factory=app.extensions['cc_session_factory'];created=datetime.now(timezone.utc)
    with factory.begin() as db:
        db.add(PrevisitCase(id='legacy-cross-tenant',doctor_id='doc_other',patient_user_id='pat_01',status='submitted',
            intake_json=json.dumps({'text':'PRIVATE_CROSS_TENANT_INTAKE'}),created_at=created.isoformat(),
            allowed_until=(created+timedelta(days=1)).isoformat()))
    client=actor(app,user)
    for suffix in ('','/messages'):
        response,statements=statements_during(app,lambda:client.get('/api/v1/previsit-cases/legacy-cross-tenant'+suffix))
        assert response.status_code==404,response.json
        assert 'PRIVATE_CROSS_TENANT_INTAKE' not in response.get_data(as_text=True)
        assert not any('cc_previsit_cases.intake_json' in statement for statement in statements)
    assert 'legacy-cross-tenant' not in {x['id'] for x in client.get('/api/v1/previsit-cases').json['items']}


def test_legacy_request_slot_rechecks_case_tenant_before_read_or_persistence(app):
    factory=app.extensions['cc_session_factory'];created=datetime.now(timezone.utc)
    with factory.begin() as db:
        db.add(PrevisitCase(id='legacy-cross-slot',doctor_id='doc_other',patient_user_id='pat_01',status='submitted',
            intake_json=json.dumps({'text':'PRIVATE_SLOT_CASE'}),created_at=created.isoformat(),
            allowed_until=(created+timedelta(days=1)).isoformat()))
        before=db.scalar(select(func.count()).select_from(Appointment))
    patient=actor(app,'pat_01')
    response,statements=statements_during(app,lambda:mutate(patient,'POST',
        '/api/v1/previsit-cases/legacy-cross-slot/appointment-requests'))
    assert response.status_code==404,response.json
    assert not any('cc_previsit_cases.intake_json' in statement for statement in statements)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Appointment))==before


@pytest.mark.parametrize('bad',[
    {'consent':False},{'consent':'true'},{'consent_version':'unknown'}])
def test_legacy_code_needs_explicit_versioned_consent_before_ledger_and_link(app,bad):
    factory=app.extensions['cc_session_factory']
    with factory.begin() as db:
        db.execute(delete(DoctorPatientLink).where(DoctorPatientLink.doctor_id=='doc_psy',DoctorPatientLink.patient_id=='pat_a'))
    doctor,patient=actor(app,'doc_psy'),actor(app,'pat_01');invitation=issue(doctor)
    result=accept(patient,invitation,**bad);assert result.status_code==422,result.json
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(PatientConsent))==0
        assert db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.doctor_id=='doc_psy',DoctorPatientLink.patient_id=='pat_a')) is None
        assert db.get(Invitation,invitation['id']).status=='pending'
    result=accept(patient,invitation);assert result.status_code==200 and result.json['clinical_link_created']
    with factory() as db:
        ledger=db.scalar(select(PatientConsent).where(PatientConsent.invitation_id=='legacy_'+invitation['id']))
        assert ledger and ledger.patient_user_id=='pat_01' and ledger.doctor_id=='doc_psy'
        assert ledger.version=='clinical-link-v1' and set(ledger.categories.split(','))==set(ALL_SCOPES)
        shadow=db.get(PatientInvitation,ledger.invitation_id)
        assert shadow.status=='accepted' and shadow.patient_user_id=='pat_01'
        assert db.get(User,'pat_01').role=='patient'
    assert accept(patient,invitation).status_code==404
    assert mutate(patient,'DELETE','/api/v1/patients/me/clinical-links/doc_psy').status_code==200
    assert doctor.get('/api/v1/doctors/me/patients/pat_a/overview').status_code==404
    with factory() as db:
        assert db.scalar(select(PatientConsent).where(PatientConsent.invitation_id=='legacy_'+invitation['id'])).revoked_at


def test_legacy_code_wrong_recipient_never_creates_ledger(app):
    doctor=actor(app,'doc_psy');invitation=issue(doctor)
    assert accept(actor(app,'pat_03'),invitation).status_code==403
    with app.extensions['cc_session_factory']() as db:
        assert not db.scalar(select(PatientConsent).where(PatientConsent.invitation_id=='legacy_'+invitation['id']))
        assert db.get(Invitation,invitation['id']).status=='pending'


def test_linked_patient_metadata_requires_actual_nonempty_current_scope(app):
    doctor,patient,_=granted(app)
    assert any(row['id']=='pat_01' for row in doctor.get('/api/v1/doctors/me/linked-patients').json['items'])
    empty=issue(doctor,[]);assert accept(patient,empty).status_code==200
    response=doctor.get('/api/v1/doctors/me/linked-patients')
    assert response.status_code==200 and 'pat_01' not in {row['id'] for row in response.json['items']}
