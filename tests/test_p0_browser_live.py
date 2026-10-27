"""Playwright live Flask-only route/role/responsive coverage.

CC_BROWSER_ENABLED=1 CC_E2E_BASE_URL=http://127.0.0.1:8000
CC_SCREENSHOT_DIR=/tmp/cc_screens pytest -q tests/test_p0_browser_live.py
No mock screens, no clinical data, no claim of end-to-end PKCE/MFA.
"""
import os
from pathlib import Path
import pytest

pytestmark=pytest.mark.skipif(os.getenv('CC_BROWSER_ENABLED')!='1',reason='Explicit live browser opt-in required')
BASE=os.getenv('CC_E2E_BASE_URL','http://127.0.0.1:8000').rstrip('/')

@pytest.fixture
def browser_page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1280,'height':820},locale='ru-RU')
        page.set_default_timeout(10000)
        yield page
        browser.close()

def role(page,uid):
    from auth_support import browser_login
    return browser_login(page, BASE, uid)['csrf_token']

def show(page,route):
    page.goto(BASE+'/#'+route,wait_until='domcontentloaded')
    page.locator('#cc-main h1').wait_for()
    # Locator assertions run under the application's strict CSP: no unsafe-eval needed.
    # wait_for_function injects eval and is blocked by script-src 'self'.
    from playwright.sync_api import expect
    expect(page.locator('#cc-main h1')).not_to_have_text('Загрузка...',timeout=15000)
    heading=page.locator('#cc-main h1').inner_text()
    assert heading!='Не удалось открыть страницу',(route,page.locator('#cc-main').inner_text()[:700])
    assert 'Не реализовано' not in page.locator('#cc-main').inner_text(),route
    assert 'СИНТЕТИЧЕСКАЯ СРЕДА · сервер' in page.locator('.demo-tag').inner_text()
    return heading

@pytest.mark.parametrize('actor,routes',[
    ('pat_01',['/notifications','/patient/treatment/adherence','/patient/adverse-events/new',
       '/patient/appointments/new']),
    ('doc_psy',['/doctor/patients/pat_a/trends','/doctor/patients/pat_a/history',
       '/doctor/patients/pat_a/treatment','/doctor/patients/pat_a/visits',
       '/doctor/patients/pat_a/adverse-events','/doctor/patients/pat_a/decisions',
       '/doctor/alerts/al_001','/doctor/clinical-library']),
    ('clinic_01',['/clinic/appointments','/clinic/patients']),
    ('researcher_01',['/research/datasets']),
])
def test_live_p0_role_route_matrix(browser_page,actor,routes):
    role(browser_page,actor)
    for path in routes:
        show(browser_page,path)

@pytest.mark.parametrize('actor,routes',[
    ('doc_psy',['/doctor/calendar','/doctor/patients/pat_a/access']),
    ('clinic_01',['/clinic','/clinic/staff','/clinic/audit']),
    ('researcher_01',['/research/compare'])])
def test_p1_live_screens(browser_page,actor,routes):
    role(browser_page,actor)
    for path in routes:show(browser_page,path)

def test_clinic_patient_reference_route_no_pii(browser_page):
    role(browser_page,'clinic_01')
    data=browser_page.request.get(BASE+'/api/v1/p0/clinic/patients')
    assert data.status==200
    ref=data.json()['items'][0]['patient_ref']
    show(browser_page,'/clinic/patients/'+ref)
    content=browser_page.locator('#cc-main').inner_text()
    assert 'Административная карточка' in content
    assert 'Показаны только разрешённые пациентом контактные' in content
    assert data.json()['items'][0]['fields']=={}
    assert 'Алексей Демонстрационный' not in content

def test_p1_questionnaire_result(browser_page):
    csrf=role(browser_page,'doc_psy')
    a=browser_page.request.post(BASE+'/api/v1/instruments/assignments',data={
        'patient_id':'pat_a','instrument_id':'GAD-7'},headers={'X-CSRF-Token':csrf})
    assert a.status==201,a.text()
    aid=a.json()['id']
    csrf=role(browser_page,'pat_01')
    submitted=browser_page.request.post(BASE+'/api/v1/instruments/assignments/'+aid+'/submit',
        data={'scores':[0,1,2,0,1,2,0]},headers={'X-CSRF-Token':csrf})
    assert submitted.status==200,submitted.text()
    show(browser_page,'/patient/questionnaires/'+aid+'/result')
    assert 'Суммарный балл' in browser_page.locator('#cc-main').inner_text()

def test_live_theme_mobile_desktop_screenshots(browser_page):
    dest=Path(os.environ.get('CC_SCREENSHOT_DIR','/tmp/clinical_compass_live_screens'))
    dest.mkdir(parents=True,exist_ok=True)
    representative=[('pat_01','/patient/treatment/adherence','patient'),
                    ('doc_psy','/doctor/patients/pat_a/treatment','doctor'),
                    ('clinic_01','/clinic','clinic'),
                    ('researcher_01','/research/compare','research')]
    for who,url,label in representative:
        role(browser_page,who)
        for width in (360,768,1280):
            browser_page.set_viewport_size({'width':width,'height':860})
            for theme in ('light','dark'):
                browser_page.goto(BASE+'/?mode=live#/')
                browser_page.evaluate('(t)=>localStorage.setItem("cc-theme",t)',theme)
                show(browser_page,url)
                assert browser_page.evaluate('document.documentElement.dataset.theme')==theme
                actual=browser_page.evaluate('({scroll:document.documentElement.scrollWidth,view:innerWidth})')
                assert actual['scroll']<=actual['view']+1,(url,width,theme,actual)
                filename=dest/(f'{label}_{width}_{theme}.png')
                browser_page.screenshot(path=str(filename),full_page=True)
                assert filename.stat().st_size>1000
