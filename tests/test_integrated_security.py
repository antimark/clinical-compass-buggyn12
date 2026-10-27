"""Integration/negative tests. Requires Flask + project dependencies in a clean venv."""
from auth_support import login_response
import json
import pytest
from sqlalchemy import select
from cc_api import create_app
from cc_api.extension_models import Invitation, ResearchObservation
from cc_api.models import DoctorPatientLink

@pytest.fixture
def client(tmp_path):
    return create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev','SECRET_KEY':'test-isolated',
                       'DB_PATH':str(tmp_path/'security.sqlite')}).test_client()

def sw(client,user):
    r=login_response(client,user)
    assert r.status_code==200, r.json
    return {'X-CSRF-Token':r.json['csrf_token']}

def post(client,path,body,h):
    return client.post(path,json=body,headers=h)

def test_link_not_implicit_before_invitation_accept_and_cross_org(client):
    h=sw(client,'pat_03')
    case=post(client,'/api/v1/previsit-cases',{'doctor_id':'doc_ther','text':'Synthetic intake',
        'symptoms':['insomnia'],'conditions':['patient report'],'case_consent':True},h)
    assert case.status_code==201
    h=sw(client,'doc_ther')
    assert client.get('/api/v1/doctors/me/patients/pat_c/overview').status_code==404
    assert client.get('/api/v1/previsit-cases/'+case.json['id']).status_code==200
    r=post(client,'/api/v1/invitations',{'target_role':'patient','recipient_id':'pat_03',
        'patient_id':'pat_c','categories':['symptoms']},h)
    assert r.status_code==201
    assert client.get('/api/v1/doctors/me/patients/pat_c/overview').status_code==404
    code=r.json['registration_code']
    h=sw(client,'pat_01')
    assert post(client,'/api/v1/invitations/accept',{'registration_code':code},h).status_code==403
    h=sw(client,'pat_03')
    assert post(client,'/api/v1/invitations/accept',{'registration_code':code,'consent':True,'consent_version':'clinical-link-v1'},h).status_code==200
    assert post(client,'/api/v1/invitations/accept',{'registration_code':code},h).status_code==404
    sw(client,'doc_ther')
    assert client.get('/api/v1/doctors/me/patients/pat_c/overview').status_code==200
    h=sw(client,'doc_other')
    assert client.get('/api/v1/doctors/me/patients/pat_c/overview').status_code==404
    assert post(client,'/api/v1/invitations',{'target_role':'patient','recipient_id':'pat_03',
        'patient_id':'pat_c','categories':['symptoms']},h).status_code==403

def test_invitation_expiry_revoke_and_storage_only_hash(client):
    h=sw(client,'doc_ther')
    issued=post(client,'/api/v1/invitations',{'target_role':'patient',
        'recipient_id':'pat_03','patient_id':'pat_c','categories':['symptoms']},h).json
    session_factory=client.application.extensions['cc_session_factory']
    with session_factory.begin() as db:
        inv=db.get(Invitation,issued['id'])
        assert issued['registration_code'] not in json.dumps({c.name:getattr(inv,c.name) for c in inv.__table__.columns})
    assert post(client,'/api/v1/invitations/'+issued['id']+'/revoke',{},h).status_code==200
    h=sw(client,'pat_03')
    assert post(client,'/api/v1/invitations/accept',{'registration_code':issued['registration_code']},h).status_code==404
    h=sw(client,'doc_ther')
    issued=post(client,'/api/v1/invitations',{'target_role':'patient','recipient_id':'pat_03',
        'patient_id':'pat_c','categories':['symptoms']},h).json
    with session_factory.begin() as db:
        inv=db.get(Invitation,issued['id']);inv.expires_at='2020-01-01T00:00:00+00:00'
    h=sw(client,'pat_03')
    assert post(client,'/api/v1/invitations/accept',{'registration_code':issued['registration_code']},h).status_code==404

def test_staff_onboarding_requires_recipient_and_org(client):
    h=sw(client,'clinic_01')
    assert post(client,'/api/v1/invitations',{'target_role':'patient','recipient_id':'pat_01',
        'patient_id':'pat_a','categories':['symptoms']},h).status_code==403
    assert post(client,'/api/v1/invitations',{'target_role':'doctor','recipient_id':'doc_other','categories':[]},h).status_code==403
    issued=post(client,'/api/v1/invitations',{'target_role':'doctor','recipient_id':'doc_psy','categories':[]},h)
    assert issued.status_code==201
    h=sw(client,'doc_psy')
    assert post(client,'/api/v1/invitations/accept',{'registration_code':issued.json['registration_code']},h).status_code==200
    assert client.get('/api/v1/previsit-cases').status_code==200
    h=sw(client,'platform_01')
    issued=post(client,'/api/v1/invitations',{'target_role':'clinic_admin','recipient_id':'clinic_01','categories':[]},h)
    assert issued.status_code==201
    h=sw(client,'clinic_01')
    assert post(client,'/api/v1/invitations/accept',{'registration_code':issued.json['registration_code']},h).status_code==200
    assert client.get('/api/v1/doctors/me/patients').status_code==403

def test_previsit_scopes_peer_and_care_team_privacy(client):
    h=sw(client,'pat_03')
    no_consent=post(client,'/api/v1/previsit-cases',{'doctor_id':'doc_psy','text':'Private'},h)
    assert no_consent.status_code==422
    created=post(client,'/api/v1/previsit-cases',{'doctor_id':'doc_psy','text':'Private',
      'case_consent':True},h)
    assert created.status_code==201
    case_id=created.json['id']
    assert post(client,f'/api/v1/previsit-cases/{case_id}/messages',{'text':'First'},h).status_code==201
    assert post(client,f'/api/v1/previsit-cases/{case_id}/messages',{'text':'Second'},h).status_code==409
    h=sw(client,'doc_ther')
    assert client.get(f'/api/v1/previsit-cases/{case_id}/messages').status_code==403
    assert client.get(f'/api/v1/previsit-cases/{case_id}').status_code==403
    assert post(client,f'/api/v1/previsit-cases/{case_id}/messages',{'text':'No'},h).status_code==403
    assert post(client,'/api/v1/threads/doctor_peer/doc_psy/messages',{'text':'No patient details'},h).status_code==201
    assert client.get('/api/v1/threads/doctor_peer/doc_psy/messages').json['items'][0]['text']=='No patient details'
    assert client.get('/api/v1/doctors/doc_psy/shared-patients').json['items']==[]
    h=sw(client,'pat_01')
    assert post(client,'/api/v1/care-team/visibility',{'doctor_a':'doc_psy','doctor_b':'doc_ther','allow':True},h).status_code==200
    sw(client,'doc_ther')
    records=client.get('/api/v1/doctors/doc_psy/shared-patients').json['items']
    assert len(records)==1 and set(records[0])=={'shared_patient_ref'}
    assert 'pat_a' not in str(records)
    h=sw(client,'pat_01')
    assert post(client,'/api/v1/care-team/visibility',{'doctor_a':'doc_psy','doctor_b':'doc_ther','allow':False},h).status_code==200
    sw(client,'doc_ther')
    assert client.get('/api/v1/doctors/doc_psy/shared-patients').json['items']==[]

def test_questionnaire_role_and_replay(client):
    h=sw(client,'doc_ther')
    assign=post(client,'/api/v1/instruments/assignments',{'patient_id':'pat_a','instrument_id':'GAD-7'},h)
    assert assign.status_code==201
    assignment_id=assign.json['id']
    h=sw(client,'pat_03')
    assert post(client,f'/api/v1/instruments/assignments/{assignment_id}/submit',{'scores':[0]*7},h).status_code==404
    h=sw(client,'pat_01')
    assert post(client,f'/api/v1/instruments/assignments/{assignment_id}/submit',{'scores':[0]*6},h).status_code==422
    r=post(client,f'/api/v1/instruments/assignments/{assignment_id}/submit',{'scores':[0,1,2,3,0,1,2]},h)
    assert r.status_code==200 and r.json['total']==9
    assert post(client,f'/api/v1/instruments/assignments/{assignment_id}/submit',{'scores':[0]*7},h).status_code==409

def test_research_recomputation_small_cells_no_row_data(client):
    h=sw(client,'researcher_01')
    first=client.get('/api/v1/research/cohorts').json
    assert len(first['items'])==2 and all(x['missing_n']==2 for x in first['items'])
    session_factory=client.application.extensions['cc_session_factory']
    with session_factory.begin() as db:
        one=db.scalar(select(ResearchObservation).where(ResearchObservation.cohort=='A',ResearchObservation.value.is_not(None)))
        one.value=1
        db.add(ResearchObservation(id='test_small',study_id='study_demo_v1',study_subject='synthetic_small',
           cohort='C',measure='synthetic_mood',value=3,source='synthetic_test',recorded_at='2026-10-18T00:00:00Z'))
    again=client.get('/api/v1/research/cohorts').json
    # Previously disclosed definition versions remain reproducible. A fresh
    # query over changed values must not provide a differencing side channel.
    assert again==first
    assert {row['cohort'] for row in again['items']}=={'A','B'}
    created=post(client,'/api/v1/p0/dataset-definitions',{'study_id':'study_demo_v1',
        'measure':'synthetic_mood','cohorts':['A']},h)
    assert created.status_code==201,created.json
    guarded=client.get('/api/v1/p0/dataset-definitions/'+created.json['id']+'/compute')
    assert guarded.status_code==200,guarded.json
    cell=guarded.json['items'][0]
    assert cell['suppressed'] is True and cell['suppression_reason']=='changed_population_values_requires_review'
    assert all(cell[key] is None for key in ('n','observed_n','missing_n','mean'))
    exported=client.get('/api/v1/research/export')
    assert exported.status_code==200 and 'synthetic_small' not in exported.get_data(as_text=True)
    assert exported.is_json and exported.json==first
    h=sw(client,'clinic_01')
    assert client.get('/api/v1/research/cohorts').status_code==403
    assert client.get('/api/v1/research/export').status_code==403

def test_ai_adapter_no_external_or_unapproved_recipient(client,monkeypatch):
    h=sw(client,'pat_01')
    assert post(client,'/api/v1/ai/summary-drafts',{'recipient_doctor_id':'doc_psy'},h).status_code==503
    monkeypatch.setenv('CC_AI_MODE','deterministic_mock')
    draft=post(client,'/api/v1/ai/summary-drafts',{'recipient_doctor_id':'doc_psy'},h)
    assert draft.status_code==201 and draft.json['state']=='needs_review'
    sw(client,'doc_psy')
    assert client.get('/api/v1/doctors/me/ai-summaries').json['items']==[]
    h=sw(client,'pat_01')
    assert post(client,'/api/v1/ai/summary-drafts/'+draft.json['id']+'/approve',{'approve':False},h).status_code==422
    assert post(client,'/api/v1/ai/summary-drafts/'+draft.json['id']+'/approve',{'approve':True},h).status_code==200
    sw(client,'doc_psy')
    assert len(client.get('/api/v1/doctors/me/ai-summaries').json['items'])==1
    sw(client,'doc_ther')
    assert client.get('/api/v1/doctors/me/ai-summaries').json['items']==[]

def test_cross_role_forbidden_admin_pii_and_csrf(client):
    h=sw(client,'clinic_01')
    assert client.get('/api/v1/previsit-cases').status_code==403
    assert client.get('/api/v1/patients/me/clinical').status_code==403
    assert client.get('/api/v1/audit/me').status_code==200
    h=sw(client,'pat_01')
    assert post(client,'/api/v1/patients/me/check-ins',{'mood_score':4,'comparison':'same'},{}).status_code==403
    assert post(client,'/api/v1/patients/me/check-ins',{'mood_score':4,'comparison':'same'},h).status_code==201

def test_clinical_link_and_case_consent_withdrawal_independent(client):
    h=sw(client,'pat_01')
    assert client.get('/api/v1/patients/me/links').status_code==200
    case=post(client,'/api/v1/previsit-cases',{'doctor_id':'doc_psy','text':'Synthetic case',
        'case_consent':True},h).json['id']
    link_revoke=client.delete('/api/v1/patients/me/clinical-links/doc_psy',headers=h)
    assert link_revoke.status_code==200
    assert client.get('/api/v1/patients/me/links').json['items']!=[]  # doc_ther remains
    sw(client,'doc_psy')
    assert client.get('/api/v1/doctors/me/patients/pat_a/overview').status_code==404
    assert client.get('/api/v1/previsit-cases/'+case).status_code==200  # case consent independent
    h=sw(client,'pat_01')
    assert post(client,'/api/v1/previsit-cases/'+case+'/withdraw',{},h).status_code==200
    sw(client,'doc_psy')
    assert client.get('/api/v1/previsit-cases/'+case).status_code==403
    assert client.get('/api/v1/previsit-cases/'+case+'/messages').status_code==403


def test_patient_doctor_chat_scoped_not_equal_previsit_or_peer(client):
    h=sw(client,'pat_01')
    p=post(client,'/api/v1/threads/patient_doctor/doc_ther/messages',{'text':'Clinical chat'},h)
    assert p.status_code==201
    h=sw(client,'doc_ther')
    records=client.get('/api/v1/threads/patient_doctor/pat_01/messages').json['items']
    assert len(records)==1 and records[0]['text']=='Clinical chat'
    assert client.get('/api/v1/threads/doctor_peer/doc_psy/messages').json['items']==[]
    h=sw(client,'doc_other')
    # Linked-patient lookups deliberately return 404 to avoid confirming
    # whether another organization's patient/thread exists (anti-enumeration).
    assert client.get('/api/v1/threads/patient_doctor/pat_01/messages').status_code==404
    h=sw(client,'clinic_01')
    assert client.get('/api/v1/threads/patient_doctor/pat_01/messages').status_code==403
