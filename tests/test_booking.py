"""Persisted physician slot proposals and atomic patient acceptance, no mock booking."""
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import select
from cc_api import create_app
from cc_api.models import User
from cc_api.extension_models import PrevisitCase,Appointment
from test_onboarding import actor,mutate
from test_patient_experience import login

BK='/api/v1/booking'

def stamp(days=10,hours=0):
    return (datetime.now(timezone.utc).replace(microsecond=0)+timedelta(days=days,hours=hours)).isoformat()

@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev','SEED_PATIENT_PERSONAS':True,
        'SECRET_KEY':'phase4-booking','DB_PATH':str(tmp_path/'booking.sqlite')})

def setup_case(app,doctor_id='doc_psy',key='booking-case',persona='trend_one'):
    patient,identity=login(app,persona)
    doctor=actor(app,doctor_id)
    with app.extensions['cc_session_factory']() as db:
        db.add(PrevisitCase(id=key,patient_user_id=identity['id'],doctor_id=doctor_id,status='submitted',
            intake_json='{}',created_at=stamp(0),allowed_until=stamp(90)))
        db.commit()
    return patient,doctor,key

def slot(doctor,day=10,hour=0):
    response=mutate(doctor,'POST',BK+'/slots',{'starts_at':stamp(day,hour),'ends_at':stamp(day,hour+0.5)})
    assert response.status_code==201,response.json
    return response.json

def proposal(doctor,case,slots,**extra):
    response=mutate(doctor,'POST',BK+'/cases/'+case+'/proposals',{'slot_ids':[s['id'] for s in slots],**extra})
    assert response.status_code==201,response.json
    return response.json

def test_offer_is_not_confirmed_patient_accept_persists_and_replay_rejected(app):
    patient,doctor,case=setup_case(app)
    slots=[slot(doctor,hour=i) for i in (0,1)]
    offered=proposal(doctor,case,slots)
    assert offered['status']=='pending' and len(offered['candidates'])==2
    assert offered['expires_at']<=min(s['starts_at'] for s in slots)
    assert all(c['status']=='offered' for c in offered['candidates'])
    selected=offered['candidates'][0]['appointment_id']
    assert mutate(doctor,'POST',BK+'/appointments/'+selected+'/accept',{}).status_code==403
    confirmed=mutate(patient,'POST',BK+'/appointments/'+selected+'/accept',{})
    assert confirmed.status_code==200,confirmed.json
    assert confirmed.json['status']=='confirmed'
    assert mutate(patient,'POST',BK+'/appointments/'+selected+'/accept',{}).status_code==409
    with app.extensions['cc_session_factory']() as db:
        assert db.get(Appointment,selected).status=='confirmed'
        assert db.get(Appointment,offered['candidates'][1]['appointment_id']).status=='cancelled'
    restarted=create_app(dict(app.config))
    renewed,_=login(restarted)
    after=renewed.get(BK+'/cases/'+case+'/proposals')
    assert after.status_code==200,after.json
    saved=next(p for p in after.json['items'] if p['id']==offered['id'])
    assert saved['status']=='accepted'
    assert mutate(actor(restarted),'POST',BK+'/cases/'+case+'/proposals',{'slot_ids':[s['id'] for s in slots]}).status_code==409


@pytest.mark.parametrize('change',[{'starts_at':'2000-01-01T10:00:00Z','ends_at':'2000-01-01T10:30:00Z'},
    {'starts_at':'2026-12-01T10:00:00','ends_at':'2026-12-01T10:30:00'},
    {'ends_at':stamp(10,-1)},{'ends_at':stamp(10,3)},{'ends_at':stamp(10,0.1)},
    {'doctor_id':'doc_other'}])
def test_slot_strict_future_aware_duration_and_unknown_fields(app,change):
    doctor=actor(app)
    response=mutate(doctor,'POST',BK+'/slots',{'starts_at':stamp(),'ends_at':stamp(10,0.5),**change})
    assert response.status_code==422,response.json


def test_slot_overlap_and_role_boundaries(app):
    patient,doctor,_=setup_case(app)
    original=slot(doctor)
    response=mutate(doctor,'POST',BK+'/slots',{'starts_at':stamp(10,0.1),'ends_at':stamp(10,0.6)})
    assert response.status_code==409,response.json
    for client in (patient,actor(app,'clinic_01'),actor(app,'researcher_01'),actor(app,'platform_01')):
        assert client.get(BK+'/slots').status_code==403
        assert mutate(client,'POST',BK+'/slots',{'starts_at':stamp(12),'ends_at':stamp(12,0.5)}).status_code==403
    assert actor(app,'doc_ther').get(BK+'/slots').json['items']==[]


@pytest.mark.parametrize('kind',['one','duplicate','four','expired','late_expiry','unknown','foreign_slot'])
def test_proposal_count_scope_and_expiry_validation(app,kind):
    patient,doctor,case=setup_case(app)
    slots=[slot(doctor,hour=i) for i in range(4)]
    ids=[s['id'] for s in slots[:2]]
    payload={'slot_ids':ids}
    if kind=='one':payload['slot_ids']=ids[:1]
    elif kind=='duplicate':payload['slot_ids']=[ids[0],ids[0]]
    elif kind=='four':payload['slot_ids']=[s['id'] for s in slots]
    elif kind=='expired':payload['expires_at']='2000-01-01T00:00:00Z'
    elif kind=='late_expiry':payload['expires_at']=stamp(11)
    elif kind=='unknown':payload['slot_ids']=['missing-one','missing-two']
    else:payload['slot_ids'][0]=slot(actor(app,'doc_ther'),day=12)['id']
    response=mutate(doctor,'POST',BK+'/cases/'+case+'/proposals',payload)
    assert response.status_code in (404,409,422),response.json
    assert patient.get(BK+'/cases/'+case+'/proposals').json['items']==[]


@pytest.mark.parametrize('change',['expiry','withdrawn','tenant'])
def test_accept_rechecks_case_current_expiry_and_tenant(app,change):
    patient,doctor,case=setup_case(app)
    offered=proposal(doctor,case,[slot(doctor,hour=i) for i in (0,1)])
    with app.extensions['cc_session_factory']() as db:
        if change=='expiry':db.get(PrevisitCase,case).allowed_until='2000-01-01T00:00:00Z'
        elif change=='withdrawn':db.get(PrevisitCase,case).status='withdrawn'
        else:db.get(User,'doc_psy').organization_id='foreign_org'
        db.commit()
    response=mutate(patient,'POST',BK+'/appointments/'+offered['candidates'][0]['appointment_id']+'/accept',{})
    assert response.status_code in (403,404,409),response.json
    with app.extensions['cc_session_factory']() as db:
        assert all(db.get(Appointment,c['appointment_id']).status!='confirmed' for c in offered['candidates'])


def test_proposal_expiry_rechecked_no_confirmation(app):
    from cc_api.clinical_workflow_models import AppointmentProposal
    patient,doctor,case=setup_case(app)
    offered=proposal(doctor,case,[slot(doctor,hour=i) for i in (0,1)])
    with app.extensions['cc_session_factory']() as db:
        db.get(AppointmentProposal,offered['id']).expires_at='2000-01-01T00:00:00Z'
        db.commit()
    assert mutate(patient,'POST',BK+'/appointments/'+offered['candidates'][0]['appointment_id']+'/accept',{}).status_code==409


def test_concurrent_slot_acceptance_has_only_one_winner(app):
    patient,doctor,case=setup_case(app)
    slots=[slot(doctor,hour=i) for i in (0,1)]
    offered=proposal(doctor,case,slots)
    clients=[login(app)[0],login(app)[0]]
    barrier=Barrier(2)
    def accept(index):
        barrier.wait()
        return mutate(clients[index],'POST',BK+'/appointments/'+offered['candidates'][index]['appointment_id']+'/accept',{}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(accept,range(2)))==[200,409]
    with app.extensions['cc_session_factory']() as db:
        assert sum(db.get(Appointment,c['appointment_id']).status=='confirmed' for c in offered['candidates'])==1


def test_unrelated_patient_and_doctor_cannot_read_or_accept_proposals(app):
    patient,doctor,case=setup_case(app)
    offered=proposal(doctor,case,[slot(doctor,hour=i) for i in (0,1)])
    selected=offered['candidates'][0]['appointment_id']
    for client in (actor(app,'pat_02'),actor(app,'doc_other'),actor(app,'clinic_01'),actor(app,'researcher_01')):
        assert client.get(BK+'/cases/'+case+'/proposals').status_code in (403,404)
        assert mutate(client,'POST',BK+'/appointments/'+selected+'/accept',{}).status_code in (403,404)
        assert mutate(client,'POST',BK+'/appointments/'+selected+'/reschedule',{'reason':'Unauthorized'}).status_code in (403,404)


def test_reschedule_keeps_original_until_replacement_is_atomically_accepted(app):
    patient,doctor,case=setup_case(app)
    offered=proposal(doctor,case,[slot(doctor,hour=i) for i in (0,1)])
    original=offered['candidates'][0]['appointment_id']
    assert mutate(patient,'POST',BK+'/appointments/'+original+'/accept',{}).status_code==200
    requested=mutate(patient,'POST',BK+'/appointments/'+original+'/reschedule',{'reason':'Синтетический запрос переноса'})
    assert requested.status_code==201,requested.json
    request=requested.json
    with app.extensions['cc_session_factory']() as db:assert db.get(Appointment,original).status=='confirmed'
    restarted=create_app(dict(app.config))
    renewed,_=login(restarted)
    listed=renewed.get(BK+'/reschedule-requests')
    assert listed.status_code==200 and request['id'] in {r['id'] for r in listed.json['items']}
    replacement=mutate(actor(restarted),'POST',BK+'/reschedule-requests/'+request['id']+'/propose',
        {'slot_ids':[slot(actor(restarted),day=12,hour=i)['id'] for i in (0,1)]})
    assert replacement.status_code==201,replacement.json
    selected=replacement.json['candidates'][0]['appointment_id']
    with restarted.extensions['cc_session_factory']() as db:assert db.get(Appointment,original).status=='confirmed'
    assert mutate(renewed,'POST',BK+'/appointments/'+selected+'/accept',{}).status_code==200
    with restarted.extensions['cc_session_factory']() as db:
        assert db.get(Appointment,original).status=='cancelled'
        assert db.get(Appointment,selected).status=='confirmed'
    resolved=next(r for r in renewed.get(BK+'/reschedule-requests').json['items'] if r['id']==request['id'])
    assert resolved['status']=='resolved' and resolved['replacement_appointment_id']==selected


@pytest.mark.parametrize('status',['declined','expired'])
def test_closed_case_future_ttl_blocks_new_and_legacy_proposal_and_acceptance(app,status):
    patient,doctor,case=setup_case(app)
    slots=[slot(doctor,hour=i) for i in (0,1)]
    offered=proposal(doctor,case,slots)
    selected=offered['candidates'][0]['appointment_id']
    with app.extensions['cc_session_factory']() as db:
        db.get(PrevisitCase,case).status=status
        assert db.get(PrevisitCase,case).allowed_until>stamp(1)
        db.commit()
    for response in (
        mutate(doctor,'POST',BK+'/cases/'+case+'/proposals',{'slot_ids':[s['id'] for s in slots]}),
        mutate(doctor,'POST','/api/v1/previsit-cases/'+case+'/offers',{'proposed_at':stamp(12),'format':'video'}),
        mutate(patient,'POST',BK+'/appointments/'+selected+'/accept',{}),
        mutate(patient,'POST','/api/v1/appointments/'+selected+'/confirm',{})):
        assert response.status_code in (403,404,409),response.json
    with app.extensions['cc_session_factory']() as db:
        assert db.get(Appointment,selected).status!='confirmed'
