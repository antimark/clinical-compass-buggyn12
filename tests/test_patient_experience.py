"""Real SQLite/server Phase 3 gates. No mocked identity or clinical interpretation.

The database is reopened for restart checks. SQLite concurrency is demo evidence;
PostgreSQL and Keycloak acceptance remains separate.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select
from cc_api import create_app
from cc_api.models import DoctorPatientLink, User
from test_onboarding import bootstrap, mutate, register, actor, issue, accept

PX='/api/v1/patient-experience'
OB='/api/v1/onboarding'
PASSWORD='Synthetic-demo-pass-42'


@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev',
        'SEED_PATIENT_PERSONAS':True,'SECRET_KEY':'phase3-isolated-tests',
        'DB_PATH':str(tmp_path/'patient-experience.sqlite')})


def login(app,key='trend_one'):
    client=app.test_client()
    response=mutate(client,'POST',OB+'/login',{'email':key+'@demo.test','password':PASSWORD})
    assert response.status_code==200,response.json
    return client,response.json['user']


def get(client,path):
    response=client.get(PX+path)
    assert response.status_code==200,(path,response.json)
    return response.json


def assignments(client):
    return get(client,'/questionnaires/assignments')['items']


def detail(client,assignment):
    return get(client,'/questionnaires/assignments/'+assignment['id'])


def save(client,assignment,answers,revision=None,**extra):
    revision=detail(client,assignment)['draft']['revision'] if revision is None else revision
    return mutate(client,'PUT',PX+'/questionnaires/assignments/'+assignment['id']+'/draft',
        {'definition_version':assignment['definition_version'],'revision':revision,
         'answers':answers,'last_page':0,**extra})


def submit(client,assignment,key='completion',revision=None,**extra):
    revision=detail(client,assignment)['draft']['revision'] if revision is None else revision
    return mutate(client,'POST',PX+'/questionnaires/assignments/'+assignment['id']+'/submit',
        {'definition_version':assignment['definition_version'],'revision':revision,
         'idempotency_key':key,**extra})


def primary(client):
    series=get(client,'/observations')['series']
    return next((s for s in series if (s['metric_key'],s['unit'],s['scale_version'])==
                 ('wellbeing','points','mood_1_5_v1')),{'points':[],'point_count':0})


def observation(client,event_key=None,**extra):
    return mutate(client,'POST',PX+'/observations',{'metric_key':'wellbeing','unit':'points',
        'scale_version':'mood_1_5_v1','value':3,'event_key':uuid4().hex if event_key is None else event_key,**extra})


def test_personas_opt_in_and_new_account_really_empty(app):
    guest=app.test_client()
    personas=get(guest,'/personas')['items']
    keys={item['persona_key'] for item in personas}
    assert {'trend_one','trend_two','invited_empty',*[f'history_{n:02}' for n in range(1,13)]}<=keys
    assert PASSWORD not in json.dumps(personas)
    assert all(item['email'].endswith('@demo.test') for item in personas)
    register(guest,'empty-phase3@qa.test')
    dashboard=get(guest,'/dashboard')
    assert dashboard['state']=='empty'
    assert dashboard['series']==[] and dashboard['assignments']==[]
    assert dashboard['links']==[] and dashboard['plans']==[] and dashboard['appointments']==[]
    assert dashboard['published_notes']==[] and dashboard['case_count']==0
    chart=get(guest,'/chart')
    assert chart['timeline']==[] and chart['series']==[]
    assert all(section['items']==[] for section in chart['sections'])
    disabled=create_app({**dict(app.config),'SEED_PATIENT_PERSONAS':False})
    assert get(disabled.test_client(),'/capabilities')['personas_enabled'] is False
    assert disabled.test_client().get(PX+'/personas').status_code==403


@pytest.mark.parametrize('environment',['development','production'])
def test_experience_explicit_profile_only(app,environment):
    disabled=create_app({**dict(app.config),'APP_ENV':environment,'SEED_PATIENT_PERSONAS':False})
    client=disabled.test_client()
    assert client.get('/api/v1/onboarding/bootstrap').json['enabled'] is False
    assert get(client,'/capabilities')['enabled'] is False
    assert client.get(PX+'/dashboard').status_code==403
    assert observation(client).status_code==403


@pytest.mark.parametrize('persona,start',[('trend_one',1),('trend_two',2)])
def test_actual_one_two_three_observations_survive_logout_and_restart(app,persona,start):
    client,user=login(app,persona)
    original=primary(client)
    assert original['point_count']==start
    result=observation(client,'persist-'+persona,value=4,observed_at='2026-01-03T13:15:00+03:00')
    assert result.status_code==201,result.json
    current=primary(client)
    assert current['point_count']==start+1
    point=next(p for p in current['points'] if p['id']==result.json['id'])
    assert point['value']==4 and point['observed_at'].startswith('2026-01-03T10:15:00')
    assert primary(client)==current
    assert mutate(client,'POST',OB+'/logout',{}).status_code==200
    assert client.get(PX+'/dashboard').status_code==401
    renewed,_=login(app,persona)
    assert primary(renewed)==current
    restarted=create_app(dict(app.config))
    after_restart,identity=login(restarted,persona)
    assert identity['id']==user['id']
    assert primary(after_restart)==current, 'Seeding must never reset real persisted additions'


def test_metric_units_scales_duplicates_idempotency_and_legacy_projection(app):
    client,_=login(app)
    payload={'value':3,'observed_at':'2026-02-03T10:00:00Z'}
    first=observation(client,'once',**payload)
    assert first.status_code==201,first.json
    replay=observation(client,'once',**payload)
    assert replay.status_code==200 and replay.json['id']==first.json['id']
    assert observation(client,'once',**{**payload,'value':4}).status_code==409
    assert observation(client,'duplicate',**{**payload,'value':5}).status_code==201
    observations=primary(client)
    assert observations['point_count']==2 and observations['duplicate_count']==1
    same=[p for p in observations['points'] if p['observed_at'].startswith('2026-02-03T10:00:00')]
    assert len(same)==1 and same[0]['value']==5
    assert observation(client,'scale',scale_version='mood_0_10_v1',value=8).status_code==201
    assert observation(client,'unit',metric_key='sleep',unit='hours',scale_version='sleep_hours_v1',value=7).status_code==201
    triples={(s['metric_key'],s['unit'],s['scale_version']) for s in get(client,'/observations')['series']}
    assert {('wellbeing','points','mood_1_5_v1'),('wellbeing','points','mood_0_10_v1'),('sleep','hours','sleep_hours_v1')}<=triples
    legacy=mutate(client,'POST','/api/v1/patients/me/check-ins',{'mood_score':2,'comparison':'same','note':'Synthetic legacy observation'})
    assert legacy.status_code==201,legacy.json
    assert any(p['id']==legacy.json['id'] and p['value']==2 for p in primary(client)['points'])


@pytest.mark.parametrize('changes',[{'value':True},{'value':0},{'value':6},{'value':'3'},
    {'unit':'hours'},{'scale_version':'unknown'},{'patient_id':'pat_a'},
    {'observed_at':'2026-01-01T12:00:00'},{'observed_at':'2999-01-01T00:00:00Z'},
    {'event_key':''},{'value':float('inf')}])
def test_observation_invalid_payload_does_not_persist(app,changes):
    client,_=login(app)
    before=primary(client)
    assert observation(client,**changes).status_code==422
    assert primary(client)==before


def test_draft_each_answer_cas_privacy_and_resumption(app):
    client,user=login(app,'trend_two')
    assignment=next(a for a in assignments(client) if a['definition_id']=='demo_15_v1')
    initial=detail(client,assignment)
    assert initial['definition']['pages']==[10,5]
    assert initial['draft']['answers']=={'q1':2,'q2':3}
    revision=initial['draft']['revision']
    saved=save(client,assignment,{'q3':4},revision,last_page=1)
    assert saved.status_code==200,saved.json
    restored=detail(client,assignment)['draft']
    assert restored['answers']=={'q1':2,'q2':3,'q3':4} and restored['last_page']==1
    assert restored['revision']==revision+1
    assert save(client,assignment,{'q3':1},revision).status_code==409
    doctor=actor(app)
    doctor_list=get(doctor,'/questionnaires/assignments')['items']
    row=next(a for a in doctor_list if a['id']==assignment['id'])
    assert not {'draft','answers','revision','last_page','total'}&row.keys()
    assert doctor.get(PX+'/questionnaires/assignments/'+assignment['id']).status_code in (403,404)
    restarted=create_app(dict(app.config))
    renewed,_=login(restarted,'trend_two')
    assert detail(renewed,assignment)['draft']==restored


@pytest.mark.parametrize('changes',[{'answers':{'q0':1}},{'answers':{'q11':1}},
    {'answers':{'q1':True}},{'answers':{'q1':0}},{'answers':{'q1':5}},
    {'answers':{'q1':'1'}},{'last_page':1},{'last_page':-1},
    {'definition_version':'unknown'},{'revision':True},{'patient_id':'pat_b'}])
def test_draft_strict_types_and_version(app,changes):
    client,_=login(app)
    assignment=assignments(client)[0]
    before=detail(client,assignment)['draft']
    payload={'answers':{'q1':2},**changes}
    assert save(client,assignment,**payload).status_code==422
    assert detail(client,assignment)['draft']==before


def assign(doctor,patient_id,definition_id):
    response=mutate(doctor,'POST',PX+'/questionnaires/assignments',{'patient_id':patient_id,'definition_id':definition_id})
    assert response.status_code==201,response.json
    return response.json


@pytest.mark.parametrize('definition,count,value,expected',[
    ('demo_10_v1',10,1,10),('demo_10_v1',10,4,40),('demo_15_v1',15,1,15),('demo_15_v1',15,4,60)])
def test_server_exact_score_boundaries_and_immutable_result(app,definition,count,value,expected):
    client,user=login(app)
    with app.extensions['cc_session_factory']() as db:
        patient_id=db.get(User,user['id']).patient_id
    doctor=actor(app)
    assignment=assign(doctor,patient_id,definition)
    assert submit(client,assignment).status_code==422
    assert save(client,assignment,{f'q{i}':value for i in range(1,count+1)}).status_code==200
    revision=detail(client,assignment)['draft']['revision']
    result=submit(client,assignment,revision=revision)
    assert result.status_code in (200,201),result.json
    body=result.json
    assert body['score']==expected and body['min_score']==count and body['max_score']==count*4
    assert len(body['answers'])==count and all(answer['value']==value and answer['label'] for answer in body['answers'])
    assert body['status']=='submitted' and 'Не является медицинской оценкой' in body['disclaimer']
    assert submit(client,assignment,revision=revision).json==body
    assert submit(client,assignment,'other-key',revision=revision).status_code==409
    assert save(client,assignment,{'q1':2},revision).status_code==409
    assert get(client,'/questionnaires/assignments/'+assignment['id']+'/result')==body
    assert get(doctor,'/questionnaires/assignments/'+assignment['id']+'/result')==body
    restarted=create_app(dict(app.config))
    renewed,_=login(restarted)
    assert get(renewed,'/questionnaires/assignments/'+assignment['id']+'/result')==body
    assert submit(renewed,assignment,'client-total',revision=revision,score=999).status_code==422


def test_acl_own_role_tenant_revocation_and_private_drafts(app):
    patient,user=login(app)
    with app.extensions['cc_session_factory']() as db:
        patient_id=db.get(User,user['id']).patient_id
    doctor=actor(app)
    assignment=assignments(patient)[0]
    assert save(patient,assignment,{f'q{i}':2 for i in range(1,11)}).status_code==200
    result=submit(patient,assignment)
    assert result.status_code in (200,201),result.json
    route='/questionnaires/assignments/'+assignment['id']+'/result'
    chart='/physician/patients/'+patient_id+'/chart'
    assert get(doctor,route)['score']==20
    for identity in ('pat_02','doc_other','clinic_01','researcher_01','platform_01'):
        other=actor(app,identity)
        assert other.get(PX+route).status_code in (403,404)
        assert other.get(PX+chart).status_code in (403,404)
        assert other.get(PX+'/questionnaires/assignments/'+assignment['id']).status_code in (403,404)
    assert patient.get(PX+chart).status_code in (403,404)
    # A second currently authorized treating physician may see only the final result.
    with app.extensions['cc_session_factory']() as db:
        db.add(DoctorPatientLink(doctor_id='doc_ther',patient_id=patient_id,categories='symptoms'))
        db.commit()
    second=actor(app,'doc_ther')
    assert get(second,route)['score']==20
    assert second.get(PX+'/questionnaires/assignments/'+assignment['id']).status_code in (403,404)
    with app.extensions['cc_session_factory']() as db:
        link=db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.doctor_id=='doc_psy',DoctorPatientLink.patient_id==patient_id))
        link.categories='medications'
        db.commit()
    assert doctor.get(PX+route).status_code in (403,404)
    assert doctor.get(PX+chart).status_code in (403,404)
    with app.extensions['cc_session_factory']() as db:
        db.get(User,'doc_ther').organization_id='org_foreign'
        db.commit()
    assert second.get(PX+route).status_code in (403,404)
    assert second.get(PX+chart).status_code in (403,404)
    assert get(patient,route)['score']==20


def test_concurrent_draft_compare_and_swap_and_final_submission(app):
    patient,_=login(app)
    assignment=assignments(patient)[0]
    clients=[login(app)[0] for _ in range(2)]
    revision=detail(patient,assignment)['draft']['revision']
    barrier=Barrier(2)
    def update(index):
        barrier.wait()
        return save(clients[index],assignment,{'q1':index+1},revision).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(update,range(2)))==[200,409]
    assert detail(patient,assignment)['draft']['revision']==revision+1
    assert save(patient,assignment,{f'q{i}':3 for i in range(1,11)}).status_code==200
    revision=detail(patient,assignment)['draft']['revision']
    barrier=Barrier(2)
    def finish(index):
        barrier.wait()
        response=submit(clients[index],assignment,'same-concurrent-key',revision)
        return response.status_code,response.json
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(finish,range(2)))
    assert all(status in (200,201) for status,_ in results),results
    assert results[0][1]==results[1][1]
    assert get(patient,'/questionnaires/assignments/'+assignment['id']+'/result')['score']==30


def test_chart_publication_scope_and_real_consent_revocation(app):
    patient=app.test_client()
    register(patient,'chart-publication@qa.test')
    doctor=actor(app)
    invitation=issue(doctor,'chart-publication@qa.test')
    created=mutate(doctor,'POST',OB+'/invitations/'+invitation['id']+'/drafts',{'content':'Synthetic note awaiting physician release'})
    assert created.status_code==201,created.json
    draft=created.json
    assert 'Synthetic note' not in json.dumps(get(patient,'/chart'))
    assert accept(patient,invitation).status_code==200
    assert 'Synthetic note' not in json.dumps(get(patient,'/chart'))
    signed=mutate(doctor,'POST',OB+'/drafts/'+draft['id']+'/sign',{'confirmation':True,'version':draft['version']})
    assert signed.status_code==200,signed.json
    assert 'Synthetic note' not in json.dumps(get(patient,'/chart'))
    published=mutate(doctor,'POST',OB+'/drafts/'+draft['id']+'/publish',{'confirmation':True,'version':signed.json['version']})
    assert published.status_code==200,published.json
    assert 'Synthetic note awaiting physician release' in json.dumps(get(patient,'/chart'))
    uid=patient.get('/api/v1/auth/me').json['user']['id']
    with app.extensions['cc_session_factory']() as db:
        patient_id=db.get(User,uid).patient_id
    assert 'Synthetic note' in json.dumps(get(doctor,'/physician/patients/'+patient_id+'/chart'))
    revoked=mutate(patient,'DELETE','/api/v1/patients/me/clinical-links/doc_psy',{})
    assert revoked.status_code==200,revoked.json
    assert 'Synthetic note' not in json.dumps(get(patient,'/chart'))
    assert doctor.get(PX+'/physician/patients/'+patient_id+'/chart').status_code==404


def test_submit_and_draft_update_cannot_commit_inconsistent_result(app):
    patient,_=login(app)
    assignment=assignments(patient)[0]
    assert save(patient,assignment,{f'q{i}':1 for i in range(1,11)}).status_code==200
    revision=detail(patient,assignment)['draft']['revision']
    clients=[login(app)[0] for _ in range(2)]
    barrier=Barrier(2)
    def race(index):
        barrier.wait()
        response=(submit(clients[index],assignment,'submit-save-race',revision) if index==0
                  else save(clients[index],assignment,{'q1':4},revision))
        return response.status_code,response.json
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(race,range(2)))
    submitted,updated=results
    assert submitted[0] in (200,201,409) and updated[0] in (200,409),results
    assert (submitted[0] in (200,201)) != (updated[0]==200),results
    result=patient.get(PX+'/questionnaires/assignments/'+assignment['id']+'/result')
    if submitted[0] in (200,201):
        assert result.status_code==200 and result.json['score']==10
        assert result.json['answers'][0]['value']==1
    else:
        assert result.status_code in (404,409)
        assert detail(patient,assignment)['draft']['answers']['q1']==4


def test_definitions_technical_demo_and_csrf_boundaries(app):
    guest=app.test_client()
    assert guest.get(PX+'/questionnaires/definitions').status_code==401
    patient,_=login(app)
    definitions=get(patient,'/questionnaires/definitions')['items']
    assert {'demo_10_v1','demo_15_v1'}.issubset({d['id'] for d in definitions})
    assert {d['id'] for d in definitions if d['status']=='evaluation_draft_unapproved'} == {'eval_phq_9_v1','eval_phq_2_v1','eval_gad_7_v1','eval_gad_2_v1'}
    for definition in (d for d in definitions if d['status']=='synthetic_demo'):
        count=10 if definition['id']=='demo_10_v1' else 15
        assert definition['pages']==([10] if count==10 else [10,5])
        assert len(definition['questions'])==count
        assert {q['id'] for q in definition['questions']}=={f'q{i}' for i in range(1,count+1)}
        assert definition['options']==[1,2,3,4]
        assert definition['status']=='synthetic_demo'
        assert 'Не является медицинской оценкой' in definition['disclaimer']
        assert not {'diagnosis','thresholds','interpretation'}&definition.keys()
    assert patient.post(PX+'/observations',json={'metric_key':'wellbeing','unit':'points',
        'scale_version':'mood_1_5_v1','value':2,'event_key':'missing-csrf'}).status_code==403
    for user in ('clinic_01','researcher_01','platform_01'):
        assert actor(app,user).get(PX+'/questionnaires/definitions').status_code==403


@pytest.mark.parametrize('missing',['signed_at','published_at'])
def test_published_flag_without_timestamp_never_releases_note(app,missing):
    from cc_api.onboarding_models import PreparedOnboardingDraft
    patient=app.test_client()
    register(patient,'timestamps@qa.test')
    doctor=actor(app)
    invitation=issue(doctor,'timestamps@qa.test')
    assert accept(patient,invitation).status_code==200
    with app.extensions['cc_session_factory']() as db:
        db.add(PreparedOnboardingDraft(id='malformed-release',invitation_id=invitation['id'],
            clinician_id='doc_psy',content='Synthetic withheld timestamp content',state='published',
            version=3,created_at='2026-01-01T00:00:00Z',
            signed_at=None if missing=='signed_at' else '2026-01-01T00:01:00Z',
            published_at=None if missing=='published_at' else '2026-01-01T00:02:00Z'))
        db.commit()
    assert 'Synthetic withheld timestamp content' not in json.dumps(get(patient,'/chart'))
    assert patient.get(OB+'/records').json['items']==[]


def test_assignment_current_grant_and_completed_snapshot(app):
    patient,user=login(app)
    with app.extensions['cc_session_factory']() as db:
        patient_id=db.get(User,user['id']).patient_id
    doctor=actor(app)
    path=PX+'/questionnaires/assignments'
    for identity in ('pat_01','doc_other','clinic_01','researcher_01','platform_01'):
        unauthorized=actor(app,identity)
        response=mutate(unauthorized,'POST',path,{'patient_id':patient_id,'definition_id':'demo_10_v1'})
        assert response.status_code in (403,404),response.json
    assignment=assign(doctor,patient_id,'demo_10_v1')
    assert save(patient,assignment,{f'q{i}':2 for i in range(1,11)}).status_code==200
    original=submit(patient,assignment).json
    # Versioned immutable snapshot is the result's source, even if a definition row
    # is altered out of band. HTTP has no mutation endpoint for these definitions.
    from cc_api.patient_experience_models import DemoQuestionnaireDefinition
    with app.extensions['cc_session_factory']() as db:
        definition=db.get(DemoQuestionnaireDefinition,'demo_10_v1')
        altered=json.loads(definition.definition_json)
        altered['questions'][0]['label']='Out-of-band changed wording'
        definition.definition_json=json.dumps(altered)
        db.commit()
    assert get(patient,'/questionnaires/assignments/'+assignment['id']+'/result')==original
    assert mutate(patient,'DELETE','/api/v1/patients/me/clinical-links/doc_psy',{}).status_code==200
    assert doctor.get(PX+'/questionnaires/assignments/'+assignment['id']+'/result').status_code==404
    assert mutate(doctor,'POST',path,{'patient_id':patient_id,'definition_id':'demo_10_v1'}).status_code==404
    assert get(patient,'/questionnaires/assignments/'+assignment['id']+'/result')==original


def test_duplicate_projection_uses_utc_instant_and_microsecond_recording_order(app):
    from cc_api.patient_experience_models import MetricObservation
    patient,user=login(app)
    with app.extensions['cc_session_factory']() as db:
        patient_id=db.get(User,user['id']).patient_id
        for suffix,value,observed,recorded in [
            ('earlier',1,'2026-03-01T12:00:00+02:00','2026-03-01T10:01:00Z'),
            ('later',4,'2026-03-01T10:00:00Z','2026-03-01T10:01:00.000001Z')]:
            db.add(MetricObservation(id='obs_time_'+suffix,patient_id=patient_id,
                metric_key='wellbeing',unit='points',scale_version='mood_1_5_v1',value=value,
                observed_at=observed,recorded_at=recorded,source='synthetic_fixture',event_key='time_'+suffix))
        db.commit()
    projected=primary(patient)
    assert projected['duplicate_count']==1 and projected['point_count']==2
    selected=[p for p in projected['points'] if p['id'].startswith('obs_time_')]
    assert len(selected)==1 and selected[0]['id']=='obs_time_later' and selected[0]['value']==4
