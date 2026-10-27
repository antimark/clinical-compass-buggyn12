"""Phase 5 actual Flask boundaries; SQLite is distinct from real-PG gate."""
import hashlib,json
import pytest
from sqlalchemy import select,func
from cryptography.fernet import Fernet
from cc_api import create_app
from cc_api.models import User
from test_onboarding import actor,mutate,register,PASSWORD
from test_patient_experience import login
from test_clinical_workflow import create,transition,CW

AP='/api/v1/admin-privacy'
RW='/api/v1/research-workflow'
CR='/api/v1/clinical-review'

@pytest.fixture
def app(tmp_path,monkeypatch):
    monkeypatch.setenv('CC_PII_ENCRYPTION_KEY',Fernet.generate_key().decode())
    return create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev','SEED_PATIENT_PERSONAS':True,
        'SECRET_KEY':'phase5-acceptance-tests','DB_PATH':str(tmp_path/'acceptance.sqlite')})

def good(response,status=200):
    assert response.status_code==status,response.json
    return response.json

def privacy_setup(app):
    patient,user=login(app,'clinical_care')
    platform,admin=actor(app,'platform_01'),actor(app,'clinic_01')
    template=good(mutate(platform,'POST',AP+'/templates',{'organization_id':'org_demo','template_key':'qa_contact','version':1,'read_fields':['first_name']}),201)
    good(mutate(patient,'PUT',AP+'/me/values',{'fields':{'first_name':'СИНТЕТИЧЕСКОЕ_ИМЯ','phone':'+70000000001'}}))
    policy=good(mutate(patient,'PUT',AP+'/me/policies/org_demo',{'template_id':template['id'],'confirmed':True,'revision':0}))
    return patient,user,platform,admin,template,policy

def enable(platform):
    for org in (None,'org_demo'):good(mutate(platform,'PATCH',AP+'/flags',{'organization_id':org,'enabled':True}))

def own_projection(admin,user):
    from cc_api.admin_privacy_service import patient_ref
    ref=patient_ref('phase5-acceptance-tests','org_demo',user['patient_id'])
    return admin.get(AP+'/patients/'+ref)


def test_admin_projection_two_flags_allowlist_encryption_and_no_core_fallback(app):
    from cc_api.admin_privacy_models import AdminPrivacyValue
    patient,user,platform,admin,template,policy=privacy_setup(app)
    assert good(own_projection(admin,user))['fields']=={}
    good(mutate(platform,'PATCH',AP+'/flags',{'organization_id':None,'enabled':True}))
    assert good(own_projection(admin,user))['fields']=={}
    good(mutate(platform,'PATCH',AP+'/flags',{'organization_id':'org_demo','enabled':True}))
    result=good(own_projection(admin,user))
    assert result['fields']=={'first_name':'СИНТЕТИЧЕСКОЕ_ИМЯ'} and result['clinical_record_access'] is False
    assert user['display_name'] not in json.dumps(result,ensure_ascii=False)
    assert 'patient_id' not in result and 'user_id' not in result
    with app.extensions['cc_session_factory']() as db:
        stored=db.scalars(select(AdminPrivacyValue).where(AdminPrivacyValue.patient_user_id==user['id'])).all()
        assert len(stored)==2 and all('СИНТЕТИЧЕСКОЕ_ИМЯ' not in row.ciphertext and '+70000000001' not in row.ciphertext for row in stored)
    bad=mutate(platform,'POST',AP+'/templates',{'organization_id':'org_demo','template_key':'bad','version':1,'read_fields':['diagnosis']})
    assert bad.status_code==422
    assert own_projection(admin,user).headers['Cache-Control']=='no-store'


def test_projection_applied_before_filter_export_and_requested_fields(app):
    patient,user,platform,admin,template,policy=privacy_setup(app);enable(platform)
    assert good(admin.get(AP+'/patients?filter_field=phone&filter_value=%2B70000000001'))['total']==0
    found=good(admin.get(AP+'/patients/export?filter_field=first_name&filter_value=СИНТЕТИЧЕСКОЕ_ИМЯ'))
    assert found['total']==1 and found['items'][0]['fields']=={'first_name':'СИНТЕТИЧЕСКОЕ_ИМЯ'}
    hidden=good(admin.get(AP+'/patients?fields=phone'))
    assert all(item['fields']=={} for item in hidden['items'])
    assert '+70000000001' not in json.dumps(good(admin.get(AP+'/patients/export')))


def test_patient_policy_explicit_confirmation_cas_override_expiry_and_withdrawal(app):
    from cc_api.admin_privacy_models import AdminPrivacyOverride
    patient,user,platform,admin,template,policy=privacy_setup(app);enable(platform)
    assert mutate(patient,'PUT',AP+'/me/policies/org_demo',{'template_id':template['id'],'confirmed':False,'revision':1}).status_code==422
    override=AP+'/me/policies/org_demo/overrides/phone'
    assert mutate(patient,'PUT',override,{'effect':'ALLOW','revision':0}).status_code==409
    good(mutate(patient,'PUT',override,{'effect':'ALLOW','expires_at':'2999-01-01T00:00:00Z','revision':1}))
    assert good(own_projection(admin,user))['fields']['phone']=='+70000000001'
    with app.extensions['cc_session_factory'].begin() as db:
        db.get(AdminPrivacyOverride,(user['id'],'org_demo','phone')).expires_at='2000-01-01T00:00:00Z'
    assert good(own_projection(admin,user))['fields']=={'first_name':'СИНТЕТИЧЕСКОЕ_ИМЯ'}
    good(mutate(patient,'DELETE',AP+'/me/policies/org_demo',{}))
    assert good(own_projection(admin,user))['fields']=={}


def test_admin_reads_fail_closed_external_key_and_current_consent(app,monkeypatch):
    patient,user,platform,admin,template,policy=privacy_setup(app)
    monkeypatch.delenv('CC_PII_ENCRYPTION_KEY')
    assert good(own_projection(admin,user))['fields']=={}
    enable(platform)
    assert own_projection(admin,user).status_code==503
    good(mutate(patient,'DELETE','/api/v1/patients/me/clinical-links/doc_psy',{}))
    assert own_projection(admin,user).status_code==404
    good(mutate(patient,'DELETE',AP+'/me/policies/org_demo',{}))


@pytest.mark.parametrize('identity',['doc_psy','pat_01','researcher_01','platform_01'])
def test_admin_projection_cannot_be_obtained_by_other_roles(app,identity):
    assert actor(app,identity).get(AP+'/patients/export').status_code==403


def test_administrative_fields_do_not_grant_clinical_access_or_cross_tenant(app):
    from cc_api.admin_privacy_service import patient_ref
    patient,user,platform,admin,template,policy=privacy_setup(app);enable(platform)
    assert admin.get(CW+'/patients/'+user['patient_id']+'/documents').status_code==403
    ref=patient_ref('phase5-acceptance-tests','org_demo','pat_b')
    assert admin.get(AP+'/patients/'+ref).status_code==404
    assert mutate(admin,'PATCH',AP+'/flags',{'organization_id':None,'enabled':True}).status_code==403
    assert mutate(admin,'PUT',AP+'/me/values',{'fields':{'first_name':'FORBIDDEN'}}).status_code==403


def definition(researcher,**extra):
    response=mutate(researcher,'POST',RW+'/definitions',{'study_id':'study_demo_v1','measure':'synthetic_mood','cohorts':['A','B'],**extra})
    return good(response,201)

def second_researcher(app):
    # Coordinator-approved fixture: change the role of an existing explicit dev
    # identity ONLY in this ephemeral test DB. The actual dev provider then reads
    # persisted role; authentication and the study grant are never patched.
    with app.extensions['cc_session_factory'].begin() as db:
        row=db.get(User,'doc_ther');row.role='researcher';row.display_name='Синтетический второй исследователь'
        row.organization_id='org_demo'
    client=actor(app,'doc_ther')
    good(mutate(actor(app,'platform_01'),'POST',RW+'/grants',{'researcher_id':'doc_ther','study_id':'study_demo_v1','active':True}))
    return client,{'id':'doc_ther'}


def test_research_actual_aggregate_missingness_no_subjects_and_version_pinned_cache(app):
    from cc_api.extension_models import ResearchObservation
    researcher=actor(app,'researcher_01');d=definition(researcher)
    original=good(researcher.get(RW+'/definitions/'+d['id']+'/compute'))
    assert all(row['n']==12 and row['observed_n']==10 and row['missing_n']==2 for row in original['items'])
    assert 'study_subject' not in json.dumps(original) and 'patient_id' not in json.dumps(original)
    revised=good(mutate(researcher,'PUT',RW+'/definitions/'+d['id'],{**d['definition'],'revision':1,'cohorts':['A']}))
    assert revised['version']==2
    assert good(researcher.get(RW+'/definitions/'+d['id']+'/compute?version=1'))==original
    assert mutate(researcher,'PUT',RW+'/definitions/'+d['id'],{**d['definition'],'revision':1}).status_code==409
    assert len(good(researcher.get(RW+'/definitions/'+d['id']+'/versions'))['items'])==2
    assert researcher.get(RW+'/definitions/'+d['id']+'/export').headers['Cache-Control']=='no-store'
    with app.extensions['cc_session_factory'].begin() as db:
        old=db.get(ResearchObservation,'obs_A0')
        db.add(ResearchObservation(id='qa_latest',study_id=old.study_id,study_subject=old.study_subject,cohort='A',measure=old.measure,value=None,source='synthetic',recorded_at='2026-10-19T10:00:00Z'))
    assert good(researcher.get(RW+'/definitions/'+d['id']+'/compute?version=1'))==original


def test_research_latest_before_criteria_and_across_users_differencing_guard(app):
    from cc_api.extension_models import ResearchObservation
    r1=actor(app,'researcher_01');baseline=definition(r1,cohorts=['A'],criteria={'include':['observed_value']})
    first=good(r1.get(RW+'/definitions/'+baseline['id']+'/compute'))
    assert first['items'][0]['n']==10
    with app.extensions['cc_session_factory'].begin() as db:
        source=db.get(ResearchObservation,'obs_A0')
        db.add(ResearchObservation(id='qa_new_missing',study_id=source.study_id,study_subject=source.study_subject,cohort='A',measure=source.measure,value=None,source='synthetic',recorded_at='2026-10-19T10:00:00Z'))
    r2,_=second_researcher(app)
    d=definition(r2,cohorts=['A'],criteria={'include':['observed_value']})
    result=good(r2.get(RW+'/definitions/'+d['id']+'/compute'))['items'][0]
    assert result['suppression_reason']=='differencing_guard'
    assert all(result[key] is None for key in ('n','observed_n','missing_n','mean'))
    assert r2.get(RW+'/definitions/'+baseline['id']).status_code==404


def test_research_grant_revocation_blocks_cached_exports_and_restart_does_not_restore(app):
    researcher=actor(app,'researcher_01');d=definition(researcher)
    good(researcher.get(RW+'/definitions/'+d['id']+'/export'))
    good(mutate(actor(app,'platform_01'),'POST',RW+'/grants',{'researcher_id':'researcher_01','study_id':'study_demo_v1','active':False}))
    assert researcher.get(RW+'/definitions/'+d['id']+'/export').status_code==404
    assert researcher.get(RW+'/definitions').json['items']==[]
    restarted=create_app(dict(app.config))
    assert actor(restarted,'researcher_01').get(RW+'/definitions/'+d['id']+'/compute').status_code==404


@pytest.mark.parametrize('payload',[{'min_cell':4},{'start_date':'invalid'},{'criteria':{'include':['invented_diagnosis']}},{'cohorts':['A','A']}])
def test_research_validation_never_silently_ignores_query_filters(app,payload):
    response=mutate(actor(app,'researcher_01'),'POST',RW+'/definitions',{'study_id':'study_demo_v1','measure':'synthetic_mood','cohorts':['A'],**payload})
    assert response.status_code==422,response.json


def shared_draft(app):
    from cc_api.extension_models import AISummaryDraft
    patient,user=login(app,'clinical_care')
    with app.extensions['cc_session_factory'].begin() as db:
        db.add(AISummaryDraft(id='qa_shared_fields',patient_user_id=user['id'],recipient_doctor_id='doc_psy',content='Синтетический проверенный пациентом текст',state='approved_for_recipient',created_at='2026-10-19T00:00:00Z'))
    return patient,user,actor(app)


def test_summary_fields_explicit_review_cas_history_does_not_create_medical_record(app):
    from cc_api.p0_models import ClinicalDecision
    from cc_api.clinical_workflow_models import ClinicalDocument
    patient,user,doctor=shared_draft(app)
    with app.extensions['cc_session_factory']() as db:
        before=(db.scalar(select(func.count()).select_from(ClinicalDecision)),db.scalar(select(func.count()).select_from(ClinicalDocument)))
    path=CR+'/summary-drafts/qa_shared_fields/fields'
    assert mutate(patient,'POST',path,{'source_version':9,'fields':[{'key':'concern','label':'Жалоба','value':'Синтетическое сообщение'}]}).status_code==409
    fields=good(mutate(patient,'POST',path,{'source_version':1,'fields':[{'key':'concern','label':'Жалоба со слов пациента','value':'Синтетическое сообщение'}]}),201)
    assert fields['clinical_record_updated'] is False
    item=fields['items'][0];endpoint=CR+'/fields/'+item['id']+'/review'
    assert item['status']=='pending' and item['reviewer_id'] is None
    assert mutate(patient,'POST',endpoint,{'revision':1,'action':'accept'}).status_code==403
    accepted=good(mutate(doctor,'POST',endpoint,{'revision':1,'action':'accept'}))
    assert accepted['status']=='accepted' and accepted['clinical_record_updated'] is False
    assert mutate(doctor,'POST',endpoint,{'revision':1,'action':'reject'}).status_code==409
    revised=good(mutate(doctor,'POST',endpoint,{'revision':2,'action':'edit','value':'Явное уточнение врача'}))
    assert revised['status']=='edited' and revised['revision']==3
    history=good(doctor.get(CR+'/fields/'+item['id']+'/history'))['items']
    assert [row['action'] for row in history]==['patient_proposed','accept','edit']
    with app.extensions['cc_session_factory']() as db:
        after=(db.scalar(select(func.count()).select_from(ClinicalDecision)),db.scalar(select(func.count()).select_from(ClinicalDocument)))
    assert before==after


def test_shared_summary_recipient_revocation_and_role_boundaries(app):
    patient,user,doctor=shared_draft(app);path=CR+'/summary-drafts/qa_shared_fields/fields'
    assert actor(app,'doc_ther').get(path).status_code==404
    assert actor(app,'doc_other').get(path).status_code==404
    assert actor(app,'clinic_01').get(path).status_code==403
    good(mutate(patient,'POST',CR+'/summary-drafts/qa_shared_fields/revoke',{}))
    assert doctor.get(path).status_code==404
    assert mutate(patient,'POST',path,{'source_version':1,'fields':[{'key':'concern','label':'Жалоба','value':'Нет доступа'}]}).status_code==404


def test_signed_legacy_encounter_addenda_append_without_mutating_original(app):
    from cc_api.p0_models import Encounter
    patient,user=login(app,'clinical_care');doctor=actor(app)
    with app.extensions['cc_session_factory'].begin() as db:
        db.add(Encounter(id='qa_old_signed',patient_id=user['patient_id'],clinician_id='doc_psy',mode='quick',content_json='{"text":"immutable original"}',status='signed',created_at='2026-10-19T00:00:00Z',signed_at='2026-10-19T00:01:00Z'))
    endpoint=CR+'/encounters/qa_old_signed/addenda'
    for n in (1,2):good(mutate(doctor,'POST',endpoint,{'text':'Синтетическое дополнение '+str(n),'reason':'Уточнение'}),201)
    assert len(good(doctor.get(endpoint))['items'])==2
    assert mutate(patient,'POST',endpoint,{'text':'Запрещено','reason':'Нет роли'}).status_code==403
    with app.extensions['cc_session_factory']() as db:assert db.get(Encounter,'qa_old_signed').content_json=='{"text":"immutable original"}'
    good(mutate(patient,'DELETE','/api/v1/patients/me/clinical-links/doc_psy',{}))
    assert doctor.get(endpoint).status_code==404


def test_pending_specialist_packet_real_reference_and_synthetic_case_stay_distinct(app):
    doctor=actor(app);patient,user=login(app,'clinical_care')
    reference=good(doctor.get('/api/v1/references/medications'))['items'][0]
    doc=create(doctor,user['patient_id'],'encounter',{'narrative':'Синтетический случай для специалистов'})
    for kind,key,version,expected in [('medication_reference',reference['id'],reference['version'],'imported_unreviewed'),('clinical_document',doc['id'],str(doc['revision']),'synthetic_patient_record')]:
        packet=good(mutate(doctor,'POST',CR+'/review-packets',{'source_kind':kind,'source_id':key,'source_version':version,'review_question':'Проверьте ограничения и источник; медицинское одобрение ожидается'}),201)
        assert packet['status']=='pending_specialist_review' and packet['medical_approval']=='pending_actual_specialist_review'
        detail=good(doctor.get(CR+'/review-packets/'+packet['id']))['packet']
        assert detail['source_status']==expected and detail['validated_scale_workflow']=='not_approved'
        canonical=json.dumps(detail['source_content'],ensure_ascii=False,sort_keys=True,separators=(',',':'))
        assert hashlib.sha256(canonical.encode()).hexdigest()==packet['source_sha256']
        assert actor(app,'doc_ther').get(CR+'/review-packets/'+packet['id']).status_code==404
        assert patient.get(CR+'/review-packets/'+packet['id']).status_code==403


def test_admin_rescheduling_is_request_only_and_cannot_change_recipient(app):
    from test_booking import setup_case,slot,proposal,BK
    patient,doctor,case=setup_case(app,key='qa_admin_case',persona='clinical_care')
    offered=proposal(doctor,case,[slot(doctor,day=40,hour=h) for h in (0,1)])
    appointment=offered['candidates'][0]['appointment_id']
    assert good(mutate(patient,'POST',BK+'/appointments/'+appointment+'/accept',{}))['status']=='confirmed'
    admin=actor(app,'clinic_01');path='/api/v1/clinic-workflow/appointments/'+appointment+'/reschedule'
    result=good(mutate(admin,'POST',path,{'reason':'Синтетический запрос другого времени'}))
    assert result['booking_confirmed'] is False and result['requires_patient_acceptance'] is True and result['requires_physician_proposal'] is True
    assert mutate(admin,'POST',path,{'reason':'Нельзя менять врача','doctor_id':'doc_ther'}).status_code==409
    from cc_api.extension_models import Appointment
    with app.extensions['cc_session_factory']() as db:assert db.get(Appointment,appointment).status=='confirmed'
    summary=good(admin.get('/api/v1/clinic-workflow/appointments'))
    assert all('patient_id' not in row and 'patient_user_id' not in row for row in summary['items'])


def test_decision_classification_validated_versioned_and_no_silent_reclassification(app):
    patient,user=login(app,'clinical_care');doctor=actor(app)
    decision=good(mutate(doctor,'POST','/api/v1/p0/decisions/'+user['patient_id'],{'text':'Синтетическое решение врача','explicit_confirmation':True}),201)
    version=good(doctor.get(CW+'/icd10?q=F32'))['version']
    path=CR+'/decisions/'+decision['id']+'/classification'
    assert mutate(doctor,'POST',path,{'code':'F32','version':'unknown'}).status_code==422
    classified=good(mutate(doctor,'POST',path,{'code':'F32','version':version}))
    assert classified['code']=='F32' and classified['version']==version
    assert good(mutate(doctor,'POST',path,{'code':'F32','version':version}))==classified
    assert mutate(doctor,'POST',path,{'code':'F33','version':version}).status_code==409
    assert mutate(patient,'POST',path,{'code':'F32','version':version}).status_code==403


def test_plan_amendments_draft_sign_publication_and_review_packet_obey_revocation(app):
    patient,user=login(app,'clinical_care');doctor=actor(app);pid=user['patient_id']
    doc=create(doctor,pid,'treatment',{'narrative':'Синтетический исходный план','items':[{'item_type':'action','title':'Синтетический шаг'}]})
    signed=good(transition(doctor,doc,'sign'));published=good(transition(doctor,signed,'publish'))
    amendment=good(transition(doctor,published,'amend',reason='Явное синтетическое уточнение'),201)
    path=CR+'/care-plans/'+doc['id']+'/amendments'
    assert good(patient.get(path))['items']==[]
    assert good(doctor.get(path))['items'][0]['id']==amendment['id']
    signed_amendment=good(transition(doctor,amendment,'sign'))
    assert good(patient.get(path))['items']==[]
    good(transition(doctor,signed_amendment,'publish'))
    assert good(patient.get(path))['items'][0]['id']==amendment['id']
    packet=good(mutate(doctor,'POST',CR+'/review-packets',{'source_kind':'clinical_document','source_id':doc['id'],'source_version':str(published['revision']),'review_question':'Синтетический случай: медицинское рецензирование ожидается'}),201)
    good(mutate(patient,'DELETE','/api/v1/patients/me/clinical-links/doc_psy',{}))
    assert patient.get(path).status_code==404
    assert doctor.get(path).status_code==404
    assert doctor.get(CR+'/review-packets/'+packet['id']).status_code==404
    assert packet['id'] not in json.dumps(good(doctor.get(CR+'/review-packets')))


def test_legacy_clinical_and_shared_summary_reads_honor_revoked_ledger_even_if_link_remains(app):
    from cc_api.onboarding_models import PatientConsent
    from cc_api.models import DoctorPatientLink
    patient,user,doctor=shared_draft(app)
    assert doctor.get('/api/v1/doctors/me/patients/'+user['patient_id']+'/clinical').status_code==200
    summaries=good(doctor.get('/api/v1/doctors/me/ai-summaries'))
    assert any(row['id']=='qa_shared_fields' for row in summaries['items'])
    with app.extensions['cc_session_factory'].begin() as db:
        for row in db.scalars(select(PatientConsent).where(PatientConsent.patient_user_id==user['id'],PatientConsent.doctor_id=='doc_psy')):
            row.revoked_at='2026-10-19T12:00:00Z'
        assert db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.patient_id==user['patient_id'],DoctorPatientLink.doctor_id=='doc_psy')) is not None
    assert doctor.get('/api/v1/doctors/me/patients/'+user['patient_id']+'/clinical').status_code==404
    assert good(doctor.get('/api/v1/doctors/me/ai-summaries'))['items']==[]


def test_legacy_case_create_and_forged_cross_tenant_case_fail_before_content(app):
    from cc_api.extension_models import PrevisitCase
    patient=actor(app,'pat_02');doctor=actor(app)
    assert mutate(patient,'POST','/api/v1/previsit-cases',{'doctor_id':'doc_psy','text':'Синтетический недопустимый другой арендатор','symptoms':[],'conditions':[],'case_consent':True}).status_code==404
    with app.extensions['cc_session_factory'].begin() as db:
        db.add(PrevisitCase(id='qa_foreign_case',patient_user_id='pat_02',doctor_id='doc_psy',status='submitted',intake_json='{"text":"PRIVATE CROSS TENANT CASE"}',created_at='2026-10-19T00:00:00Z',allowed_until='2999-01-01T00:00:00Z'))
    for client in (patient,doctor):
        assert client.get('/api/v1/previsit-cases/qa_foreign_case').status_code==404
        assert client.get('/api/v1/previsit-cases/qa_foreign_case/messages').status_code==404
        assert mutate(client,'POST','/api/v1/previsit-cases/qa_foreign_case/messages',{'text':'Недопустимое сообщение'}).status_code==404
        assert 'qa_foreign_case' not in json.dumps(good(client.get('/api/v1/previsit-cases')))


def test_legacy_patient_invitation_needs_explicit_versioned_consent_and_creates_revocable_ledger(app):
    from cc_api.extension_models import Invitation
    from cc_api.models import DoctorPatientLink
    from cc_api.onboarding_models import PatientConsent,PatientInvitation
    physician=actor(app,'doc_ther');patient=actor(app,'pat_03')
    issued=good(mutate(physician,'POST','/api/v1/invitations',{'target_role':'patient','recipient_id':'pat_03','patient_id':'pat_c','categories':['symptoms','medications']}),201)
    for extra in ({},{'consent':False,'consent_version':'clinical-link-v1'},{'consent':True,'consent_version':'wrong'}):
        response=mutate(patient,'POST','/api/v1/invitations/accept',{'registration_code':issued['registration_code'],**extra})
        assert response.status_code==422,response.json
        with app.extensions['cc_session_factory']() as db:
            assert db.get(Invitation,issued['id']).status=='pending'
            assert db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.doctor_id=='doc_ther',DoctorPatientLink.patient_id=='pat_c')) is None
            assert list(db.scalars(select(PatientConsent).where(PatientConsent.patient_user_id=='pat_03')))==[]
    accepted=good(mutate(patient,'POST','/api/v1/invitations/accept',{'registration_code':issued['registration_code'],'consent':True,'consent_version':'clinical-link-v1'}))
    assert accepted['clinical_link_created'] is True
    with app.extensions['cc_session_factory']() as db:
        ledger=db.scalar(select(PatientConsent).where(PatientConsent.patient_user_id=='pat_03',PatientConsent.doctor_id=='doc_ther'))
        assert ledger and ledger.version=='clinical-link-v1' and set(ledger.categories.split(','))=={'symptoms','medications'}
        shadow=db.get(PatientInvitation,ledger.invitation_id)
        assert shadow.status=='accepted' and shadow.patient_user_id=='pat_03'
        assert issued['registration_code'] not in shadow.token_hash
    assert mutate(patient,'POST','/api/v1/invitations/accept',{'registration_code':issued['registration_code'],'consent':True,'consent_version':'clinical-link-v1'}).status_code==404
    good(mutate(patient,'DELETE','/api/v1/patients/me/clinical-links/doc_ther',{}))
    assert physician.get('/api/v1/doctors/me/patients/pat_c/overview').status_code==404
    with app.extensions['cc_session_factory']() as db:
        assert db.scalar(select(PatientConsent).where(PatientConsent.patient_user_id=='pat_03',PatientConsent.doctor_id=='doc_ther')).revoked_at
