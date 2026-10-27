"""Live synthetic role workflows; private generated actor credentials outside source."""
import csv,io,json,os,secrets,time
from pathlib import Path
import pytest
from playwright.sync_api import expect
from tests_e2e.test_jury_live import browser,show,register,login,mutate,BASE,ROOT
from tests_e2e.evidence import scenario,record,OUT,RUN_ID
WS=Path(os.environ.get('CC_QA_WORKSPACE','/private/tmp/clinical-compass-jury-20261027'))

@pytest.fixture(scope='module')
def roles(browser):
    actors=json.loads((WS/'jury-actors.json').read_text());pages={};contexts=[]
    for role,actor in actors.items():
        context=browser.new_context(viewport={'width':1280,'height':900},locale='ru-RU');contexts.append(context)
        page=context.new_page();page.set_default_timeout(15000)
        with scenario(role+'_normal_login',role=role,method='live Flask + SQLite + Chromium'):
            login(page,actor['email'],actor['password'])
            expect(page).not_to_have_url(BASE+'/#/login')
        pages[role]=page
    context=browser.new_context(viewport={'width':1280,'height':900},locale='ru-RU');contexts.append(context)
    patient=context.new_page();patient.set_default_timeout(15000)
    email='linked-'+secrets.token_hex(5)+'@evaluation.test';password=secrets.token_urlsafe(24)
    with scenario('patient_registration_and_explicit_invitation_consent',role='patient',method='live Flask + SQLite + Chromium'):
        data=register(patient,email,password);expect(patient).to_have_url(BASE+'/#/patient')
        doctor=pages['doctor'];show(doctor,'/doctor/invitations')
        form=doctor.locator('form[data-form=create-invitation]')
        form.locator('[name=recipient_email]').fill(email)
        for field in form.locator('input[name=category]').all():field.check()
        with doctor.expect_response(lambda r:r.url.endswith('/onboarding/invitations') and r.request.method=='POST') as sent:
            form.locator('button').click()
        assert sent.value.status==201;inv=sent.value.json()
        show(patient,inv['url']);patient.locator('form[data-form=invite-preview] button').click();patient.locator('[name=consent]').check()
        with patient.expect_response(lambda r:r.url.endswith('/onboarding/invitations/accept') and r.request.method=='POST') as accepted:
            patient.locator('form[data-form=invite-accept] button').first.click()
        assert accepted.value.ok
    actors['patient']={'email':email,'password':password,'id':data['user']['id'],'patient_id':data['user']['patient_id']}
    private=WS/'jury-linked-patient.json';fd=os.open(private,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:json.dump(actors['patient'],f)
    pages['patient']=patient
    yield pages,actors
    for c in contexts:c.close()


def test_researcher_filter_methodology_and_csv(roles):
    pages,_=roles;p=pages['researcher'];show(p,'/research/demo-v3')
    expect(p.locator('#main')).to_contain_text('12 наблюдений')
    expect(p.locator('#main')).to_contain_text('3.5')
    p.locator('#research-cohort').select_option('A')
    p.get_by_role('button',name='Рассчитать',exact=True).click()
    expect(p).to_have_url(BASE+'/#/research/demo-v3?cohort=A')
    expect(p.locator('#main')).to_contain_text('sum(non-null mood_1_5)')
    response=p.request.get(BASE+'/api/v1/research/demo-datasets/synthetic_research_v3/summary?cohort=A')
    assert response.ok and response.json()['n']==6 and response.json()['observed_n']==5
    with p.expect_download() as dl:p.get_by_role('link',name='Скачать CSV всех агрегатов').click()
    rows=list(csv.DictReader(io.StringIO(Path(dl.value.path()).read_text())))
    assert len(rows)==1 and rows[0]['synthetic']=='True' and rows[0]['n']=='12'
    assert not any('subject' in key for key in rows[0])
    assert p.request.get(BASE+'/api/v1/research/demo-datasets/synthetic_research_v3/summary?from=2026-10-20').status==422
    assert p.request.get(BASE+'/api/v1/patient-experience/chart').status==403


def test_clinic_name_opt_in_revoke_and_staff(roles):
    pages,actors=roles;p=pages['patient'];admin=pages['clinic_admin']
    hidden='ФИО скрыто: нет разрешения пациента'
    show(admin,'/clinic/patients');expect(admin.locator('#main')).to_contain_text(hidden)
    show(p,'/patient/admin-identity')
    values=p.locator('form[data-form=admin-identity-values]')
    for key,value in {'first_name':'Учебный','last_name':'Вымышленный','middle_name':'Примерович'}.items():values.locator('[name='+key+']').fill(value)
    with p.expect_response(lambda r:r.url.endswith('/me/values') and r.request.method=='PUT') as saved:values.locator('button').click()
    assert saved.value.ok
    show(admin,'/clinic/patients');expect(admin.locator('#main')).not_to_contain_text('Примерович')
    show(p,'/patient/admin-identity')
    consent=p.locator('form[data-form=admin-identity-consent]');expect(consent).to_be_visible()
    consent.locator('[name=confirmed]').check()
    with p.expect_response(lambda r:'/me/policies/' in r.url and r.request.method=='PUT') as granted:consent.locator('button').click()
    assert granted.value.ok
    show(admin,'/clinic/patients');expect(admin.locator('#main')).to_contain_text('Вымышленный Учебный Примерович')
    projection=admin.request.get(BASE+'/api/v1/p0/clinic/patients').json()
    assert 'diagnosis' not in json.dumps(projection) and 'diary' not in json.dumps(projection)
    show(p,'/patient/admin-identity');p.once('dialog',lambda dialog:dialog.accept())
    with p.expect_response(lambda r:'/me/policies/' in r.url and r.request.method=='DELETE') as revoked:p.locator('[data-command=admin-identity-revoke]').click()
    assert revoked.value.ok
    show(admin,'/clinic/patients');expect(admin.locator('#main')).not_to_contain_text('Примерович');expect(admin.locator('#main')).to_contain_text(hidden)
    show(admin,'/clinic/staff');expect(admin.locator('#main')).to_contain_text(pages['doctor'].request.get(BASE+'/api/v1/auth/me').json()['user']['display_name'])
    assert admin.request.get(BASE+'/api/v1/patient-experience/physician/patients/'+actors['patient']['patient_id']+'/chart').status==403


def test_doctor_assign_patient_submit_review_and_private_draft(roles):
    pages,actors=roles;doctor=pages['doctor'];p=pages['patient'];pid=actors['patient']['patient_id']
    show(doctor,'/doctor/questionnaires');form=doctor.locator('form[data-form=assign-questionnaire]')
    form.locator('[name=patient_id]').select_option(pid);form.locator('[name=definition_id]').select_option('eval_gad_2_v1')
    with doctor.expect_response(lambda r:r.url.endswith('/questionnaires/assignments') and r.request.method=='POST') as assigned:form.locator('button').click()
    assert assigned.value.status==201;aid=assigned.value.json()['id']
    show(p,'/patient/questionnaires/'+aid);q=p.locator('form[data-form=questionnaire]')
    for field in q.locator('fieldset').all():field.locator('input[value="1"]').check()
    with p.expect_response(lambda r:r.url.endswith('/submit') and r.request.method=='POST') as submitted:q.get_by_role('button',name='Отправить ответы',exact=True).click()
    assert submitted.value.ok and submitted.value.json()['score']==2
    show(doctor,'/doctor/questionnaires');doctor.locator('[data-command=doctor-questionnaire-result][data-id="'+aid+'"]').click()
    expect(doctor.get_by_role('dialog')).to_contain_text('2 из 6 баллов')
    assert pages['researcher'].request.get(BASE+'/api/v1/patient-experience/questionnaires/assignments/'+aid+'/result').status==403
    # A patient-private diary never becomes the doctor's context.
    response=mutate(p,'POST','/api/v1/clinical-intelligence/patient-chat/diary',{'content':'Вымышленная личная запись для проверки приватности.','confirmed':True})
    assert response.status==201
    assert doctor.request.get(BASE+'/api/v1/clinical-intelligence/patient-chat/sources').status==403


def test_doctor_real_qwen_evidence_manual_note_and_referral(roles):
    pages,actors=roles;p=pages['patient'];doctor=pages['doctor'];pid=actors['patient']['patient_id']
    case=mutate(p,'POST','/api/v1/previsit-cases',{'doctor_id':actors['doctor']['id'],'text':'Вымышленный пациент: плохо сплю. Тревожусь из-за работы.','symptoms':[],'conditions':[],'case_consent':True})
    assert case.status==201;cid=case.json()['id']
    route='/doctor/patients/'+pid+'/clinical-intelligence?case='+cid
    show(doctor,route)
    with doctor.expect_response(lambda r:'/snapshot?' in r.url and r.request.method=='POST',timeout=65000) as analyzed:
        doctor.locator('[data-command=ci-analyze]').click()
    result=analyzed.value.json()
    metadata={k:result.get(k) for k in ('analysis_status','mode','model_version','primary_model_version','error_code','claims_persisted')}
    with (OUT/'qwen-live-metadata.jsonl').open('a') as f:
        f.write(json.dumps({'run_id':RUN_ID,**metadata})+'\n');f.flush();os.fsync(f.fileno())
    # Replaceable latest summary; append-only JSONL above is authoritative raw evidence.
    (OUT/'qwen-live-metadata.json').write_text(json.dumps(metadata,indent=2))
    assert analyzed.value.ok and result['mode']=='local_llm' and result['analysis_status']=='ready',result.get('error_code')
    assert result['tags'] and result['evidence']
    source='Вымышленный пациент: плохо сплю. Тревожусь из-за работы.'
    for item in result['evidence']:assert source[item['start']:item['end']]==item['quote']
    expect(doctor.locator('[data-command=ci-review]').first).to_be_visible()
    with doctor.expect_response(lambda r:'/reviews' in r.url and r.request.method=='POST') as reviewed:doctor.locator('[data-command=ci-review]').first.click()
    assert reviewed.value.ok
    note=doctor.locator('form[data-form=ci-document]');expect(note).to_be_visible()
    note.locator('[name=narrative]').fill('Учебный черновик. Врач проверил источник и самостоятельно отредактировал запись.')
    note.locator('[name=confirmed]').check()
    with doctor.expect_response(lambda r:r.url.endswith('/documents') and r.request.method=='POST') as saved:note.locator('button').click()
    assert saved.value.status==201
    doc=saved.value.json();assert doc.get('status')=='draft'
    referral=doctor.locator('form[data-form=ci-referral]');expect(referral).to_be_visible()
    referral.locator('[name=clinical_reason]').fill('Самостоятельное учебное решение врача после проверки вымышленного обращения.')
    referral.locator('[name=confirmed]').check()
    with doctor.expect_response(lambda r:'/referrals?' in r.url and r.request.method=='POST') as referred:referral.locator('button').click()
    assert referred.value.status==201


def test_patient_intake_messages_checkin_and_appointment(roles):
    import datetime as dt
    pages,actors=roles;p=pages['patient'];doctor=pages['doctor']
    show(p,'/patient')
    check=p.locator('form[data-form=checkin]');check.locator('input[value="3"]').check();check.locator('[name=comparison]').select_option('same')
    with p.expect_response(lambda r:r.url.endswith('/check-ins') and r.request.method=='POST') as checked:check.locator('button').click()
    assert checked.value.status==201
    show(p,'/patient/requests/new');form=p.locator('form[data-form=new-request]')
    form.locator('[name=doctor_id]').select_option(actors['doctor']['id']);form.locator('[name=text]').fill('Вымышленное обращение для проверки записи и переписки.');form.locator('[name=case_consent]').check()
    with p.expect_response(lambda r:r.url.endswith('/previsit-cases') and r.request.method=='POST') as created:form.locator('button').click()
    assert created.value.status==201;cid=created.value.json()['id']
    expect(p).to_have_url(BASE+'/#/patient/requests/'+cid)
    for who,base,message in ((p,'/patient','Вымышленный вопрос пациента.'),(doctor,'/doctor','Учебный ответ врача.')):
        show(who,base+'/requests/'+cid+'/chat');msg=who.locator('form[data-form=case-message]');msg.locator('[name=text]').fill(message)
        with who.expect_response(lambda r:r.url.endswith('/messages') and r.request.method=='POST') as sent:msg.locator('button').click()
        assert sent.value.status==201
    show(p,'/patient/requests/'+cid+'/chat');expect(p.locator('#main')).to_contain_text('Учебный ответ врача.')
    show(doctor,'/doctor/requests/'+cid);offer=doctor.locator('form[data-form=offer]')
    slots=doctor.request.get(BASE+'/api/v1/booking/slots').json()['items']
    candidate=(dt.datetime.now().astimezone()+dt.timedelta(days=2)).replace(hour=12,minute=0,second=0,microsecond=0)
    occupied=[(dt.datetime.fromisoformat(row['starts_at'].replace('Z','+00:00')),dt.datetime.fromisoformat(row['ends_at'].replace('Z','+00:00'))) for row in slots]
    for _ in range(72):
        if all(candidate+dt.timedelta(minutes=30)<=start or candidate>=end for start,end in occupied):break
        candidate+=dt.timedelta(hours=1)
    else:raise AssertionError('No free synthetic appointment time in bounded search')
    offer.locator('[name=proposed_at]').fill(candidate.strftime('%Y-%m-%dT%H:%M'))
    offer.locator('[name=format]').select_option('in_person')
    with doctor.expect_response(lambda r:r.url.endswith('/offers') and r.request.method=='POST') as proposed:offer.locator('button').click()
    assert proposed.value.status==201;aid=proposed.value.json()['id']
    show(p,'/patient/appointments');p.once('dialog',lambda dialog:dialog.accept())
    with p.expect_response(lambda r:r.url.endswith('/confirm') and r.request.method=='POST') as accepted:p.locator('[data-command=confirm-appointment][data-id="'+aid+'"]').click()
    assert accepted.value.ok
    p.reload();expect(p.locator('#main')).to_contain_text('Подтверждено')
    show(pages['clinic_admin'],'/clinic/appointments');expect(pages['clinic_admin'].locator('#main')).to_be_visible()


@pytest.mark.parametrize('audience',['patient','doctor'])
def test_live_contextual_qwen_chat_and_privacy(roles,audience):
    pages,actors=roles;page=pages[audience]
    if audience=='patient':
        show(page,'/patient/assistant');diary=page.locator('form[data-form=ci-diary]')
        diary.locator('[name=content]').fill('Вымышленная личная запись: плохо сплю. Тревожусь из-за работы.')
        diary.locator('[name=confirmed]').check()
        with page.expect_response(lambda r:r.url.endswith('/patient-chat/diary') and r.request.method=='POST') as saved:diary.locator('button').click()
        assert saved.value.status==201
        with page.expect_response(lambda r:r.url.endswith('/threads') and r.request.method=='POST') as made:page.locator('[data-command=ci-patient-thread][data-type=diary]').first.click()
    else:
        case=mutate(pages['patient'],'POST','/api/v1/previsit-cases',{'doctor_id':actors['doctor']['id'],'text':'Вымышленный пациент: плохо сплю. Тревожусь из-за работы.','case_consent':True})
        assert case.status==201
        show(page,'/doctor/patients/'+actors['patient']['patient_id']+'/clinical-intelligence?case='+case.json()['id'])
        with page.expect_response(lambda r:r.url.endswith('/threads') and r.request.method=='POST') as made:page.locator('[data-command=ci-create-thread]').click()
    assert made.value.status==201;tid=made.value.json()['id']
    form=page.locator('form[data-form=ci-message]');expect(form).to_be_visible()
    form.locator('[name=content]').fill('Какие справочные материалы о сне есть в выбранной записи?')
    with page.expect_response(lambda r:r.url.endswith('/messages') and r.request.method=='POST') as queued:form.locator('button[type=submit],button.btn-primary').click()
    assert queued.value.status==202
    deadline=time.monotonic()+100
    while True:
        r=page.request.get(BASE+'/api/v1/clinical-intelligence/threads/'+tid);assert r.ok
        data=r.json();job=data['jobs'][-1]
        if job['status'] not in ('queued','running'):break
        assert time.monotonic()<deadline,'Bounded Qwen wait expired'
        time.sleep(1)
    assert job['status']=='completed',job.get('safe_error_code')
    assistant=[m for m in data['messages'] if m['role']=='assistant'][-1]
    assert assistant['mode']=='local_llm' and assistant['model']=='qwen3:4b-instruct'
    assert assistant['catalog_citations']
    with (OUT/'chat-qwen-metadata.jsonl').open('a') as f:
        f.write(json.dumps({'audience':audience,'mode':assistant['mode'],'model':assistant['model'],'timings':job['timings'],'status':job['status']})+'\n');f.flush();os.fsync(f.fileno())
    page.get_by_role('button',name='Обновить ответы').click()
    expect(page.locator('#main')).to_contain_text('local_llm')
    other=pages['doctor' if audience=='patient' else 'patient']
    assert other.request.get(BASE+'/api/v1/clinical-intelligence/threads/'+tid).status==404
    page.reload();expect(page.locator('#main')).to_contain_text('local_llm')


def test_doctor_profile_staff_full_name_roundtrip(roles):
    pages,_=roles;doctor=pages['doctor'];admin=pages['clinic_admin']
    show(doctor,'/doctor/profile/edit');form=doctor.locator('form[data-form=profile]');form.locator('[name=display_name]').fill('Врач Учебный Примерович')
    with doctor.expect_response(lambda r:r.url.endswith('/profiles/me') and r.request.method=='PUT') as saved:form.locator('button').click()
    assert saved.value.ok
    doctor.reload();expect(doctor.locator('[name=display_name]')).to_have_value('Врач Учебный Примерович')
    show(admin,'/clinic/staff');expect(admin.locator('#main')).to_contain_text('Врач Учебный Примерович')
