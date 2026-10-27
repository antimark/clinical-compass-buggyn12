"""Executable unmet P0 acceptance assertions (strict expected failures).

They should turn XPASS and fail CI only when a proper feature is implemented;
then update the source and tests instead of silently removing them.
"""
from auth_support import login_response
import os
import pytest
from cc_api import create_app

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.delenv('CC_DATABASE_URL',raising=False)
    return create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev','SECRET_KEY':'qa-p0-known-blocker',
                       'DB_PATH':str(tmp_path/'blocked.sqlite')}).test_client()

def role(c,uid):
    r=login_response(c,uid)
    assert r.status_code==200
    return {'X-CSRF-Token':r.json['csrf_token']}

@pytest.mark.xfail(strict=True,reason='C04: real email verification deferred; synthetic registration separately verified')
def test_c04_patient_verified_self_registration(client):
    assert client.get('/api/v1/p0/auth/capabilities').json['registration_enabled'] is True

@pytest.mark.xfail(strict=True,reason='C05-C06: real credential verification deferred; actual invited MFA enrollment separately verified')
def test_c05_c06_clinician_verified_enrollment(client):
    assert client.get('/api/v1/p0/auth/capabilities').json['verified_staff_enrollment_enabled'] is True

def test_plan_amendments_exist(client):
    role(client,'doc_psy')
    h=role(client,'doc_psy')
    created=client.post('/api/v1/clinical-workflow/patients/pat_a/documents',headers=h,json={
        'kind':'treatment','mode':'quick','content':{'items':[{'item_type':'action','title':'Синтетический план'}]}})
    assert created.status_code==201
    row=created.json
    for step in ('sign','publish'):
        result=client.post('/api/v1/clinical-workflow/documents/'+row['id']+'/'+step,headers=h,json={'revision':row['revision']})
        assert result.status_code==200;row=result.json
    amended=client.post('/api/v1/clinical-workflow/documents/'+row['id']+'/amend',headers=h,json={'revision':row['revision'],'reason':'Уточнение синтетического плана'})
    assert amended.status_code==201
    items=client.get('/api/v1/p0/care-plans/amendments').json['items']
    assert any(x['id']==amended.json['id'] and x['parent_id']==row['id'] and x['status']=='draft' for x in items)
    role(client,'pat_01')
    assert client.get('/api/v1/p0/care-plans/amendments').status_code==403

@pytest.mark.xfail(strict=True,reason='P08/D13: complete versioned SignalEngine with source evidence not integrated')
def test_versioned_signal_evidence_exists(client):
    role(client,'doc_psy')
    assert client.get('/api/v1/p0/alerts/al_001').json['signal_provenance']!='Legacy synthetic fixture; no validated SignalEngine evidence available'

def test_signed_encounter_correction(client):
    h=role(client,'doc_psy')
    a=client.post('/api/v1/p0/encounters/pat_a',json={'mode':'quick','narrative':'Synthetic visit','sign':True},headers=h)
    assert a.status_code==201
    response=client.post('/api/v1/p0/encounters/'+a.json['id']+'/amend',json={'reason':'Correction','text':'Addendum'},headers=h)
    assert response.status_code==201 and response.json['encounter_id']==a.json['id']
    from cc_api.p0_models import Encounter
    from cc_api.clinical_review_models import EncounterAddendum
    with client.application.extensions['cc_session_factory']() as db:
        assert 'Synthetic visit' in db.get(Encounter,a.json['id']).content_json
        assert db.get(EncounterAddendum,response.json['id']).reason=='Correction'
    role(client,'pat_01')
    assert client.post('/api/v1/p0/encounters/'+a.json['id']+'/amend',json={'reason':'Correction','text':'No'},headers=role(client,'pat_01')).status_code==403

def test_purpose_bound_contact_grant(client):
    h=role(client,'clinic_01')
    ref=client.get('/api/v1/p0/clinic/patients').json['items'][0]['patient_ref']
    response=client.post('/api/v1/p0/clinic/patients/'+ref+'/reveal',json={
        'purpose':'appointment_administration','requested_fields':['contact']},headers=h)
    # A purpose string alone never grants access; explicit feature/patient grants
    # and encrypted values are tested positively in test_phase5_acceptance.
    assert response.status_code==403
    assert client.get('/api/v1/p0/clinic/patients/'+ref).json['fields']=={}

def test_advanced_research_definition(client):
    h=role(client,'researcher_01')
    x=client.post('/api/v1/p0/dataset-definitions',json={
        'study_id':'study_demo_v1','measure':'synthetic_mood','cohorts':['A','B'],
        'criteria':{'include':['synthetic_quality']},'min_cell':10},headers=h)
    assert x.status_code==201 and x.json.get('applied_criteria')

def test_admin_scheduling_update(client):
    h=role(client,'pat_03')
    case=client.post('/api/v1/previsit-cases',json={
        'doctor_id':'doc_psy','text':'Synthetic appointment','case_consent':True},headers=h)
    assert case.status_code==201
    appt=client.post('/api/v1/previsit-cases/'+case.json['id']+'/appointment-requests',json={},headers=h)
    assert appt.status_code==201
    h=role(client,'clinic_01')
    result=client.post('/api/v1/p0/clinic/appointments/reschedule',json={
        'appointment_id':appt.json['id'],'new_time':'2026-11-10T10:00:00Z'},headers=h)
    assert result.status_code==200 and result.json['booking_confirmed'] is False
    from cc_api.extension_models import Appointment
    from cc_api.clinical_workflow_models import RescheduleRequest
    with client.application.extensions['cc_session_factory']() as db:
        assert db.get(Appointment,appt.json['id']).status=='requested'
        assert db.get(RescheduleRequest,result.json['id']).status=='requested'
