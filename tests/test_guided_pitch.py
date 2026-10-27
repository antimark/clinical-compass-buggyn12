"""Guided pitch is a read projection of genuine authorized clinical writes."""
import json
from datetime import datetime,timedelta,timezone
import pytest
from sqlalchemy import select,func
from cc_api import create_app
from cc_api.models import User
from cc_api.extension_models import Audit
from cc_api.p0_models import UserNotification
from cc_api.pitch_models import PitchRun,PitchEscalationSimulation
from test_onboarding import actor,mutate
from test_patient_experience import login,observation
from test_clinical_workflow import create,transition,CW

PT='/api/v1/pitch'
DX='/api/v1/doctor-experience'

@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev','SEED_PATIENT_PERSONAS':True,
        'SECRET_KEY':'phase5-pitch-tests','DB_PATH':str(tmp_path/'pitch.sqlite')})

def setup(app):
    patient,identity=login(app,'clinical_care')
    doctor=actor(app)
    response=mutate(doctor,'POST',PT+'/runs',{'patient_id':identity['patient_id']})
    assert response.status_code==201,response.json
    return patient,doctor,identity['patient_id'],response.json

def progress(client,run):
    response=client.get(PT+'/runs/'+run['id']+'/progress')
    assert response.status_code==200,response.json
    return response.json

def steps(value):return {s['key']:s['done'] for s in value['steps']}

def deteriorate(patient,doctor,pid):
    now=datetime.now(timezone.utc)-timedelta(seconds=10)
    ids=[]
    for n,value in enumerate((5,1)):
        response=observation(patient,value=value,observed_at=(now+timedelta(seconds=n)).isoformat())
        assert response.status_code==201,response.json
        ids.append(response.json['id'])
    response=doctor.get(DX+'/dashboard')
    assert response.status_code==200,response.json
    return ids


def test_new_run_does_not_claim_existing_fixture_history_as_new_steps(app):
    patient,doctor,pid,run=setup(app)
    # Fixture already has published plans, decisions, historical signals and observations.
    own=progress(doctor,run)
    assert all(value is False for value in steps(own).values()),own
    assert own['signals']==[] and own['escalations']==[]
    patient_steps=steps(progress(patient,run))
    assert patient_steps['observation'] is False and patient_steps['publication'] is False
    assert all(patient_steps[k] is None for k in ('alert','chart_review','decision','treatment'))
    # Discovering old observations for the first time after starting the run is
    # not evidence of a new patient write.
    assert doctor.get(DX+'/dashboard').status_code==200
    assert steps(progress(doctor,run))['alert'] is False


def test_genuine_cross_role_writes_explicit_review_decision_sign_and_publication(app):
    patient,doctor,pid,run=setup(app)
    ids=deteriorate(patient,doctor,pid)
    state=progress(doctor,run)
    assert steps(state)['observation'] is True and steps(state)['alert'] is True
    for signal in state['signals']:
        detail=doctor.get(DX+'/signals/'+signal['id']).json
        assert set(ids)&{point['id'] for point in detail['evidence']['observations']}
    assert mutate(patient,'POST',PT+'/runs/'+run['id']+'/chart-review',{}).status_code==403
    assert mutate(doctor,'POST',PT+'/runs/'+run['id']+'/chart-review',{}).json=={'reviewed':True}
    with app.extensions['cc_session_factory']() as db:
        assert db.scalar(select(Audit.id).where(Audit.action=='pitch_chart_reviewed',Audit.object_id==run['id'],Audit.actor=='doc_psy'))
    assert mutate(doctor,'POST','/api/v1/p0/decisions/'+pid,{'text':'Синтетическое решение','explicit_confirmation':False}).status_code==422
    assert steps(progress(doctor,run))['decision'] is False
    assert mutate(doctor,'POST','/api/v1/p0/decisions/'+pid,{'text':'Синтетическое решение','explicit_confirmation':True}).status_code==201
    draft=create(doctor,pid,'treatment',{'narrative':'PRIVATE PITCH DRAFT','items':[{'item_type':'action','title':'Синтетический план'}]})
    assert steps(progress(doctor,run))['treatment'] is True
    assert 'PRIVATE PITCH DRAFT' not in json.dumps(progress(patient,run))
    assert patient.get(CW+'/documents/'+draft['id']).status_code==404
    signed=transition(doctor,draft,'sign')
    assert signed.status_code==200,signed.json
    assert steps(progress(patient,run))['publication'] is False
    assert patient.get(CW+'/documents/'+draft['id']).status_code==404
    assert transition(doctor,signed.json,'publish').status_code==200
    assert all(value is True for value in steps(progress(doctor,run)).values())
    assert steps(progress(patient,run))['publication'] is True
    restarted=create_app(dict(app.config))
    renewed,_=login(restarted,'clinical_care')
    assert steps(progress(renewed,run))['publication'] is True


@pytest.mark.parametrize('identity',['doc_other','doc_ther','pat_01','clinic_01','researcher_01','platform_01'])
def test_run_rejects_nonparticipants_and_other_tenant(app,identity):
    _,_,_,run=setup(app)
    other=actor(app,identity)
    assert other.get(PT+'/runs/'+run['id']+'/progress').status_code in (403,404)
    assert mutate(other,'POST',PT+'/runs/'+run['id']+'/chart-review',{}).status_code in (403,404)


def test_current_ledger_revocation_hides_run_and_blocks_mutation(app):
    from cc_api.onboarding_models import PatientConsent
    patient,doctor,pid,run=setup(app)
    with app.extensions['cc_session_factory']() as db:
        consent=db.scalar(select(PatientConsent).where(PatientConsent.doctor_id=='doc_psy',PatientConsent.patient_user_id=='pxu_clinical_care'))
        assert consent
        consent.categories='symptoms,diagnosis'
        db.commit()
    for client in (patient,doctor):
        assert client.get(PT+'/runs/'+run['id']+'/progress').status_code==404
        assert run['id'] not in json.dumps(client.get(PT+'/runs').json)
    assert mutate(doctor,'POST',PT+'/runs/'+run['id']+'/chart-review',{}).status_code==404
    assert mutate(doctor,'POST',PT+'/runs',{'patient_id':pid}).status_code==404


def test_escalation_nullable_explicit_config_cas_manual_only_and_no_delivery(app):
    patient,doctor,pid,run=setup(app)
    deteriorate(patient,doctor,pid)
    state=progress(doctor,run)
    sid=state['signals'][0]['id']
    config=next(c for c in state['escalations'] if c['signal_id']==sid)
    assert config=={'signal_id':sid,'delay_seconds':None,'target_label':None,'revision':0}
    with app.extensions['cc_session_factory']() as db:before=db.scalar(select(func.count()).select_from(UserNotification))
    endpoint=PT+'/signals/'+sid
    assert mutate(doctor,'POST',endpoint+'/simulate',{'revision':0,'explicit_demo':True}).status_code==409
    empty=mutate(doctor,'PUT',endpoint+'/escalation',{'revision':0,'delay_seconds':None,'target_label':None})
    assert empty.status_code==200 and empty.json['revision']==1
    assert mutate(doctor,'POST',endpoint+'/simulate',{'revision':1,'explicit_demo':True}).status_code==422
    for payload in ({'revision':1,'delay_seconds':True,'target_label':'TEST'}, {'revision':1,'delay_seconds':-1,'target_label':'TEST'},
                    {'revision':1,'delay_seconds':0,'target_label':' '}):
        assert mutate(doctor,'PUT',endpoint+'/escalation',payload).status_code==422
    saved=mutate(doctor,'PUT',endpoint+'/escalation',{'revision':1,'delay_seconds':120,'target_label':'Условный участник демонстрации'})
    assert saved.status_code==200 and saved.json['revision']==2
    assert mutate(doctor,'PUT',endpoint+'/escalation',{'revision':1,'delay_seconds':60,'target_label':'STALE'}).status_code==409
    assert mutate(doctor,'POST',endpoint+'/simulate',{'revision':2}).status_code==409
    for client in (patient,actor(app,'doc_other')):
        assert mutate(client,'PUT',endpoint+'/escalation',{'revision':2,'delay_seconds':0,'target_label':'UNAUTHORIZED'}).status_code in (403,404)
        assert mutate(client,'POST',endpoint+'/simulate',{'revision':2,'explicit_demo':True}).status_code in (403,404)
    simulated=mutate(doctor,'POST',endpoint+'/simulate',{'revision':2,'explicit_demo':True})
    assert simulated.status_code==200 and simulated.json['simulated'] is True and simulated.json['delivered'] is False
    with app.extensions['cc_session_factory']() as db:
        rows=db.scalars(select(PitchEscalationSimulation)).all()
        assert len(rows)==1 and rows[0].config_revision==2
        assert json.loads(rows[0].config_json)['delay_seconds']==120
        assert db.scalar(select(func.count()).select_from(UserNotification))==before


def test_pitch_requires_authenticated_explicit_synthetic_profile(app):
    assert app.test_client().get(PT+'/runs').status_code==401
    patient,_=login(app,'clinical_care')
    assert mutate(patient,'POST',PT+'/runs',{'patient_id':'pat_a'}).status_code==403
    disabled=create_app({**dict(app.config),'APP_ENV':'production','SEED_PATIENT_PERSONAS':False})
    assert disabled.test_client().get(PT+'/capabilities').json=={'enabled':False}
    # Synthetic password login is deliberately unavailable in this profile.
    assert disabled.test_client().get('/api/v1/onboarding/bootstrap').json['enabled'] is False
    assert disabled.test_client().get(PT+'/runs').status_code==404


def test_config_compare_and_swap_has_single_winner_under_real_sqlite_concurrency(app):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    patient,doctor,pid,run=setup(app)
    deteriorate(patient,doctor,pid)
    sid=progress(doctor,run)['signals'][0]['id']
    endpoint=PT+'/signals/'+sid+'/escalation'
    assert mutate(doctor,'PUT',endpoint,{'revision':0,'delay_seconds':None,'target_label':None}).status_code==200
    barrier=Barrier(2)
    def save_config(value):
        client=actor(app)
        barrier.wait()
        response=mutate(client,'PUT',endpoint,{'revision':1,'delay_seconds':value,'target_label':'Условная проверка гонки'})
        return response.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(save_config,[60,120]))
    assert sorted(statuses)==[200,409],statuses
    config=next(c for c in progress(doctor,run)['escalations'] if c['signal_id']==sid)
    assert config['revision']==2 and config['delay_seconds'] in (60,120)
