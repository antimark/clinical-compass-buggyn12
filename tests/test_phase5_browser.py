"""Real guided pitch: ordinary role forms, persisted evidence, no mocked APIs."""
from auth_support import browser_login
from test_browser_e2e import background_channels
import os
from pathlib import Path
import pytest
from test_browser_e2e import page,phase3_login,switch_demo_actor,assert_no_document_overflow,assert_public_text_contrast

pytestmark=pytest.mark.skipif(os.getenv('CC_BROWSER_ENABLED')!='1',reason='Requires local live synthetic Flask and Playwright Chromium')
PT='/api/v1/pitch'
CW='/api/v1/clinical-workflow'


def capture(page,label):
    from playwright.sync_api import expect
    target=Path(os.getenv('CC_SCREENSHOT_DIR','/tmp/clinical_compass_live_screens'))
    target.mkdir(parents=True,exist_ok=True)
    for width in (360,768,1280):
        page.set_viewport_size({'width':width,'height':900})
        for theme in ('light','dark'):
            page.evaluate('(theme)=>localStorage.setItem("cc-theme",theme)',theme)
            page.reload()
            expect(page.locator('#cc-main')).to_have_attribute('aria-busy','false')
            expect(page.locator('#cc-main h1')).to_be_visible()
            assert_no_document_overflow(page)
            assert_public_text_contrast(page)
            assert page.evaluate('document.documentElement.dataset.theme')==theme
            if theme=='dark':
                for field in page.locator('#cc-main input:not([type=hidden]),#cc-main select,#cc-main textarea').all():
                    if field.is_visible():
                        import re
                        channels=background_channels(field)
                        assert len(channels)==3 and max(channels)<130,(label,channels)
            page.evaluate('window.scrollTo(0,0)')
            destination=target/f'phase5_{label}_{width}_{theme}.png'
            page.screenshot(path=str(destination),full_page=True,animations="disabled")
            assert destination.stat().st_size>1000


def test_guided_pitch_real_cross_role_observation_decision_and_publication(page):
    from playwright.sync_api import expect
    from uuid import uuid4
    base=os.getenv('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    # Patient signs in through the password form in an independent browser session.
    context=page.context.browser.new_context()
    try:
        patient=context.new_page()
        identity=phase3_login(patient,base,'clinical_care')
        pid=identity['user']['patient_id']
        page.goto(base+'/#/login')
        browser_login(page, base, 'doc_psy')
        page.goto(base+'/#/settings?view=pitch')
        expect(page.locator('#cc-main h1')).to_have_text('Пошаговая демонстрация')
        # A fresh local gate can have prior runs from API checks. Open controls explicitly.
        choices=page.locator('.pitch-choices')
        if choices.count():choices.locator('summary').click()
        start=page.locator('[data-form="pitch-start"]')
        start.locator('[name="patient_id"]').select_option(pid)
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith(PT+'/runs')) as started:
            start.locator('button[type=submit]').click()
        assert started.value.status==201,started.value.text()
        run=started.value.json()
        progress_url=base+PT+'/runs/'+run['id']+'/progress'
        assert all(step['done'] is False for step in page.request.get(progress_url).json()['steps'])
        ids=[]
        for value in ('5','1'):
            patient.goto(base+'/#/patient')
            form=patient.locator('[data-form="px-observation"]')
            form.locator('[name="value"]').select_option(value)
            with patient.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/patient-experience/observations')) as saved:
                form.locator('button[type=submit]').click()
            assert saved.value.status==201,saved.value.text()
            ids.append(saved.value.json()['id'])
            expect(patient.locator('#cc-main')).to_have_attribute('aria-busy','false')
        page.goto(base+'/#/doctor')
        expect(page.locator('#cc-main h1')).to_have_text('Рабочий стол врача')
        dashboard=page.request.get(base+'/api/v1/doctor-experience/dashboard').json()
        matching=[signal for signal in dashboard['warnings'] if set(ids)=={p['id'] for p in signal['evidence'].get('observations',[])}]
        assert len(matching)==1,dashboard
        state=page.request.get(progress_url).json()
        assert any(s['id']==matching[0]['id'] for s in state['signals'])
        page.goto(base+'/#/doctor/patients/'+pid)
        expect(page.locator('#cc-main h1').first).to_have_text('Карта пациента')
        page.goto(base+'/#/settings?view=pitch&run_id='+run['id'])
        page.locator('[data-form="pitch-chart-review"] button[type=submit]').click()
        expect(page.locator('#cc-main')).to_contain_text('Просмотр карты зафиксирован')
        escalation=page.locator('[data-form="pitch-escalation"]').filter(has=page.locator('[name="signal_id"][value="'+matching[0]['id']+'"]'))
        expect(escalation.locator('[name="delay_seconds"]')).to_have_value('')
        expect(escalation.locator('[name="target_label"]')).to_have_value('')
        escalation.locator('[name="delay_seconds"]').fill('120')
        escalation.locator('[name="target_label"]').fill('Условный участник презентации')
        with page.expect_response(lambda r:r.request.method=='PUT' and r.url.endswith('/escalation')) as configured:
            escalation.locator('button[type=submit]').click()
        assert configured.value.status==200
        button=page.locator('[data-action="pitch-simulate"][data-id="'+matching[0]['id']+'"]')
        expect(button).to_be_enabled()
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/simulate')) as simulated:
            button.click()
        assert simulated.value.status==200 and simulated.value.json()['delivered'] is False
        expect(page.locator('#cc-main')).to_contain_text('Сообщения не отправлялись')
        capture(page,'guided_pitch_escalation')
        page.goto(base+'/#/doctor/patients/'+pid+'/decisions')
        form=page.locator('[data-form="p0-decision"]')
        text='Синтетическое решение презентации '+uuid4().hex
        form.locator('[name="text"]').fill(text)
        form.locator('[name="explicit_confirmation"]').check()
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/p0/decisions/'+pid)) as decision:
            form.locator('button[type=submit]').click()
        assert decision.value.status==201,decision.value.text()
        page.goto(base+'/#/doctor/patients/'+pid+'/treatment')
        page.get_by_role('button',name='Создать план лечения',exact=True).click()
        form=page.locator('[data-form="cw-save"]')
        form.locator('[name="narrative"]').fill(text)
        form.get_by_role('button',name='Добавить другой элемент',exact=True).click()
        form=page.locator('[data-form="cw-save"]')
        form.locator('[name="item_0_title"]').fill('Синтетический индивидуальный план презентации')
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith(CW+'/patients/'+pid+'/documents')) as drafted:
            form.get_by_role('button',name='Сохранить черновик',exact=True).click()
        assert drafted.value.status==201,drafted.value.text()
        doc=drafted.value.json()
        assert patient.request.get(base+CW+'/documents/'+doc['id']).status==404
        card=page.locator('[data-document-id="'+doc['id']+'"]')
        page.once('dialog',lambda dialog:dialog.accept())
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/documents/'+doc['id']+'/sign')) as signed:
            card.get_by_role('button',name='Подписать',exact=True).click()
        assert signed.value.status==200
        assert patient.request.get(base+CW+'/documents/'+doc['id']).status==404
        assert next(s for s in patient.request.get(progress_url).json()['steps'] if s['key']=='publication')['done'] is False
        page.once('dialog',lambda dialog:dialog.accept())
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/documents/'+doc['id']+'/publish')) as published:
            card.get_by_role('button',name='Опубликовать пациенту',exact=True).click()
        assert published.value.status==200
        assert patient.request.get(base+CW+'/documents/'+doc['id']).json()['content']['narrative']==text
        page.goto(base+'/#/settings?view=pitch&run_id='+run['id'])
        expect(page.locator('.pitch-step.is-done')).to_have_count(6)
        patient.goto(base+'/#/settings?view=pitch&run_id='+run['id'])
        expect(patient.locator('.pitch-step.is-done')).to_have_count(2)
        assert patient.locator('[data-form="pitch-chart-review"],[data-form="pitch-escalation"]').count()==0
        assert text not in patient.locator('#cc-main').inner_text(),'Guided projection must not leak private document content'
        patient.reload()
        expect(patient.locator('.pitch-step.is-done')).to_have_count(2)
        capture(patient,'guided_pitch_patient')
    finally:context.close()


def test_long_reference_keyboard_navigation_reduced_motion_and_theme_matrix(page):
    from playwright.sync_api import expect
    base=os.getenv('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    page.goto(base+'/#/login')
    browser_login(page, base, 'doc_psy')
    page.emulate_media(reduced_motion='reduce')
    page.goto(base+'/#/doctor/clinical-library/atomoxetine_canon_40mg')
    expect(page.locator('.rf-detail')).to_be_visible()
    page.locator('.rf-toc > summary').focus()
    page.keyboard.press('Enter')
    expect(page.locator('.rf-toc')).to_have_attribute('open','')
    target=page.locator('.rf-toc [data-action="rf-section"]').nth(2)
    target.focus()
    page.keyboard.press('Enter')
    section=page.locator('.rf-sections > .rf-section').nth(2)
    expect(section).to_have_attribute('open','')
    expect(section.locator('summary')).to_be_focused()
    section.locator('[data-action="rf-top"]').click()
    expect(page.locator('.rf-toc > summary')).to_be_focused()
    page.get_by_role('button',name='Раскрыть все разделы',exact=True).click()
    assert page.locator('.rf-sections > .rf-section:not([open])').count()==0
    page.get_by_role('button',name='Свернуть все разделы',exact=True).click()
    assert page.locator('.rf-sections > .rf-section[open]').count()==0
    capture(page,'long_medication_navigation')


# Phase5B additions preserve all Phase5A guided and reference coverage.
"""Actual Phase 5 UI acceptance; server/role/consent states are never mocked."""
import os,re,sys
from pathlib import Path
from uuid import uuid4
import pytest
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_browser_e2e import page,switch_demo_actor,assert_no_document_overflow,assert_public_text_contrast
from playwright.sync_api import expect
pytestmark=pytest.mark.skipif(os.getenv('CC_BROWSER_ENABLED')!='1',reason='Requires local synthetic Flask and Chromium')
AP='/api/v1/admin-privacy';RW='/api/v1/research-workflow';CR='/api/v1/clinical-review'
def base():return os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
def actor(page,ident,name):
    switch_demo_actor(page,ident,{'platform_01':'Администратор платформы (синтетический)','clinic_01':'Демо администратор','researcher_01':'Демо исследователь'}.get(ident,name),base())
def patient(page):
    page.goto(base()+'/#/login')
    if page.locator('[data-action="ob-logout"]').count():
        page.locator('.cc-account-menu > summary').click()
        page.locator('[data-action="ob-logout"]').click();expect(page.locator('[data-action="ob-logout"]')).to_have_count(0);expect(page.locator('form[data-form="ob-login"]')).to_be_visible()
    f=page.locator('form[data-form="ob-login"]');f.locator('[name=email]').fill('clinical_care@demo.test');f.locator('[name=password]').fill('Synthetic-demo-pass-42')
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/v1/onboarding/login')) as r:f.get_by_role('button',name='Войти в аккаунт',exact=True).click()
    assert r.value.status==200,r.value.text();expect(page.locator('#cc-main h1')).to_have_text('Сегодня')
def submitted(page,form,method,path,status=200):
    with page.expect_response(lambda r:r.request.method==method and r.url.split('?')[0]==base()+path) as response:form.locator('button[type=submit]').click()
    assert response.value.status==status,response.value.text()[:700]
    return response.value.json()
def matrix(page,label):
    dest=Path(os.environ.get('CC_SCREENSHOT_DIR','/tmp/phase5b_ui_screens'));dest.mkdir(parents=True,exist_ok=True)
    for width in (360,768,1280):
        page.set_viewport_size({'width':width,'height':900})
        for theme in ('light','dark'):
            page.evaluate('(t)=>{localStorage.setItem("cc-theme",t);document.documentElement.dataset.theme=t}',theme)
            expect(page.locator('#cc-main')).to_have_attribute('aria-busy','false')
            assert_no_document_overflow(page);assert_public_text_contrast(page)
            if theme=='dark':
                for field in page.locator('#cc-main input:not([type=hidden]),#cc-main textarea,#cc-main select').all():
                    if field.is_visible():
                        channels=background_channels(field)
                        assert len(channels)==3 and max(channels)<130,(label,channels)
            page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(dest/f'phase5b_{label}_{width}_{theme}.png'),full_page=True,animations="disabled")
def test_phase5b_explicit_contact_policy_platform_flags_clinic_projection_and_revocation(page):
    token=uuid4().hex[:10];first='СИНТЕТИЧЕСКИЙ_'+token;phone='+7000000'+token[:4]
    actor(page,'platform_01','Администратор платформы');page.goto(base()+'/#/settings?view=privacy');expect(page.locator('#cc-main h1')).to_have_text('Административные разрешения')
    f=page.locator('[data-form="aw-flag"]');f.locator('[name=enabled]').check();submitted(page,f,'PATCH',AP+'/flags')
    f=page.locator('[data-form="aw-flag"]');f.locator('[name=organization_id]').fill('org_demo');f.locator('[name=enabled]').check();submitted(page,f,'PATCH',AP+'/flags')
    f=page.locator('[data-form="aw-template"]');f.locator('[name=organization_id]').fill('org_demo');f.locator('[name=template_key]').fill('browser_'+token);f.locator('[name=read_fields][value=first_name]').check();template=submitted(page,f,'POST',AP+'/templates',201)
    patient(page);page.goto(base()+'/#/settings?view=privacy');expect(page.locator('#cc-main h1')).to_have_text('Контакты и административный доступ')
    f=page.locator('[data-form="aw-values"]');f.locator('[name=first_name]').fill(first);f.locator('[name=phone]').fill(phone);submitted(page,f,'PUT',AP+'/me/values')
    f=page.locator('[data-form="aw-policy"]');f.locator('[name=template_id]').select_option(template['id']);f.locator('[name=confirmed]').check();submitted(page,f,'PUT',AP+'/me/policies/org_demo')
    matrix(page,'patient_contact_permission')
    actor(page,'clinic_01','Администратор клиники');page.goto(base()+'/#/clinic/patients');expect(page.locator('#cc-main h1')).to_have_text('Пациенты клиники')
    f=page.locator('[data-form="aw-patient-filter"]');f.locator('[name=filter_field]').select_option('first_name');f.locator('[name=filter_value]').fill(first);f.locator('button[type=submit]').click()
    row=page.locator('.aw-row').filter(has_text=first);expect(row).to_have_count(1);expect(row).not_to_contain_text(phone)
    row.get_by_role('link',name='Открыть разрешённые сведения',exact=True).click();expect(page.locator('#cc-main h1')).to_have_text('Административная карточка');expect(page.locator('#cc-main')).to_contain_text(first);expect(page.locator('#cc-main')).not_to_contain_text(phone)
    detail=page.url;matrix(page,'clinic_authorized_contact_detail')
    patient(page);page.goto(base()+'/#/settings?view=privacy');page.once('dialog',lambda d:d.accept())
    with page.expect_response(lambda r:r.request.method=='DELETE' and r.url.endswith(AP+'/me/policies/org_demo')) as revoked:page.get_by_role('button',name='Отозвать всё административное разрешение',exact=True).click()
    assert revoked.value.status==200
    actor(page,'clinic_01','Администратор клиники');page.goto(detail);expect(page.locator('#cc-main h1')).to_have_text('Административная карточка');expect(page.locator('#cc-main')).not_to_contain_text(first)
    expect(page.locator('#cc-main')).to_contain_text('Контактные поля не раскрыты')
def test_phase5b_versioned_research_criteria_compute_and_guarded_export(page):
    actor(page,'researcher_01','Исследователь');page.goto(base()+'/#/research/datasets');expect(page.locator('#cc-main h1')).to_have_text('Исследовательские датасеты')
    f=page.locator('[data-form="aw-dataset"]');f.locator('[name=include][value=observed_value]').check();f.locator('[name=exclude][value=missing_value]').check();f.locator('[name=start_date]').fill('2020-01-01');f.locator('[name=end_date]').fill('2035-01-01')
    d=submitted(page,f,'POST',RW+'/definitions',201);assert d['definition']['criteria']=={'include':['observed_value'],'exclude':['missing_value']}
    f=page.locator('[data-form="aw-dataset"]');expect(f.locator('[name=id]')).to_have_value(d['id']);f.locator('[name=min_cell]').fill('6');updated=submitted(page,f,'PUT',RW+'/definitions/'+d['id']);assert updated['version']==2
    matrix(page,'research_versioned_builder')
    card=page.locator('.aw-row').filter(has=page.locator('[data-action=aw-versions][data-id="'+d['id']+'"]'));card.get_by_role('button',name='История версий',exact=True).click();expect(card.locator('.aw-versions')).to_contain_text('Версия 1');expect(card.locator('.aw-versions')).to_contain_text('Версия 2')
    with page.expect_response(lambda r:r.url.endswith('/compute?version=1')) as computed:card.locator('.aw-versions [data-action=aw-compute][data-version="1"]').click()
    assert computed.value.status==200;payload=computed.value.json();assert payload['version']==1 and 'subjects' not in payload
    expect(page.locator('#cc-main')).to_contain_text('Сохранённый расчёт и проверка раскрытия');matrix(page,'research_aggregate_result')
    with page.expect_download() as download:page.locator('[data-action=aw-export][data-id="'+d['id']+'"]').click()
    assert download.value.suggested_filename.endswith('.csv')
    assert len(page.request.get(base()+RW+'/definitions/'+d['id']+'/versions').json()['items'])==2
    patient(page);assert page.request.get(base()+RW+'/definitions/'+d['id']+'/export').status==403

def test_phase5b_imported_and_illustrative_review_packets_remain_pending(page):
    actor(page,'doc_psy','Демо психиатр');page.goto(base()+'/#/doctor/clinical-library?view=review');expect(page.locator('#cc-main h1')).to_have_text('Запросы медицинского рецензирования')
    f=page.locator('[data-form="aw-review-packet"]');f.locator('[name=review_question]').fill('Синтетический запрос: проверить происхождение и пригодность справочного текста.');packet=submitted(page,f,'POST',CR+'/review-packets',201)
    assert packet['status']=='pending_specialist_review' and packet['medical_approval']=='pending_actual_specialist_review'
    page.locator('[data-action=aw-review-packet][data-id="'+packet['id']+'"]').click();expect(page.locator('#cc-main')).to_contain_text('Валидированный рабочий процесс шкалы не утверждён')
    f=page.locator('[data-form="aw-review-packet"]');options=f.locator('[name=source] option').evaluate_all('(els)=>els.map(e=>({value:e.value,text:e.textContent}))');therapy=next(x for x in options if x['value'].startswith('therapy_reference|'));f.locator('[name=source]').select_option(therapy['value']);f.locator('[name=review_question]').fill('Синтетический запрос по иллюстративной архитектуре КПТ; медицинское утверждение не выдано.');illustrative=submitted(page,f,'POST',CR+'/review-packets',201)
    assert illustrative['status']=='pending_specialist_review';matrix(page,'medical_review_pending_distinctions')
    saved=page.request.get(base()+CR+'/review-packets').json()['items'];assert {packet['id'],illustrative['id']}<=set(x['id'] for x in saved)
    patient(page);assert page.request.get(base()+CR+'/review-packets').status==403
