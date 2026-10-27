"""Flask-backed synthetic P0 and P1 security/functional regression tests.

Temporary SQLite per test; no real data, network or external AI providers.
Expected gaps are deliberately xfail, not success.
"""
from auth_support import login_response
import json
import pytest
from sqlalchemy import select
from cc_api import create_app
from cc_api.models import Alert, User
from cc_api.extension_models import Appointment
from cc_api.p0_models import UserNotification

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv('CC_DATABASE_URL',raising=False)
    monkeypatch.setenv('CC_AI_MODE','disabled')
    app=create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev','SECRET_KEY':'p0-live-isolated-only',
                    'DB_PATH':str(tmp_path/'p0.sqlite')})
    return app.test_client()

def login(c,uid):
    res=login_response(c,uid)
    assert res.status_code==200,res.get_json()
    return {'X-CSRF-Token':res.json['csrf_token']}

def send(c,path,body=None,headers=None):
    return c.post(path,json=body or {},headers=headers or {})

def require(response,code):
    assert response.status_code==code,(response.status_code,response.get_data(as_text=True)[:500])
    return response.get_json()

def test_p0_auth_capabilities_explicitly_not_implemented(client):
    caps=require(client.get('/api/v1/p0/auth/capabilities'),200)
    assert caps['registration_enabled'] is False
    assert caps['oidc_interactive_enabled'] is False
    assert caps['verified_staff_enrollment_enabled'] is False
    assert require(client.get('/api/v1/health'),200)['status']=='ok'
    assert client.get('/api/v1/auth/me').status_code==401

@pytest.mark.xfail(strict=True,reason='C03-C06: real email/professional verification deferred; local IdP proof is not production acceptance')
def test_blocked_c03_to_c06_real_enrollment(client):
    capabilities=require(client.get('/api/v1/p0/auth/capabilities'),200)
    assert capabilities['registration_enabled'] and capabilities['oidc_interactive_enabled'] and capabilities['verified_staff_enrollment_enabled']

def test_csrf_cookie_security_and_non_demo_boot_guard(client):
    h=login(client,'pat_01')
    assert send(client,'/api/v1/p0/adverse-events',{'description':'Synthetic only'}).status_code==403
    ok=send(client,'/api/v1/p0/adverse-events',{'description':'Synthetic only'},h)
    require(ok,201)
    for hdr in ('Cache-Control','X-Request-ID','X-Content-Type-Options'):
        assert hdr in ok.headers
    with pytest.raises(RuntimeError,match='CC_SECRET_KEY'):
        create_app({'DEMO_MODE':False,'SECRET_KEY':'UNSAFE_SYNTHETIC_DEMO_ONLY'})

def test_p0_care_plans_adherence_and_notifications_cross_role(client):
    hdoc=login(client,'doc_psy')
    b={'patient_id':'pat_a','items':[{'item_type':'behavioral','title':'Synthetic daily check-in','frequency':'daily'}]}
    created=require(send(client,'/api/v1/p0/care-plans',b,hdoc),201)
    assert created['status']=='draft' and created['publication_required'] is True
    h=login(client,'pat_01')
    assert require(client.get('/api/v1/p0/care-plans'),200)['items']==[]
    assert client.get(created['document_url']).status_code==404
    assert require(client.get('/api/v1/p0/notifications'),200)['items']==[]
    hdoc=login(client,'doc_psy')
    signed=require(send(client,created['document_url']+'/sign',{'revision':created['revision']},hdoc),200)
    assert signed['status']=='signed' and signed['published_at'] is None
    h=login(client,'pat_01')
    assert require(client.get('/api/v1/p0/care-plans'),200)['items']==[]
    assert client.get(created['document_url']).status_code==404
    assert require(client.get('/api/v1/p0/notifications'),200)['items']==[]
    hdoc=login(client,'doc_psy')
    published=require(send(client,created['document_url']+'/publish',{'revision':signed['revision']},hdoc),200)
    assert published['status']=='published' and published['published_at']
    h=login(client,'pat_01')
    plans=require(client.get('/api/v1/p0/care-plans'),200)['items']
    item=next(p for p in plans if p['id']==created['id'])['items'][0]
    require(send(client,'/api/v1/p0/plan-items/'+item['id']+'/report',{'outcome':'partial'},h),201)
    assert require(client.get('/api/v1/p0/care-plans'),200)['items'][0]['items'][0]['reports'][0]['outcome']=='partial'
    notes=require(client.get('/api/v1/p0/notifications'),200)['items']
    assert notes
    read=require(send(client,'/api/v1/p0/notifications/'+notes[0]['id']+'/read',{},h),200)
    assert read['read_at']
    h3=login(client,'pat_03')
    assert client.get('/api/v1/p0/care-plans').json['items']==[]
    require(send(client,'/api/v1/p0/notifications/'+notes[0]['id']+'/read',{},h3),404)
    hother=login(client,'doc_other')
    assert send(client,'/api/v1/p0/care-plans',b,hother).status_code==404

def test_p0_patient_adverse_event_clinician_review_and_data_minimization(client):
    h=login(client,'pat_01')
    created=require(send(client,'/api/v1/p0/adverse-events',{'description':'Synthetic discomfort'},h),201)
    assert created['causality']=='not_assessed'
    h=login(client,'doc_other')
    assert client.get('/api/v1/p0/adverse-events?patient_id=pat_a').status_code==404
    assert send(client,'/api/v1/p0/adverse-events/'+created['id']+'/review',{'status':'assessed','review_text':'No causality inferred'},h).status_code==404
    h=login(client,'doc_psy')
    d=require(client.get('/api/v1/p0/adverse-events?patient_id=pat_a'),200)
    assert any(x['id']==created['id'] for x in d['items'])
    require(send(client,'/api/v1/p0/adverse-events/'+created['id']+'/review',{'status':'assessed','review_text':'For clinician review only'},h),200)
    login(client,'pat_01')
    patient=require(client.get('/api/v1/p0/adverse-events'),200)['items']
    assert all('review_text' not in e for e in patient)

def test_p0_trends_history_encounter_signing_and_confirmed_decisions(client):
    h=login(client,'doc_psy')
    obs=require(client.get('/api/v1/p0/observations/pat_a'),200)
    assert 'items' in obs and 'missingness' in obs
    assert client.get('/api/v1/p0/observations/pat_b').status_code==404
    assert 'clinician_confirmed_diagnoses' in require(client.get('/api/v1/p0/history/pat_a'),200)
    enc=require(send(client,'/api/v1/p0/encounters/pat_a',{'mode':'quick','narrative':'Synthetic follow-up','sign':True},h),201)
    assert enc['status']=='signed'
    visits=require(client.get('/api/v1/p0/encounters/pat_a'),200)
    assert any(e['id']==enc['id'] and e['signed_at'] for e in visits['items'])
    no=send(client,'/api/v1/p0/decisions/pat_a',{'text':'Synthetic clinician decision'},h)
    assert no.status_code==422
    ok=require(send(client,'/api/v1/p0/decisions/pat_a',{'text':'Synthetic clinician decision','explicit_confirmation':True},h),201)
    assert any(d['id']==ok['id'] for d in client.get('/api/v1/p0/decisions/pat_a').json['items'])
    login(client,'pat_01')
    assert client.get('/api/v1/p0/encounters/pat_a').status_code==403

def test_p0_alert_assessment_and_replay(client):
    h=login(client,'doc_psy')
    info=require(client.get('/api/v1/p0/alerts/al_001'),200)
    assert 'signal_provenance' in info
    created=require(send(client,'/api/v1/p0/alerts/al_001/assess',{'status':'closed','assessment':'Synthetic manual assessment'},h),201)
    assert created['alert_status']=='closed'
    assert send(client,'/api/v1/p0/alerts/al_001/assess',{'status':'closed','assessment':'Repeat'},h).status_code==409
    login(client,'doc_other')
    assert client.get('/api/v1/p0/alerts/al_001').status_code==404

def test_p0_clinic_admin_appointments_patient_refs_no_pii(client):
    login(client,'clinic_01')
    for path in ['/api/v1/p0/clinic/appointments','/api/v1/p0/clinic/patients']:
        d=require(client.get(path),200)
        assert 'items' in d
        # Policy metadata may *name* restricted fields, but must never include
        # their values or serialize these fields inside returned patient rows.
        forbidden_keys={'diagnosis_label','medication_label','synthetic_contact',
                        'patient_email','review_text','patient_name','diagnosis',
                        'messages','notes','display_name'}
        for item in d['items']:
            assert forbidden_keys.isdisjoint(item), (path, item)
        actual_data=json.dumps(d['items'],ensure_ascii=False).lower()
        for secret in ('@example.invalid','алексей демонстрационный',
                       'синтетический случай','учебный препарат'):
            assert secret not in actual_data
        if 'restricted_fields' in d:
            assert set(d['restricted_fields']) >= {'patient_email','diagnosis'}
    refs=client.get('/api/v1/p0/clinic/patients').json['items']
    assert refs
    r=require(client.get('/api/v1/p0/clinic/patients/'+refs[0]['patient_ref']),200)
    assert r['clinical_record_access'] is False
    login(client,'pat_01')
    assert client.get('/api/v1/p0/clinic/patients').status_code==403
    login(client,'doc_other')
    assert client.get('/api/v1/p0/clinic/appointments').status_code==403

def test_p0_research_cohort_recompute_acl_and_suppression(client):
    h=login(client,'researcher_01')
    assert send(client,'/api/v1/p0/dataset-definitions',{'study_id':'study_demo_v1','measure':'synthetic_mood','cohorts':['A','A']},h).status_code==422
    created=require(send(client,'/api/v1/p0/dataset-definitions',{'study_id':'study_demo_v1','measure':'synthetic_mood','cohorts':['A','B']},h),201)
    data=require(client.get('/api/v1/p0/dataset-definitions/'+created['id']+'/compute'),200)
    assert len(data['items'])==2
    assert all(x['source']=='vetted_synthetic_observations' for x in data['items'])
    assert all(x['suppressed'] or x['n']>=5 for x in data['items'])
    assert 'study_subject' not in json.dumps(data)
    login(client,'pat_01')
    assert client.get('/api/v1/p0/dataset-definitions/'+created['id']+'/compute').status_code==403
    login(client,'clinic_01')
    assert client.get('/api/v1/research/export').status_code==403

def test_p0_summary_patient_edit_and_clinician_visibility(client,monkeypatch):
    monkeypatch.setenv('CC_AI_MODE','deterministic_mock')
    h=login(client,'pat_01')
    d=require(send(client,'/api/v1/ai/summary-drafts',{'recipient_doctor_id':'doc_psy'},h),201)
    got=require(client.get('/api/v1/p0/summary-drafts/'+d['id']),200)
    assert got['state']=='needs_review'
    upd=require(send(client,'/api/v1/p0/summary-drafts/'+d['id']+'/edit',{'content':'Reviewed synthetic draft'},h),200)
    assert upd['version']==1
    login(client,'doc_psy')
    assert client.get('/api/v1/doctors/me/ai-summaries').json['items']==[]
    h=login(client,'pat_01')
    require(send(client,'/api/v1/ai/summary-drafts/'+d['id']+'/approve',{'approve':True},h),200)
    assert send(client,'/api/v1/p0/summary-drafts/'+d['id']+'/edit',{'content':'Silent overwrite'},h).status_code==409
    login(client,'doc_psy')
    assert any(x['id']==d['id'] for x in client.get('/api/v1/doctors/me/ai-summaries').json['items'])
    login(client,'doc_other')
    assert client.get('/api/v1/doctors/me/ai-summaries').json['items']==[]

def test_blocked_clinician_structured_ai_approval(client):
    login(client,'doc_psy')
    response=client.get('/api/v1/p0/summary-proposals')
    assert response.status_code==200 and response.json['clinical_record_updated'] is False
    assert response.json['requires_explicit_field_review'] is True
    login(client,'pat_01')
    assert client.get('/api/v1/p0/summary-proposals').status_code==403

def test_p0_reference_catalog_empty_approved_only_and_roles(client):
    login(client,'doc_psy')
    d=require(client.get('/api/v1/p0/reference-articles'),200)
    assert 'items' in d
    assert all(item['approval_status']=='approved' for item in d['items'])
    assert client.get('/api/v1/p0/reference-articles/missing').status_code==404
    login(client,'pat_01')
    assert client.get('/api/v1/p0/reference-articles').status_code==403

@pytest.mark.xfail(strict=True,reason='D22-D23: no reviewed/licensed clinical content supplied')
def test_blocked_clinical_library_has_reviewed_material(client):
    login(client,'doc_psy')
    assert len(client.get('/api/v1/p0/reference-articles').json['items'])>0

def test_p0_previsit_request_appointment_and_clinic_visibility(client):
    h=login(client,'pat_03')
    case=require(send(client,'/api/v1/previsit-cases',{'doctor_id':'doc_psy','text':'Synthetic intake','case_consent':True},h),201)
    requested=require(send(client,'/api/v1/previsit-cases/'+case['id']+'/appointment-requests',{},h),201)
    assert requested['status']=='requested'
    login(client,'clinic_01')
    listed=client.get('/api/v1/p0/clinic/appointments').json['items']
    # Incoming appointments remain administratively visible, while their
    # patient projection has no contact fields or clinical access by default.
    entry=next(row for row in listed if row['appointment_id']==requested['id'])
    assert entry['patient']['fields']=={} and entry['patient']['contact_visible'] is False
    assert entry['patient']['clinical_record_access'] is False
    assert entry['patient']['patient_ref'] not in ('pat_c','pat_03')
    assert all('patient_user_id' not in x and 'intake' not in x for x in listed)
    scheduling=require(client.get('/api/v1/clinic-workflow/appointments'),200)['items']
    assert any(row['id']==requested['id'] and row['status']=='requested' for row in scheduling)
    assert all(not {'patient_id','patient_user_id','patient_ref','intake','diagnosis'}&row.keys() for row in scheduling)

def test_p1_scoped_staff_and_ready_p1_api_reuse(client):
    login(client,'clinic_01')
    d=require(client.get('/api/v1/p1/clinic/staff'),200)
    assert d['items'] and d['synthetic_only']
    assert all('verified_subject' not in x and 'synthetic_contact' not in x and isinstance(x.get('display_name'),str) for x in d['items'])
    assert all(x['user_ref']!='doc_other' for x in d['items'])
    assert client.get('/api/v1/audit/me').status_code==200
    login(client,'researcher_01')
    assert client.get('/api/v1/research/cohorts').status_code==200
    login(client,'doc_psy')
    clinical=require(client.get('/api/v1/doctors/me/patients/pat_a/clinical'),200)
    assert 'scope' in clinical
    assert client.get('/api/v1/appointments').status_code==200
    login(client,'pat_02')
    assert client.get('/api/v1/p1/clinic/staff').status_code==403

def test_p1_questionnaire_submitted_result_persists(client):
    h=login(client,'doc_psy')
    q=require(send(client,'/api/v1/instruments/assignments',{'patient_id':'pat_a','instrument_id':'GAD-7'},h),201)
    h=login(client,'pat_01')
    require(send(client,'/api/v1/instruments/assignments/'+q['id']+'/submit',{'scores':[0,1,2,0,1,2,0]},h),200)
    found=next(x for x in client.get('/api/v1/instruments/assignments').json['items'] if x['id']==q['id'])
    assert found['status']=='submitted'
    assert json.loads(found['response_json'])['total']==6
    login(client,'pat_02')
    assert all(x['id']!=q['id'] for x in client.get('/api/v1/instruments/assignments').json['items'])
