"""Selective UX handoff: real authenticated app/SQLite; no successful HTTP fixtures."""
import json,os,secrets
from pathlib import Path
import pytest
from playwright.sync_api import expect
from tests_e2e.test_jury_live import browser,BASE,show,login,mutate,register
from tests_e2e.test_roles_live import roles
from tests_e2e.evidence import scenario,OUT,RUN_ID
WS=Path(os.environ['CC_QA_WORKSPACE'])

@pytest.fixture(scope='module')
def actors(roles):
    pages,accounts=roles
    traces=WS/'traces';traces.mkdir(mode=0o700,exist_ok=True)
    for p in pages.values():p.context.tracing.start(screenshots=True,snapshots=True,sources=False)
    yield pages,accounts
    for role,p in pages.items():p.context.tracing.stop(path=str(traces/('handoff-'+RUN_ID+'-'+role+'.zip')))


def transition(page,document,action):
    page.once('dialog',lambda dialog:dialog.accept())
    with page.expect_response(lambda r:r.url.endswith('/documents/'+document['id']+'/'+action) and r.request.method=='POST') as changed:
        page.locator('[data-command="'+action+'-document"][data-id="'+document['id']+'"]').click()
    assert changed.value.ok
    return changed.value.json()


def test_draft_edit_explicit_sign_publish_and_patient_readback(actors):
    pages,accounts=actors;d,p=pages['doctor'],pages['patient'];pid=accounts['patient']['patient_id']
    show(d,'/doctor/patients/'+pid+'/visits');f=d.locator('[data-form=create-encounter]')
    f.locator('[name=narrative]').fill('Вымышленная запись врача для проверки черновика.');f.locator('[name=confirmed]').check()
    with d.expect_response(lambda r:r.url.endswith('/documents') and r.request.method=='POST') as created:f.locator('button').click()
    assert created.value.status==201;doc=created.value.json();url=BASE+'/api/v1/clinical-workflow/documents/'+doc['id']
    assert p.request.get(url).status==404
    edit=d.locator('[data-form=edit-clinical-document][data-id="'+doc['id']+'"]');edit.locator('xpath=..').locator('summary').click()
    narrative='Учебная запись отредактирована врачом перед подписью.'
    edit.locator('[name=narrative]').fill(narrative);edit.locator('[name=confirmed]').check()
    with d.expect_response(lambda r:r.url==url and r.request.method=='PUT') as saved:edit.locator('button').click()
    assert saved.value.ok and saved.value.json()['content']['narrative']==narrative
    doc=transition(d,saved.value.json(),'sign');assert doc['status']=='signed' and p.request.get(url).status==404
    doc=transition(d,doc,'publish');assert doc['status']=='published'
    p.reload();result=p.request.get(url);assert result.ok and result.json()['content']['narrative']==narrative
    assert pages['researcher'].request.get(url).status==403
    show(d,'/doctor/patients/'+pid+'/history');expect(d.locator('#main')).not_to_contain_text('Записей приёмов нет')


def test_manual_medication_publish_today_adherence_and_reload(actors):
    pages,accounts=actors;d,p=pages['doctor'],pages['patient'];pid=accounts['patient']['patient_id']
    show(d,'/doctor/patients/'+pid+'/treatment');f=d.locator('[data-form=create-treatment]')
    fields={'title':'Учебный препарат — тест, не назначение','dose':'Тестовая запись дозы врача, не применять','frequency':'Учебный режим, без применения','route':'Учебная запись пути','duration':'Тестовый период','notes':'Только вымышленные данные; не схема лечения.'}
    for key,value in fields.items():f.locator('[name='+key+']').fill(value)
    f.locator('[name=confirmed]').check()
    with d.expect_response(lambda r:r.url.endswith('/documents') and r.request.method=='POST') as created:f.locator('button').click()
    assert created.value.status==201;doc=created.value.json();assert p.request.get(BASE+'/api/v1/clinical-workflow/documents/'+doc['id']).status==404
    doc=transition(d,doc,'sign');doc=transition(d,doc,'publish')
    show(p,'/patient/treatment')
    for value in fields.values():expect(p.locator('#main')).to_contain_text(value)
    show(p,'/patient');button=p.locator('[data-command=report-plan]').first;expect(button).to_be_visible();item=button.get_attribute('data-id');button.click()
    with p.expect_response(lambda r:r.url.endswith('/plan-items/'+item+'/report') and r.request.method=='POST') as reported:
        p.locator('[data-command=report-outcome][data-outcome=completed]').click()
    assert reported.value.status==201
    p.reload();expect(p.locator('#main')).to_contain_text('Учебный препарат')
    plans=p.request.get(BASE+'/api/v1/p0/care-plans').json()['items'];matches=[i for plan in plans for i in plan['items'] if i['id']==item]
    assert matches and any(r['outcome']=='completed' for r in matches[0]['reports'])


def test_optional_behavioral_plan_edit_preserves_fields_and_publish(actors):
    pages,accounts=actors;d,p=pages['doctor'],pages['patient'];pid=accounts['patient']['patient_id']
    show(d,'/doctor/patients/'+pid+'/psychotherapy');f=d.locator('[data-form=create-treatment]')
    values={'title':'Учебный дневник наблюдений','frequency':'Учебная отметка без лечебных утверждений','duration':'Тестовый период','notes':'Комментарий для сохранения всех полей.'}
    for key,value in values.items():f.locator('[name='+key+']').fill(value)
    f.locator('[name=confirmed]').check()
    with d.expect_response(lambda r:r.url.endswith('/documents') and r.request.method=='POST') as created:f.locator('button').click()
    assert created.value.status==201;doc=created.value.json()
    f=d.locator('[data-form=edit-clinical-document][data-id="'+doc['id']+'"]');f.locator('xpath=..').locator('summary').click();f.locator('[name=assessment]').fill('Учебная правка врача.');f.locator('[name=confirmed]').check()
    with d.expect_response(lambda r:r.url.endswith('/documents/'+doc['id']) and r.request.method=='PUT') as saved:f.locator('button').click()
    assert saved.value.ok
    for key,value in values.items():assert saved.value.json()['content']['items'][0][key]==value
    doc=transition(d,saved.value.json(),'sign');doc=transition(d,doc,'publish');show(p,'/patient/treatment');expect(p.locator('#main')).to_contain_text(values['title'])


def test_linked_patient_doctor_messages_and_wrong_role_denied(actors):
    pages,accounts=actors;p,d=pages['patient'],pages['doctor']
    for page,route,text in [(p,'/patient/messages/'+accounts['doctor']['id'],'Учебное личное сообщение врачу.'),(d,'/doctor/messages/'+accounts['patient']['id'],'Учебный ответ наблюдающего врача.')]:
        show(page,route);f=page.locator('[data-form=clinical-message]');f.locator('[name=text]').fill(text)
        with page.expect_response(lambda r:'/threads/patient_doctor/' in r.url and r.request.method=='POST') as sent:f.locator('button').click()
        assert sent.value.status==201
    show(p,'/patient/messages/'+accounts['doctor']['id']);expect(p.locator('#main')).to_contain_text('Учебный ответ наблюдающего врача.')
    assert pages['researcher'].request.get(BASE+'/api/v1/threads/patient_doctor/'+accounts['doctor']['id']+'/messages').status==403


def test_real_rule_signal_readable_evidence_review_persists(actors):
    pages,_=actors;p,d=pages['patient'],pages['doctor']
    for value in (5,2):assert mutate(p,'POST','/api/v1/patients/me/check-ins',{'mood_score':value,'comparison':'same','note':'Учебное наблюдение для проверки правила.'}).status==201
    signals=d.request.get(BASE+'/api/v1/doctor-experience/signals').json()['items'];signal=next(x for x in signals if x['source']=='wellbeing_observation')
    show(d,'/doctor/alerts/'+signal['id']);expect(d.locator('#main')).to_contain_text('Снижение')
    form=d.locator('[data-form=signal-review]');form.locator('[name=assessment]').fill('Врач проверил вымышленные исходные оценки; клинический риск автоматически не установлен.')
    form.locator('[name=status]').select_option('acknowledged')
    with d.expect_response(lambda r:r.url.endswith('/signals/'+signal['id']+'/review') and r.request.method=='POST') as reviewed:form.locator('button').click()
    assert reviewed.value.ok
    d.reload();expect(d.locator('#main')).to_contain_text('Врач проверил вымышленные исходные оценки')
    detail=d.request.get(BASE+'/api/v1/doctor-experience/signals/'+signal['id']).json();assert detail['status']=='acknowledged' and detail['reviews']


def test_invitation_qr_trusted_origin_wrong_recipient_and_revoke(actors):
    pages,_=actors;d,p=pages['doctor'],pages['patient'];show(d,'/doctor/invitations');f=d.locator('[data-form=create-invitation]')
    f.locator('[name=recipient_email]').fill('new-'+secrets.token_hex(5)+'@evaluation.test');f.locator('[name=category]').first.check()
    with d.expect_response(lambda r:r.url.endswith('/onboarding/invitations') and r.request.method=='POST') as created:f.locator('button').click()
    assert created.value.status==201;invite=created.value.json();assert invite['absolute_url'].startswith(BASE+'/#/invite/')
    expect(d.locator('#created-invitation img.invite-qr')).to_be_visible()
    assert d.locator('#created-invitation img').evaluate('el=>el.complete&&el.naturalWidth>0')
    preview=mutate(p,'POST','/api/v1/onboarding/invitations/preview',{'token':invite['token']});assert preview.ok
    assert mutate(p,'POST','/api/v1/onboarding/invitations/accept',{'token':invite['token'],'consent':True,'consent_version':preview.json()['consent_version']}).status==403
    assert mutate(d,'POST','/api/v1/onboarding/invitations/'+invite['id']+'/revoke',{}).ok
    assert mutate(p,'POST','/api/v1/onboarding/invitations/preview',{'token':invite['token']}).status==404
    no_csrf=d.request.post(BASE+'/api/v1/onboarding/invitations',data={'recipient_email':'csrf@evaluation.test','categories':['symptoms']});assert no_csrf.status==403


@pytest.mark.parametrize('width',[320,390,768,1280,1440])
def test_responsive_patient_and_keyboard(actors,width):
    pages,_=actors;p=pages['patient'];p.set_viewport_size({'width':width,'height':900});show(p,'/patient/treatment')
    assert p.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'horizontal overflow'
    p.keyboard.press('Tab');assert p.evaluate('document.activeElement!==document.body')
    p.set_viewport_size({'width':1280,'height':900})


def test_auth_return_safe_targets_and_role_gates(actors,browser):
    _,accounts=actors
    for target,expected in [('/doctor/invitations','/doctor/invitations'),('//example.invalid','/doctor'),('/patient/profile','/doctor')]:
        c=browser.new_context();p=c.new_page();show(p,'/login?next='+__import__('urllib.parse',fromlist=['quote']).quote(target,safe=''))
        p.locator('#login-email').fill(accounts['doctor']['email']);p.locator('#login-pass').fill(accounts['doctor']['password']);p.locator('form[data-form=login] button').click();expect(p).to_have_url(BASE+'/#'+expected);c.close()


def test_invited_signup_explicit_consent_and_single_use(actors,browser):
    pages,accounts=actors;d=pages['doctor'];email='invited-'+secrets.token_hex(5)+'@evaluation.test'
    invite=mutate(d,'POST','/api/v1/onboarding/invitations',{'recipient_email':email,'categories':['symptoms']}).json()
    c=browser.new_context();p=c.new_page();show(p,invite['url']);p.locator('[data-form=invite-preview] button').click()
    expect(p.locator('#invitation-preview')).to_contain_text('Запрашиваемые права')
    register(p,email,secrets.token_urlsafe(24));expect(p).to_have_url(BASE+'/#'+invite['url'])
    assert p.request.get(BASE+'/api/v1/patients/me/links').json()['items']==[]
    p.locator('[data-form=invite-preview] button').click();f=p.locator('[data-form=invite-accept]');f.locator('[name=consent]').check()
    with p.expect_response(lambda r:r.url.endswith('/invitations/accept') and r.request.method=='POST') as accepted:f.locator('button').first.click()
    assert accepted.value.ok
    preview=mutate(p,'POST','/api/v1/onboarding/invitations/preview',{'token':invite['token']})
    assert preview.status==409
    assert any(x['id']==accounts['doctor']['id'] for x in p.request.get(BASE+'/api/v1/patients/me/links').json()['items']);c.close()


def test_adverse_review_and_explicit_clinical_decision(actors):
    pages,accounts=actors;p,d=pages['patient'],pages['doctor'];pid=accounts['patient']['patient_id']
    show(p,'/patient/adverse-events/new');f=p.locator('[data-form=adverse]');f.locator('[name=description]').fill('Вымышленное сообщение о событии для проверки рассмотрения, без утверждения причинной связи.')
    with p.expect_response(lambda r:r.url.endswith('/adverse-events') and r.request.method=='POST') as created:f.locator('button').click()
    assert created.value.status==201
    show(d,'/doctor/patients/'+pid+'/adverse-events');f=d.locator('[data-form=adverse-review]').first;f.locator('[name=review_text]').fill('Учебный комментарий врача: причинная связь не установлена.')
    with d.expect_response(lambda r:'/adverse-events/' in r.url and r.url.endswith('/review') and r.request.method=='POST') as reviewed:f.locator('button').click()
    assert reviewed.value.ok;d.reload();expect(d.locator('#main')).to_contain_text('Учебный комментарий врача')
    show(d,'/doctor/patients/'+pid+'/decisions');f=d.locator('[data-form=confirm-clinical-decision]');f.locator('[name=text]').fill('Самостоятельное учебное решение врача после просмотра данных.');f.locator('[name=confirmed]').check()
    with d.expect_response(lambda r:r.url.endswith('/decisions/'+pid) and r.request.method=='POST') as decided:f.locator('button').click()
    assert decided.value.status==201;d.reload();expect(d.locator('#main')).to_contain_text('Самостоятельное учебное решение врача')


def test_explicit_pair_visibility_enable_and_revoke(actors,browser):
    pages,accounts=actors;p=pages['patient'];second=json.loads((WS/'jury-second-doctor.json').read_text());c=browser.new_context();d=c.new_page();login(d,second['email'],second['password']);expect(d).to_have_url(BASE+'/#/doctor')
    invite=mutate(d,'POST','/api/v1/onboarding/invitations',{'recipient_email':accounts['patient']['email'],'categories':['symptoms']}).json()
    show(p,invite['url']);p.locator('[data-form=invite-preview] button').click();f=p.locator('[data-form=invite-accept]');f.locator('[name=consent]').check()
    with p.expect_response(lambda r:r.url.endswith('/invitations/accept') and r.request.method=='POST') as linked:f.locator('button').first.click()
    assert linked.value.ok
    show(p,'/patient/access');f=p.locator('[data-form=team-visibility-create]');f.locator('[name=doctor_a]').select_option(accounts['doctor']['id']);f.locator('[name=doctor_b]').select_option(second['id']);f.locator('[name=confirmed]').check()
    with p.expect_response(lambda r:r.url.endswith('/care-team/visibility') and r.request.method=='POST') as shared:f.locator('button').click()
    assert shared.value.ok
    expect(p.locator('#main')).to_contain_text('Совместный доступ: разрешён')
    p.once('dialog',lambda dialog:dialog.accept())
    with p.expect_response(lambda r:r.url.endswith('/care-team/visibility') and r.request.method=='POST') as revoked:p.locator('[data-command=team-visibility][data-allow=false]').click()
    assert revoked.value.ok;p.reload();expect(p.locator('#main')).to_contain_text('Совместный доступ: отключён');c.close()


def test_scope_visibility_revoke_fresh_doctor_session_denies(actors,browser):
    pages,accounts=actors;p=pages['patient'];show(p,'/patient/access');expect(p.locator('#main')).to_contain_text('симптомы и самочувствие')
    scopes=p.request.get(BASE+'/api/v1/patients/me/links').json()['items'];assert next(x for x in scopes if x['id']==accounts['doctor']['id'])['categories']
    p.once('dialog',lambda dialog:dialog.accept())
    with p.expect_response(lambda r:'/clinical-links/' in r.url and r.request.method=='DELETE') as revoked:p.locator('[data-command=revoke-doctor-link][data-id="'+accounts['doctor']['id']+'"]').click()
    assert revoked.value.ok
    c=browser.new_context();d=c.new_page();login(d,accounts['doctor']['email'],accounts['doctor']['password']);expect(d).to_have_url(BASE+'/#/doctor')
    assert d.request.get(BASE+'/api/v1/clinical-workflow/patients/'+accounts['patient']['patient_id']+'/documents').status==404
    assert d.request.get(BASE+'/api/v1/threads/patient_doctor/'+accounts['patient']['id']+'/messages').status in (403,404)
    assert all(x['id']!=accounts['doctor']['id'] for x in p.request.get(BASE+'/api/v1/patients/me/links').json()['items']);c.close()
