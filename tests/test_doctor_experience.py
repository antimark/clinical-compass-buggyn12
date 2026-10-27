"""Phase 4A real persisted signal, permission and physician review gates.

Synthetic deterministic rules are demonstrated, never clinical prediction evidence.
SQLite concurrency is a demo gate; PostgreSQL/Keycloak/MFA remain separate.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import select

from cc_api import create_app
from cc_api.models import DoctorPatientLink, User
from cc_api.extension_models import Audit
from test_onboarding import actor, mutate, register, issue, accept
from test_patient_experience import login, observation

DX='/api/v1/doctor-experience'


@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev',
        'SEED_PATIENT_PERSONAS':True,'SECRET_KEY':'phase4-isolated-tests',
        'DB_PATH':str(tmp_path/'doctor-experience.sqlite')})


def read(client,path='/dashboard'):
    response=client.get(DX+path)
    assert response.status_code==200,(path,response.json)
    return response.json


def patient_id(app,identity):
    with app.extensions['cc_session_factory']() as db:
        return db.get(User,identity['id']).patient_id


def deteriorate(app):
    patient,identity=login(app)
    ids=[]
    for suffix,value,stamp in [('before',5,'2026-04-01T10:00:00Z'),('after',1,'2026-04-02T10:00:00Z')]:
        response=observation(patient,'doctor-warning-'+suffix,value=value,observed_at=stamp)
        assert response.status_code==201,response.json
        ids.append(response.json['id'])
    return patient,patient_id(app,identity),ids


def own_signal(doctor,pid,ids):
    items=read(doctor)['warnings']
    matches=[s for s in items if s['patient_id']==pid and s['rule_version']=='wellbeing-decrease-2-v1'
        and {o['id'] for o in s['evidence']['observations']}==set(ids)]
    assert len(matches)==1,items
    return matches[0]


def priority(doctor,pid,revision=0,**extra):
    return mutate(doctor,'PUT',DX+'/patients/'+pid+'/priority',
        {'priority':3,'note':'Синтетический плановый приоритет врача','revision':revision,**extra})


def test_decrease_is_durable_explainable_idempotent_and_scale_specific(app):
    patient,pid,ids=deteriorate(app)
    doctor=actor(app)
    signal=own_signal(doctor,pid,ids)
    assert signal['kind']=='system_signal' and signal['status']=='open'
    assert signal['reason'] and signal['occurred_at'] and signal['source'] and signal['limitation']
    evidence=signal['evidence']['observations']
    assert [o['value'] for o in evidence]==[5,1]
    assert [o['observed_at'][:10] for o in evidence]==['2026-04-01','2026-04-02']
    assert all(o['unit']=='points' and o['scale_version']=='mood_1_5_v1' for o in evidence)
    assert own_signal(doctor,pid,ids)['id']==signal['id']
    # Incompatible scale and unit cannot create a new comparable decrease.
    assert observation(patient,'foreign-scale',value=0,scale_version='mood_0_10_v1',observed_at='2026-04-03T10:00:00Z').status_code==201
    assert observation(patient,'foreign-unit',metric_key='sleep',unit='hours',scale_version='sleep_hours_v1',value=0,observed_at='2026-04-04T10:00:00Z').status_code==201
    assert own_signal(doctor,pid,ids)['evidence']==signal['evidence']
    restarted=create_app(dict(app.config))
    assert own_signal(actor(restarted),pid,ids)['id']==signal['id']
    assert read(actor(restarted),'/signals/'+signal['id'])['evidence']==signal['evidence']


def test_patient_report_is_distinct_and_attributed(app):
    patient,identity=login(app)
    pid=patient_id(app,identity)
    response=mutate(patient,'POST','/api/v1/patients/me/check-ins',
        {'mood_score':3,'comparison':'same','note':'Синтетическое сообщение: прошу обсудить самочувствие'})
    assert response.status_code==201,response.json
    warnings=read(actor(app))['warnings']
    matches=[s for s in warnings if s['patient_id']==pid and s['kind']=='patient_report'
        and response.json['id'] in json.dumps(s['evidence'])]
    assert len(matches)==1
    assert matches[0]['occurred_at'] and matches[0]['source'] and matches[0]['reason']
    assert 'Синтетическое сообщение' in json.dumps(matches[0],ensure_ascii=False)


def test_manual_priority_cas_does_not_mutate_signals(app):
    _,pid,ids=deteriorate(app)
    doctor=actor(app)
    before=own_signal(doctor,pid,ids)
    row=next(p for p in read(doctor)['patients'] if p['id']==pid)
    response=priority(doctor,pid,row['priority_revision'])
    assert response.status_code==200,response.json
    current=next(p for p in read(doctor)['patients'] if p['id']==pid)
    assert current['physician_priority']==3 and current['priority_revision']==row['priority_revision']+1
    assert current['priority_note']=='Синтетический плановый приоритет врача'
    assert priority(doctor,pid,row['priority_revision'],priority=0).status_code==409
    assert own_signal(doctor,pid,ids)==before
    restarted=create_app(dict(app.config))
    saved=next(p for p in read(actor(restarted))['patients'] if p['id']==pid)
    assert saved['physician_priority']==3 and saved['priority_revision']==current['priority_revision']


def test_review_appends_history_and_audit_without_rewriting_evidence(app):
    _,pid,ids=deteriorate(app)
    doctor=actor(app)
    before=own_signal(doctor,pid,ids)
    with app.extensions['cc_session_factory']() as db:
        audit_before=len(db.scalars(select(Audit).where(Audit.object_id==before['id'])).all())
    for state in ('acknowledged','closed'):
        response=mutate(doctor,'POST',DX+'/signals/'+before['id']+'/review',
            {'status':state,'assessment':'Врач просмотрел синтетические исходные наблюдения: '+state})
        assert response.status_code==200,response.json
    detail=read(doctor,'/signals/'+before['id'])
    assert detail['status']=='closed' and detail['evidence']==before['evidence']
    assert len(detail['reviews'])==2
    assert [r['status'] for r in detail['reviews']]==['acknowledged','closed']
    with app.extensions['cc_session_factory']() as db:
        audit=db.scalars(select(Audit).where(Audit.object_id==before['id'])).all()
        assert len(audit)>=audit_before+2 and all(a.actor=='doc_psy' for a in audit)
    assert all(s['id']!=before['id'] for s in read(doctor)['warnings'])
    assert read(doctor,'/signals/'+before['id'])['evidence']==before['evidence']


@pytest.mark.parametrize('identity',['pat_01','doc_other','clinic_01','researcher_01','platform_01'])
def test_role_and_unlinked_physician_cannot_read_or_review_signal(app,identity):
    _,pid,ids=deteriorate(app)
    signal=own_signal(actor(app),pid,ids)
    other=actor(app,identity)
    assert other.get(DX+'/signals/'+signal['id']).status_code in (403,404)
    assert priority(other,pid).status_code in (403,404)
    assert mutate(other,'POST',DX+'/signals/'+signal['id']+'/review',
        {'status':'closed','assessment':'Unauthorized'}).status_code in (403,404)
    dashboard=other.get(DX+'/dashboard')
    if identity=='doc_other':
        assert dashboard.status_code==200
        assert pid not in json.dumps(dashboard.json)
    else:
        assert dashboard.status_code==403


def test_revoked_consent_filters_existing_events_before_serialization(app):
    patient,pid,ids=deteriorate(app)
    doctor=actor(app)
    signal=own_signal(doctor,pid,ids)
    assert mutate(patient,'DELETE','/api/v1/patients/me/clinical-links/doc_psy',{}).status_code==200
    assert doctor.get(DX+'/signals/'+signal['id']).status_code==404
    assert pid not in json.dumps(read(doctor))
    assert mutate(doctor,'POST',DX+'/signals/'+signal['id']+'/review',
        {'status':'closed','assessment':'No remaining grant'}).status_code==404
    assert priority(doctor,pid).status_code==404
    from cc_api.doctor_experience_models import DoctorSignal
    with app.extensions['cc_session_factory']() as db:
        assert db.get(DoctorSignal,signal['id']) is not None,'Revocation filters access without erasing history'


@pytest.mark.parametrize('change',['scope','tenant','ledger'])
def test_current_scope_tenant_and_consent_rechecked(app,change):
    _,pid,ids=deteriorate(app)
    doctor=actor(app)
    signal=own_signal(doctor,pid,ids)
    with app.extensions['cc_session_factory']() as db:
        if change=='scope':
            db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.doctor_id=='doc_psy',DoctorPatientLink.patient_id==pid)).categories='medications'
        elif change=='tenant':
            db.get(User,'doc_psy').organization_id='org_other'
        else:
            from cc_api.onboarding_models import PatientConsent
            consent=db.scalar(select(PatientConsent).where(PatientConsent.patient_user_id==db.scalar(select(User.id).where(User.patient_id==pid)),PatientConsent.doctor_id=='doc_psy'))
            consent.revoked_at='2026-05-01T10:00:00Z'
        db.commit()
    assert doctor.get(DX+'/signals/'+signal['id']).status_code==404
    assert not any(s['patient_id']==pid for s in read(doctor)['warnings'])
    assert priority(doctor,pid).status_code==404


def test_new_patient_empty_and_case_does_not_imply_clinical_access(app):
    patient=app.test_client()
    identity=register(patient,'phase4-new@qa.test')
    pid=patient_id(app,identity['user'])
    doctor=actor(app)
    assert pid not in json.dumps(read(doctor))
    invitation=issue(doctor,'phase4-new@qa.test')
    assert accept(patient,invitation).status_code==200
    row=next(p for p in read(doctor)['patients'] if p['id']==pid)
    assert row['open_signal_count']==0 and row['completed_questionnaire_count']==0
    assert row['latest_observed_at'] is None and row['nearest_appointment_at'] is None
    assert row['physician_priority']==0


@pytest.mark.parametrize('payload',[{'priority':True},{'priority':4},{'priority':-1},{'priority':'3'},
    {'revision':True},{'revision':-1},{'note':'x'*501},{'patient_id':'pat_b'}])
def test_priority_strict_payload_and_csrf(app,payload):
    _,pid,_=deteriorate(app)
    doctor=actor(app)
    assert priority(doctor,pid,**payload).status_code==422
    assert doctor.put(DX+'/patients/'+pid+'/priority',json={'priority':2,'revision':0}).status_code==403


def test_concurrent_manual_priority_has_single_cas_winner(app):
    _,pid,_=deteriorate(app)
    clients=[actor(app),actor(app)]
    row=next(p for p in read(clients[0])['patients'] if p['id']==pid)
    barrier=Barrier(2)
    def update(index):
        barrier.wait()
        return priority(clients[index],pid,row['priority_revision'],priority=index+1).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(update,range(2)))==[200,409]


def test_sort_filters_counters_and_search_reflect_real_rows(app):
    _,pid,ids=deteriorate(app)
    doctor=actor(app)
    own_signal(doctor,pid,ids)
    for ordering in ('attention','appointment','name','priority'):
        dashboard=read(doctor,'/dashboard?sort='+ordering)
        assert dashboard['sort']==ordering
        assert dashboard['counters']['patients']==len(dashboard['patients'])
        rows=dashboard['patients']
        if ordering=='attention':
            assert [r['open_signal_count'] for r in rows]==sorted((r['open_signal_count'] for r in rows),reverse=True)
        elif ordering=='priority':
            assert [r['physician_priority'] for r in rows]==sorted((r['physician_priority'] for r in rows),reverse=True)
        elif ordering=='appointment':
            dates=[r['nearest_appointment_at'] for r in rows if r['nearest_appointment_at']]
            assert dates==sorted(dates)
        else:
            names=[r['display_name'] for r in rows]
            assert names==sorted(names,key=str.casefold)
    assert all(row['open_signal_count']>0 for row in read(doctor,'/dashboard?filter=attention')['patients'])
    assert read(doctor,'/dashboard?q=zzzz-no-person')['patients']==[]
    assert doctor.get(DX+'/dashboard?sort=unsupported').status_code==422


def test_explicit_synthetic_gate_and_anonymous_denial(app):
    guest=app.test_client()
    assert guest.get(DX+'/dashboard').status_code==401
    assert read(guest,'/capabilities')['enabled'] is True
    disabled=create_app({**dict(app.config),'APP_ENV':'development','SEED_PATIENT_PERSONAS':False})
    assert read(disabled.test_client(),'/capabilities')['enabled'] is False
    # Synthetic password login is deliberately unavailable in this profile.
    assert disabled.test_client().get('/api/v1/onboarding/bootstrap').json['enabled'] is False
    assert disabled.test_client().get(DX+'/dashboard').status_code==403


def test_case_metadata_never_grants_chart_scope_and_expiry_withdrawal_filter(app):
    from cc_api.extension_models import PrevisitCase
    patient=app.test_client()
    identity=register(patient,'case-only-phase4@qa.test')
    uid=identity['user']['id']
    pid=patient_id(app,identity['user'])
    with app.extensions['cc_session_factory']() as db:
        for key,doctor,expiry,status in [
            ('case-visible','doc_psy','2999-01-01T00:00:00Z','submitted'),
            ('case-expired','doc_psy','2000-01-01T00:00:00Z','submitted'),
            ('case-withdrawn','doc_psy','2999-01-01T00:00:00Z','withdrawn'),
            ('case-other-doctor','doc_ther','2999-01-01T00:00:00Z','submitted')]:
            db.add(PrevisitCase(id=key,patient_user_id=uid,doctor_id=doctor,status=status,
                intake_json=json.dumps({'text':'PRIVATE CASE INTAKE'}),
                created_at='2026-01-01T00:00:00Z',allowed_until=expiry))
        db.commit()
    doctor=actor(app)
    dashboard=read(doctor)
    ids={case['id'] for case in dashboard['cases']}
    assert 'case-visible' in ids
    assert not {'case-expired','case-withdrawn','case-other-doctor'}&ids
    assert pid not in {row['id'] for row in dashboard['patients']}
    assert 'PRIVATE CASE INTAKE' not in json.dumps(dashboard)
    assert priority(doctor,pid).status_code==404
    assert doctor.get('/api/v1/patient-experience/physician/patients/'+pid+'/chart').status_code==404


def test_adverse_event_warning_requires_medication_scope_independently(app):
    from cc_api.p0_models import AdverseEvent
    patient,identity=login(app)
    pid=patient_id(app,identity)
    doctor=actor(app)
    with app.extensions['cc_session_factory']() as db:
        db.add(AdverseEvent(id='phase4-adverse-event',patient_id=pid,reporter_id=identity['id'],
            description='Синтетическая жалоба на переносимость',status='reported',
            created_at='2026-04-01T10:00:00Z'))
        db.commit()
    # Fixture originally grants symptoms only. Medical concerns are a separate scope.
    initial=read(doctor)
    assert 'phase4-adverse-event' not in json.dumps(initial)
    with app.extensions['cc_session_factory']() as db:
        link=db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.patient_id==pid,DoctorPatientLink.doctor_id=='doc_psy'))
        from cc_api.onboarding_models import PatientConsent
        ledger=db.scalar(select(PatientConsent).where(PatientConsent.patient_user_id==identity['id'],PatientConsent.doctor_id=='doc_psy'))
        link.categories='symptoms,medications'
        ledger.categories='symptoms,medications'
        db.commit()
    signals=[s for s in read(doctor)['warnings'] if 'phase4-adverse-event' in json.dumps(s['evidence'])]
    assert len(signals)==1
    signal=signals[0]
    assert signal['kind']=='patient_report' and signal['required_scope']=='medications'
    assert 'Синтетическая жалоба' in json.dumps(signal,ensure_ascii=False)
    with app.extensions['cc_session_factory']() as db:
        ledger=db.scalar(select(PatientConsent).where(PatientConsent.patient_user_id==identity['id'],PatientConsent.doctor_id=='doc_psy'))
        ledger.categories='symptoms'
        db.commit()
    assert doctor.get(DX+'/signals/'+signal['id']).status_code==404
    assert 'phase4-adverse-event' not in json.dumps(read(doctor))
