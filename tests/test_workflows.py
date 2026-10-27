"""Run with pytest after installing backend/requirements.txt. Synthetic only."""
from auth_support import login_response
import pytest
from cc_api import create_app

@pytest.fixture
def client(tmp_path):
    a=create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev','DB_PATH':str(tmp_path/'test.sqlite')})
    return a.test_client()

def switch(client,user):
    r=login_response(client,user)
    assert r.status_code==200
    return {'X-CSRF-Token':r.json['csrf_token']}

def test_patient_previsit_private_until_invited(client):
    h=switch(client,'pat_01')
    r=client.post('/api/v1/previsit-cases',json={'doctor_id':'doc_psy','case_consent':True,'text':'Trouble sleeping','symptoms':['insomnia'],'conditions':['patient_reported_anxiety']},headers=h)
    assert r.status_code==201;case=r.json['id']
    assert client.post(f'/api/v1/previsit-cases/{case}/messages',json={'text':'Hello'},headers=h).status_code==201
    assert client.post(f'/api/v1/previsit-cases/{case}/messages',json={'text':'Second'},headers=h).status_code==409
    h=switch(client,'doc_ther')
    assert client.get(f'/api/v1/previsit-cases/{case}').status_code==403
    h=switch(client,'doc_psy')
    assert client.get(f'/api/v1/previsit-cases/{case}').status_code==200
    assert client.post(f'/api/v1/previsit-cases/{case}/messages',json={'text':'Can schedule'},headers=h).status_code==201
    offer=client.post(f'/api/v1/previsit-cases/{case}/offers',json={'proposed_at':'2026-11-04T11:00:00+02:00','format':'video'},headers=h)
    assert offer.status_code==201
    h=switch(client,'pat_01')
    assert client.post(f'/api/v1/appointments/{offer.json["id"]}/confirm',json={},headers=h).status_code==200
    assert client.post(f'/api/v1/previsit-cases/{case}/messages',json={'text':'Thanks'},headers=h).status_code==201

def test_invitation_one_time_and_authorization(client):
    h=switch(client,'doc_psy')
    r=client.post('/api/v1/invitations',json={'target_role':'patient','recipient_id':'pat_03','patient_id':'pat_c','categories':['symptoms']},headers=h)
    assert r.status_code==201;token=r.json['registration_code']
    h=switch(client,'doc_ther')
    assert client.post('/api/v1/invitations/accept',json={'registration_code':token},headers=h).status_code==403
    h=switch(client,'pat_03')
    assert client.post('/api/v1/invitations/accept',json={'registration_code':token,'consent':True,'consent_version':'clinical-link-v1'},headers=h).status_code==200
    assert client.post('/api/v1/invitations/accept',json={'registration_code':token},headers=h).status_code==404

def test_clinic_cannot_read_previsit_or_create_patient_link(client):
    h=switch(client,'clinic_01')
    assert client.get('/api/v1/previsit-cases').status_code==403
    assert client.post('/api/v1/invitations',json={'target_role':'patient','recipient_id':'pat_03','patient_id':'pat_c'},headers=h).status_code==403
    assert client.post('/api/v1/invitations',json={'target_role':'doctor','recipient_id':'doc_ther','categories':[]},headers=h).status_code==201

def test_care_team_grant_and_revoke(client):
    h=switch(client,'pat_01')
    endpoint='/api/v1/care-team/visibility';payload={'doctor_a':'doc_psy','doctor_b':'doc_ther','allow':True}
    assert client.post(endpoint,json=payload,headers=h).status_code==200
    switch(client,'doc_psy')
    assert len(client.get('/api/v1/doctors/doc_ther/shared-patients').json['items'])==1
    h=switch(client,'pat_01');payload['allow']=False
    assert client.post(endpoint,json=payload,headers=h).status_code==200
    switch(client,'doc_psy')
    assert client.get('/api/v1/doctors/doc_ther/shared-patients').json['items']==[]

def test_csrf_and_role_restrictions(client):
    switch(client,'pat_01')
    assert client.post('/api/v1/previsit-cases',json={'doctor_id':'doc_psy','text':'Help'}).status_code==403
    assert client.get('/api/v1/research/synthetic-summary').status_code==403
    switch(client,'researcher_01')
    r=client.get('/api/v1/research/synthetic-summary')
    assert r.status_code==200 and r.json['dataset'].startswith('synthetic')
