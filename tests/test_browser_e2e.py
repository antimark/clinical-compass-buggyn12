"""Optional real-browser smoke matrix. Run only against a local synthetic Flask demo.
CC_E2E_BASE_URL=http://127.0.0.1:8000 CC_BROWSER_ENABLED=1 pytest -q tests/test_browser_e2e.py
"""
from auth_support import browser_login
import os
import pytest

pytestmark=pytest.mark.skipif(os.getenv('CC_BROWSER_ENABLED')!='1', reason='Requires local live demo and Playwright Chromium')

@pytest.fixture
def page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        p=browser.new_page()
        yield p
        browser.close()

def test_route_refresh_themes_and_responsive(page):
    base=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    for width in (360,768,1280):
        page.set_viewport_size({'width':width,'height':850})
        for theme in ('light','dark'):
            page.goto(base+'/?mode=mock#/doctors')
            page.evaluate('(t)=>localStorage.setItem("cc-theme",t)',theme)
            page.reload()
            from playwright.sync_api import expect
            expect(page.locator('#cc-main')).to_have_attribute('aria-busy','false')
            assert page.locator('h1').inner_text()=='Каталог врачей'
            assert page.evaluate('document.documentElement.dataset.theme')==theme
            assert page.locator('main#cc-main').count() == 1
            page.keyboard.press('Tab')
            assert page.evaluate('document.activeElement !== document.body')

def switch_demo_actor(page, actor_id, display_name, base):
    """Use the real password login form, refreshing client identity and CSRF."""
    from auth_support import browser_login
    return browser_login(page, base, actor_id)


def test_server_persisted_cross_role_previsit_appointment_and_replay(page):
    base=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    page.goto(base+'/#/login')
    browser_login(page, base, 'pat_03')
    # The UI switch uses an async POST. Do not navigate away before it completes.
    from playwright.sync_api import expect
    page.goto(base+'/#/patient/requests/new')
    # The responding doctor must be the one selected in the intake.
    page.locator('select[name="doctor_id"]').select_option('doc_ther')
    page.locator('textarea[name="text"]').fill('Synthetic browser-flow intake')
    page.locator('input[name="case_consent"]').check()
    # Waiting for `**/#/patient/requests/*` is unsafe: the initial `/new` URL
    # already matches the glob and can be mistaken for a newly created case ID.
    # Wait for the actual persisted server response, then for the exact case URL.
    with page.expect_response(
        lambda response: response.request.method == 'POST'
        and response.url.rstrip('/').endswith('/api/v1/previsit-cases'),
        timeout=15000,
    ) as created_case:
        page.locator('form[data-form="intake"] button[type="submit"]').click()
    response=created_case.value
    assert response.status==201, f'Case creation failed: HTTP {response.status}: {response.text()[:500]}'
    case_id=response.json()['id']
    assert case_id and case_id!='new', f'Invalid persisted case identifier: {case_id!r}'
    expect(page).to_have_url(base+'/#/patient/requests/'+case_id,timeout=15000)
    page.goto(base+'/#/patient/requests/'+case_id+'/chat')
    expect(page.locator('#cc-main h1')).to_have_text('Переписка по обращению',timeout=15000)
    page.locator('form[data-form="case-message"] textarea[name="text"]').fill('First message')
    page.locator('form[data-form="case-message"] button[type="submit"]').click()
    page.get_by_text('Первое сообщение отправлено.').wait_for()
    switch_demo_actor(page,'doc_ther','Демо психотерапевт',base)
    page.goto(base+'/#/doctor/requests/'+case_id+'/chat')
    expect(page.locator('#cc-main h1')).to_have_text('Переписка по обращению',timeout=15000)
    page.locator('form[data-form="case-message"] textarea[name="text"]').fill('Doctor response')
    # Assert the POST outcome explicitly: a missing message could otherwise be
    # a CSRF/authorization failure hidden behind the UI rerender.
    with page.expect_response(
        lambda response: response.request.method == 'POST'
        and response.url.rstrip('/').endswith('/api/v1/previsit-cases/'+case_id+'/messages'),
        timeout=15000,
    ) as doctor_reply:
        page.locator('form[data-form="case-message"] button[type="submit"]').click()
    reply=doctor_reply.value
    assert reply.status==201, f'Doctor reply rejected: HTTP {reply.status}: {reply.text()[:500]}'
    assert reply.json()['sender_id']=='doc_ther'
    assert reply.json()['text']=='Doctor response'
    expect(page.locator('.cc-msg').filter(has_text='Doctor response')).to_be_visible(timeout=15000)
    persisted=page.request.get(base+'/api/v1/previsit-cases/'+case_id+'/messages')
    assert persisted.status==200,persisted.text()[:500]
    assert any(m['sender_id']=='doc_ther' and m['text']=='Doctor response'
               for m in persisted.json()['items'])
    page.goto(base+'/#/doctor/requests/'+case_id)
    page.locator('input[name="proposed_at"]').fill('2026-11-04T11:00:00+02:00')
    page.locator('form[data-form="offer"] button[type="submit"]').click()
    expect(page.locator('#cc-main')).to_contain_text('Предложено',timeout=15000)
    switch_demo_actor(page,'pat_03','Новый пациент (без связи)',base)
    page.goto(base+'/#/patient/requests/'+case_id)
    page.get_by_role('button',name='Подтвердить').click()
    expect(page.locator('#cc-main')).to_contain_text('Подтверждено',timeout=15000)


def public_doctors_from_server(page, base):
    response=page.request.get(base+'/api/v1/public/doctors')
    assert response.status==200,response.text()[:500]
    doctors=response.json()['items']
    assert doctors,'Synthetic backend must provide real public directory records'
    assert all(d.get('id') and d.get('slug') and d.get('name') for d in doctors)
    return doctors


def assert_no_document_overflow(page):
    size=page.evaluate('({scroll:document.documentElement.scrollWidth,view:innerWidth})')
    assert size['scroll']<=size['view']+1,size


def background_channels(control):
    return control.evaluate("""e=>{const c=document.createElement('canvas');c.width=c.height=1;
        const x=c.getContext('2d');x.fillStyle=getComputedStyle(e).backgroundColor;x.fillRect(0,0,1,1);
        return Array.from(x.getImageData(0,0,1,1).data).slice(0,3);}""")


def assert_public_text_contrast(page):
    """Check actual rendered text, including inherited colors after theme reload.

    A correct data-theme or CSS variable alone does not prove readable text.
    """
    result=page.locator('#cc-main').evaluate(r'''root => {
        // Canvas resolves all CSS Color 4 spaces and exponent notation to sRGB bytes.
        const canvas=document.createElement('canvas');canvas.width=canvas.height=1;
        const ctx=canvas.getContext('2d',{willReadFrequently:true});
        const rgba=c=>{ctx.clearRect(0,0,1,1);ctx.fillStyle=c;ctx.fillRect(0,0,1,1);
            const v=Array.from(ctx.getImageData(0,0,1,1).data);return [...v.slice(0,3),v[3]/255];};
        const blend=(top,bottom)=>top.slice(0,3).map((v,i)=>v*top[3]+bottom[i]*(1-top[3]));
        const luminance=rgb=>rgb.map(v=>v/255).map(v=>v<=0.04045?v/12.92:((v+0.055)/1.055)**2.4)
            .reduce((total,v,i)=>total+v*[0.2126,0.7152,0.0722][i],0);
        const inspect=()=>Array.from(root.querySelectorAll('h1,h2,p')).filter(e=>
            e.getClientRects().length && e.textContent.trim()).map(e=>{
            const ancestors=[];
            for(let a=e;a;a=a.parentElement) ancestors.push(a);
            let background=[255,255,255];
            for(const a of ancestors.reverse()) background=blend(rgba(getComputedStyle(a).backgroundColor),background);
            const foreground=blend(rgba(getComputedStyle(e).color),background);
            const a=luminance(foreground),b=luminance(background);
            return {text:e.textContent.trim().slice(0,90),contrast:(Math.max(a,b)+0.05)/(Math.min(a,b)+0.05),
                    foreground,background};
        });
        const samples=inspect();
        return {readable:samples.length>0 && samples.every(s=>s.contrast>=4.5),
                samples:samples.filter(s=>s.contrast<4.5)};
    }''')
    assert result['readable'],result['samples']


def test_public_live_navigation_preserves_guest_boundary(page):
    """Public GETs come from Flask; browsing/CTA cannot create a clinical link."""
    from playwright.sync_api import expect
    base=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    assert page.request.get(base+'/api/v1/auth/me').status==401
    assert page.request.get(base+'/api/v1/patients/me/links').status==401
    doctors=public_doctors_from_server(page,base)
    page.goto(base+'/')
    expect(page.locator('#cc-main h1')).to_have_text('Между приёмами — тоже часть лечения.')
    with page.expect_response(lambda r: r.request.method=='GET' and r.url==base+'/api/v1/public/doctors') as listing:
        page.locator('#cc-main').get_by_role('link',name='Перейти в каталог сейчас',exact=False).click()
    assert listing.value.status==200
    expect(page.locator('#cc-main h1')).to_have_text('Каталог врачей')
    for doctor in doctors:
        card=page.locator('[data-doctor-id="'+doctor['id']+'"]')
        expect(card).to_contain_text(doctor['name'])
        expect(card).to_contain_text({'psychiatry':'Психиатрия','psychotherapy':'Психотерапия'}.get(doctor['specialty'],doctor['specialty']))
        assert card.get_attribute('href')=='#/doctors/'+doctor['slug']
    doctor=doctors[-1]  # Avoid accidentally accepting a default-first-doctor flow.
    with page.expect_response(lambda r: r.request.method=='GET' and r.url==base+'/api/v1/public/doctors/'+doctor['slug']) as profile:
        page.locator('a[data-doctor-id="'+doctor['id']+'"]').click()
    assert profile.value.status==200
    detail=profile.value.json()
    dialog=page.get_by_role('dialog',name='Карточка врача')
    expect(dialog).to_be_visible()
    expect(dialog.locator('h1')).to_have_text(detail['name'])
    expect(dialog).to_contain_text({'psychiatry':'Психиатрия','psychotherapy':'Психотерапия'}.get(detail['specialty'],detail['specialty']))
    assert detail['clinic_id']==doctor['clinic_id']
    page.locator('[data-public-first-contact]').click()
    caps=page.request.get(base+'/api/v1/p0/auth/capabilities').json()
    if caps.get('synthetic_registration_enabled'):
        expect(page.locator('form[data-form="ob-journey"]')).to_be_visible()
        expect(page.locator('select[name="doctor_id"]')).to_have_value(doctor['id'])
    else:
        expect(page.locator('#cc-main')).to_contain_text('Вход')
    assert page.request.get(base+'/api/v1/auth/me').status==401
    assert page.request.get(base+'/api/v1/patients/me/links').status==401
    assert page.request.get(base+'/api/v1/previsit-cases').status==401


def test_public_live_catalogue_filters_and_empty_state(page):
    from playwright.sync_api import expect
    base=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    doctors=public_doctors_from_server(page,base)
    page.goto(base+'/doctors')
    expect(page.locator('[data-doctor-id]')).to_have_count(len(doctors))
    search=page.locator('#directory-search')
    search.fill('НетТакогоСинтетическогоВрача')
    expect(page.locator('[data-doctor-id]')).to_have_count(0)
    expect(page.locator('#directory-count')).to_contain_text('0')
    expect(page.locator('#cc-main')).to_contain_text('Врачи не найдены')
    search.fill('')
    selected=doctors[-1]
    page.locator('#directory-specialty').select_option(selected['specialty'])
    page.locator('#directory-clinic').select_option(selected['clinic_id'])
    matching=[d for d in doctors if d['specialty']==selected['specialty'] and d['clinic_id']==selected['clinic_id']]
    expect(page.locator('[data-doctor-id]')).to_have_count(len(matching))
    for doctor in matching:
        expect(page.locator('[data-doctor-id="'+doctor['id']+'"]')).to_be_visible()
    page.locator('#directory-specialty').select_option('')
    page.locator('#directory-clinic').select_option('')
    search.fill(selected['name'])
    expect(page.locator('[data-doctor-id="'+selected['id']+'"]')).to_be_visible()
    page.reload()
    expect(page.locator('#cc-main h1')).to_have_text('Каталог врачей')
    expect(page.locator('[data-doctor-id]')).to_have_count(len(doctors))
    for specialty,label in (('psychiatry','Психиатрия'),('psychotherapy','Психотерапия')):
        expected=[d for d in doctors if d['specialty']==specialty]
        assert expected,'The live synthetic fixture must include '+specialty
        page.locator('#directory-search').fill(label)
        expect(page.locator('[data-doctor-id]')).to_have_count(len(expected))
        for doctor in expected:
            expect(page.locator('[data-doctor-id="'+doctor['id']+'"]')).to_be_visible()


def test_public_live_responsive_screenshots_and_keyboard(page):
    """18 live screenshots; nested pathname refreshes must load all local assets."""
    from pathlib import Path
    from playwright.sync_api import expect
    base=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    doctor=public_doctors_from_server(page,base)[-1]
    dest=Path(os.environ.get('CC_SCREENSHOT_DIR','/tmp/clinical_compass_live_screens'))
    dest.mkdir(parents=True,exist_ok=True)
    pages=[('/', 'landing','Между приёмами — тоже часть лечения.'),('/doctors','catalogue','Каталог врачей'),
           ('/doctors/'+doctor['slug'],'profile',doctor['name'])]
    page.emulate_media(reduced_motion='reduce')
    for width in (360,768,1280):
        page.set_viewport_size({'width':width,'height':860})
        for theme in ('light','dark'):
            page.goto(base+'/')
            page.evaluate('(t)=>localStorage.setItem("cc-theme",t)',theme)
            for path,label,title in pages:
                page.goto(base+path)
                page.reload()
                expect(page.locator('#cc-main h1')).to_have_text(title)
                assert page.evaluate('document.documentElement.dataset.theme')==theme
                assert_no_document_overflow(page)
                policy=page.locator('meta[http-equiv="Content-Security-Policy"]').get_attribute('content')
                assert "script-src 'self'" in policy and 'unsafe-eval' not in policy
                assert page.evaluate('Array.from(document.scripts).every(s => new URL(s.src).pathname.startsWith("/assets/"))')
                page.keyboard.press('Tab')
                focused=page.evaluate('''() => {
                    const e=document.activeElement, s=getComputedStyle(e);
                    return {tag:e.tagName,outline:s.outlineStyle,width:parseFloat(s.outlineWidth),
                            shadow:s.boxShadow};
                }''')
                assert focused['tag']!='BODY',focused
                assert (focused['outline']!='none' and focused['width']>0) or focused['shadow']!='none',focused
                motion=page.locator('#cc-main').evaluate('''root => Array.from(root.querySelectorAll('*')).map(e => {
                    const s=getComputedStyle(e);return [s.animationDuration,s.transitionDuration];
                }).flat().flatMap(v=>v.split(',').map(parseFloat))''')
                assert all(duration<=0.01 for duration in motion),max(motion,default=0)
                assert_public_text_contrast(page)
                filename=dest/f'public_{label}_{width}_{theme}.png'
                page.screenshot(path=str(filename),full_page=True)
                assert filename.stat().st_size>1000


def test_live_patient_first_contact_keeps_doctor_and_dark_controls(page):
    from playwright.sync_api import expect
    base=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    doctors=public_doctors_from_server(page,base)
    doctor=doctors[-1]
    page.goto(base+'/#/login')
    browser_login(page, base, 'pat_03')
    page.evaluate('localStorage.setItem("cc-theme","dark")')
    page.goto(base+'/doctors/'+doctor['slug'])
    expect(page.locator('#cc-main h1')).to_have_text(doctor['name'])
    page.locator('[data-public-first-contact]').click()
    expect(page.locator('form[data-form="intake"]')).to_be_visible()
    expect(page.locator('select[name="doctor_id"]')).to_have_value(doctor['id'])
    expect(page.locator('input[name="case_consent"]')).not_to_be_checked()
    expect(page.locator('#cc-main')).to_contain_text('не создаёт долговременную клиническую связь')
    for width in (360,768,1280):
        page.set_viewport_size({'width':width,'height':860})
        assert_no_document_overflow(page)
        for selector in ('input[name="symptoms"]','textarea[name="text"]','select[name="doctor_id"]'):
            control=page.locator(selector)
            expect(control).to_be_visible()
            colors=control.evaluate('''e => {
                const s=getComputedStyle(e), p=getComputedStyle(e,'::placeholder');
                const cv=document.createElement('canvas');cv.width=cv.height=1;const cx=cv.getContext('2d');
                const rgb=c=>{cx.clearRect(0,0,1,1);cx.fillStyle=c;cx.fillRect(0,0,1,1);return Array.from(cx.getImageData(0,0,1,1).data).slice(0,3);};
                const lum=c=>rgb(c).map(x=>x/255).map(x=>x<=0.04045?x/12.92:((x+0.055)/1.055)**2.4)
                    .reduce((a,v,i)=>a+v*[0.2126,0.7152,0.0722][i],0);
                const contrast=(a,b)=>(Math.max(lum(a),lum(b))+0.05)/(Math.min(lum(a),lum(b))+0.05);
                return {bg:rgb(s.backgroundColor),text:contrast(s.color,s.backgroundColor),
                        placeholder:contrast(p.color,s.backgroundColor)};
            }''')
            assert len(colors['bg'])==3 and max(colors['bg'])<130,(selector,colors)
            assert colors['text']>=4.5,(selector,colors)
            if control.get_attribute('placeholder'):
                assert colors['placeholder']>=4.5,(selector,colors)
    # No form submit here: viewing or drafting must not imply consent or linking.


def test_public_catalogue_empty_failure_and_pending_states(page):
    """Controlled transport states only; persistence evidence uses real GETs above."""
    from playwright.sync_api import expect
    base=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    endpoint=base+'/api/v1/public/doctors'
    page.route(endpoint,lambda request: request.fulfill(json={'items':[]}))
    page.goto(base+'/doctors')
    expect(page.locator('#directory-count')).to_have_text('Найдено врачей: 0')
    expect(page.locator('#directory-results')).to_contain_text('Врачи не найдены')
    page.unroute(endpoint)
    page.route(endpoint,lambda request: request.fulfill(status=503,json={'error':{'message':'Synthetic directory unavailable','code':'TEST_UNAVAILABLE'}}))
    page.reload()
    expect(page.locator('#cc-main h1')).to_have_text('Не удалось открыть страницу')
    expect(page.locator('#cc-main')).to_contain_text('Synthetic directory unavailable')
    expect(page.locator('#cc-main')).to_have_attribute('aria-busy','false')
    page.unroute(endpoint)
    # Hold a real request, inspect the loading UI, then send it to Flask unchanged.
    pending=[]
    page.route(endpoint,lambda request: pending.append(request))
    with page.expect_request(endpoint):
        page.reload(wait_until='domcontentloaded')
    expect(page.locator('#cc-main h1')).to_have_text('Загрузка...')
    expect(page.locator('#cc-main')).to_have_attribute('aria-busy','true')
    page.locator('#cc-main [role="status"]').wait_for()
    assert len(pending)==1
    pending[0].continue_()
    expect(page.locator('#cc-main h1')).to_have_text('Каталог врачей')
    expect(page.locator('#cc-main')).to_have_attribute('aria-busy','false')
    expect(page.locator('[data-doctor-id]').first).to_be_visible()


def register_live_patient(page,email,password):
    """Use the real registration form and observe its committed server response."""
    from playwright.sync_api import expect
    form=page.locator('form[data-form="ob-register"]')
    expect(form).to_be_visible()
    form.locator('[name="display_name"]').fill('Синтетический браузерный пациент')
    form.locator('[name="email"]').fill(email)
    form.locator('[name="password"]').fill(password)
    form.locator('[name="terms_consent"]').check()
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/v1/onboarding/register')) as registration:
        form.locator('button[type="submit"]').click()
    response=registration.value
    assert response.status==201,response.text()[:500]
    expect(page.locator('form[data-form="ob-state"]')).to_be_visible()
    return response.json()


def test_live_guest_draft_registration_explicit_case_and_account_resume(page):
    from uuid import uuid4
    from playwright.sync_api import expect
    base=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    password='Browser-synthetic-password-42'
    email='browser-'+uuid4().hex+'@qa.test'
    doctors=public_doctors_from_server(page,base)
    doctor=next(d for d in doctors if d['id']=='doc_ther')
    page.goto(base+'/doctors/'+doctor['slug'])
    page.locator('[data-public-first-contact]').click()
    guest=page.locator('form[data-form="ob-journey"]')
    expect(guest).to_be_visible()
    expect(guest.locator('[name="doctor_id"]')).to_have_value(doctor['id'])
    guest.locator('[name="subject"]').fill('Первое синтетическое обращение')
    guest.locator('[name="message"]').fill('Сохранённый текст перед регистрацией')
    with page.expect_response(lambda r:r.request.method=='PUT' and r.url.endswith('/api/v1/onboarding/journey')) as saved:
        guest.get_by_role('button',name='Сохранить черновик',exact=True).click()
    assert saved.value.status==200,saved.value.text()[:500]
    page.reload()
    expect(page.locator('form[data-form="ob-journey"] [name="message"]')).to_have_value('Сохранённый текст перед регистрацией')
    page.locator('form[data-form="ob-journey"]').get_by_role('button',name='Сохранить и зарегистрироваться').click()
    account=register_live_patient(page,email,password)
    assert account['context']['role']=='patient'
    assert page.request.get(base+'/api/v1/previsit-cases').json()['items']==[]
    assert page.request.get(base+'/api/v1/patients/me/links').json()['items']==[]
    page.locator('form[data-form="ob-state"]').get_by_role('button',name='Пропустить').click()
    intake=page.locator('form[data-form="intake"]')
    expect(intake).to_be_visible()
    expect(intake.locator('[name="doctor_id"]')).to_have_value(doctor['id'])
    expect(intake.locator('[name="subject"]')).to_have_value('Первое синтетическое обращение')
    expect(intake.locator('[name="text"]')).to_have_value('Сохранённый текст перед регистрацией')
    expect(intake.locator('[name="case_consent"]')).not_to_be_checked()
    page.reload()
    expect(page.locator('form[data-form="intake"] [name="text"]')).to_have_value('Сохранённый текст перед регистрацией')
    page.locator('form[data-form="intake"] [name="case_consent"]').check()
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/v1/previsit-cases')) as submission:
        page.locator('form[data-form="intake"] button[type="submit"]').click()
    assert submission.value.status==201,submission.value.text()[:500]
    case=submission.value.json()
    assert case['doctor_id']==doctor['id']
    assert 'Сохранённый текст перед регистрацией' in case['intake']['text']
    expect(page).to_have_url(base+'/doctors/'+doctor['slug']+'#/patient/requests/'+case['id'])
    # Persisted case-level consent never creates a permanent clinical link.
    assert page.request.get(base+'/api/v1/patients/me/links').json()['items']==[]
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/v1/onboarding/logout')) as logout:
        page.locator('.cc-account-menu > summary').click()
        page.locator('[data-action="ob-logout"]').click()
    assert logout.value.status==200
    page.reload()
    assert page.request.get(base+'/api/v1/auth/me').status==401
    login=page.locator('form[data-form="ob-login"]')
    expect(login).to_be_visible()
    login.locator('[name="email"]').fill(email)
    login.locator('[name="password"]').fill(password)
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/v1/onboarding/login')) as logged:
        login.locator('button[type="submit"]').click()
    assert logged.value.status==200,logged.value.text()[:500]
    assert logged.value.json()['user']['id']==account['user']['id']
    expect(page.locator('#cc-main h1')).to_have_text('Сегодня')
    persisted=page.request.get(base+'/api/v1/previsit-cases/'+case['id'])
    assert persisted.status==200 and persisted.json()['intake']['text']==case['intake']['text']
    assert page.request.get(base+'/api/v1/onboarding/state').json()['status']=='completed'


def test_live_invitation_register_consent_and_separate_release(page):
    from uuid import uuid4
    from playwright.sync_api import expect
    base=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    email='invited-'+uuid4().hex+'@qa.test'
    password='Invited-synthetic-password-42'
    page.goto(base+'/#/login')
    browser_login(page, base, 'doc_psy')
    page.goto(base+'/#/doctor/invitations/new')
    form=page.locator('form[data-form="ob-invite-create"]')
    expect(form).to_be_visible()
    form.locator('[name="recipient_email"]').fill(email)
    form.locator('[name="categories"][value="symptoms"]').check()
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/v1/onboarding/invitations')) as issuing:
        form.locator('button[type="submit"]').click()
    assert issuing.value.status==201,issuing.value.text()[:500]
    inv=issuing.value.json()
    expect(page.locator('#ob-invite-link')).to_have_value(inv['absolute_url'])
    expect(page.locator('#ob-invite-qr')).to_have_attribute('src',inv['qr_data_uri'])
    from pathlib import Path
    evidence=Path(os.environ.get('CC_SCREENSHOT_DIR','/tmp/clinical_compass_live_screens'))
    evidence.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(evidence/'phase2_issued_qr_live.png'),full_page=True)
    draft_form=page.locator('form[data-form="ob-draft"]').filter(has=page.locator('input[name="invitation_id"][value="'+inv['id']+'"]'))
    draft_form.locator('[name="content"]').fill('Подготовленная синтетическая запись до согласия')
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/invitations/'+inv['id']+'/drafts')) as drafted:
        draft_form.locator('button[type="submit"]').click()
    assert drafted.value.status==201,drafted.value.text()[:500]
    draft=drafted.value.json()
    expect(page.locator('[data-action="ob-sign"][data-id="'+draft['id']+'"]')).to_be_disabled()
    recipient=page.context.browser.new_page()
    try:
        recipient.goto(base+'/#'+inv['url'])
        expect(recipient.locator('#cc-main h1')).to_have_text('Приглашение врача')
        recipient.get_by_role('link',name='Создать аккаунт пациента').click()
        register_live_patient(recipient,email,password)
        assert recipient.request.get(base+'/api/v1/patients/me/links').json()['items']==[]
        assert recipient.request.get(base+'/api/v1/onboarding/records').json()['items']==[]
        recipient.locator('form[data-form="ob-state"]').get_by_role('button',name='Продолжить').click()
        consent=recipient.locator('form[data-form="ob-invite-accept"]')
        expect(consent).to_be_visible()
        expect(consent.locator('[name="clinical_consent"]')).not_to_be_checked()
        consent.locator('[name="clinical_consent"]').check()
        recipient.screenshot(path=str(evidence/'phase2_explicit_consent_live.png'),full_page=True)
        with recipient.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/v1/onboarding/invitations/accept')) as accepted:
            consent.locator('button[type="submit"]').click()
        assert accepted.value.status==200,accepted.value.text()[:500]
        expect(recipient.locator('#ob-records')).to_contain_text('Опубликованных записей пока нет')
        assert recipient.request.get(base+'/api/v1/onboarding/records').json()['items']==[]
        page.reload()
        sign=page.locator('[data-action="ob-sign"][data-id="'+draft['id']+'"]')
        expect(sign).to_be_enabled()
        page.once('dialog',lambda dialog:dialog.accept())
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/drafts/'+draft['id']+'/sign')) as signed:
            sign.click()
        assert signed.value.status==200,signed.value.text()[:500]
        assert recipient.request.get(base+'/api/v1/onboarding/records').json()['items']==[]
        publish=page.locator('[data-action="ob-publish"][data-id="'+draft['id']+'"]')
        expect(publish).to_be_visible()
        page.once('dialog',lambda dialog:dialog.accept())
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/drafts/'+draft['id']+'/publish')) as published:
            publish.click()
        assert published.value.status==200,published.value.text()[:500]
        recipient.reload()
        expect(recipient.locator('#ob-records')).to_contain_text(draft['content'])
        released=recipient.request.get(base+'/api/v1/onboarding/records').json()['items']
        assert len(released)==1 and released[0]['id']==draft['id']
        assert released[0]['content']==draft['content']
    finally:
        recipient.close()


def test_live_onboarding_forms_responsive_screenshots(page):
    """24 screenshots of real registration/onboarding/invite/issuer forms."""
    from pathlib import Path
    from uuid import uuid4
    from playwright.sync_api import expect
    base=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    dest=Path(os.environ.get('CC_SCREENSHOT_DIR','/tmp/clinical_compass_live_screens'))
    dest.mkdir(parents=True,exist_ok=True)
    password='Screenshots-synthetic-password-42'
    # Independent contexts retain their actual own cookie identity at each view.
    doctor=page.context.browser.new_page()
    invitee=page.context.browser.new_page()
    welcome=page.context.browser.new_page()
    try:
        doctor.goto(base+'/#/login')
        browser_login(doctor, base, 'doc_ther')
        boot=doctor.request.get(base+'/api/v1/onboarding/bootstrap').json()
        response=doctor.request.post(base+'/api/v1/onboarding/invitations',data={
            'recipient_email':'screens-'+uuid4().hex+'@qa.test','categories':['symptoms'],'ttl_hours':24},
            headers={'X-CSRF-Token':boot['csrf_token']})
        assert response.status==201,response.text()[:500]
        inv=response.json()
        welcome.goto(base+'/#/register/patient')
        register_live_patient(welcome,'welcome-'+uuid4().hex+'@qa.test',password)
        targets=[(page,'/register/patient','registration','Регистрация пациента'),
            (welcome,'/onboarding','onboarding','Добро пожаловать'),
            (invitee,inv['url'],'invitation','Приглашение врача'),
            (doctor,'/doctor/invitations/new','issuer','Приглашения пациентам')]
        for target,path,label,title in targets:
            target.emulate_media(reduced_motion='reduce')
            for width in (360,768,1280):
                target.set_viewport_size({'width':width,'height':860})
                for theme in ('light','dark'):
                    target.goto(base+'/#'+path)
                    target.evaluate('(t)=>localStorage.setItem("cc-theme",t)',theme)
                    target.reload()
                    expect(target.locator('#cc-main h1')).to_have_text(title)
                    expect(target.locator('#cc-main')).to_have_attribute('aria-busy','false')
                    assert target.evaluate('document.documentElement.dataset.theme')==theme
                    assert_no_document_overflow(target)
                    if theme=='dark':
                        for control in target.locator('#cc-main input:not([type=hidden]):not([type=checkbox]),#cc-main textarea,#cc-main select').all():
                            style=control.evaluate('''e=>({background:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color})''')
                            import re
                            channels=background_channels(control)
                            assert len(channels)==3 and max(channels)<130,(label,style)
                    filename=dest/f'phase2_{label}_{width}_{theme}.png'
                    target.screenshot(path=str(filename),full_page=True)
                    assert filename.stat().st_size>1000
    finally:
        for target in (doctor,invitee,welcome):
            target.close()


def test_live_legacy_staff_invitation_token_uses_original_accept_flow(page):
    """Enabled patient onboarding must preserve recipient-bound staff fixtures."""
    from playwright.sync_api import expect
    base=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    page.goto(base+'/#/login')
    browser_login(page, base, 'clinic_01')
    boot=page.request.get(base+'/api/v1/onboarding/bootstrap').json()
    issued=page.request.post(base+'/api/v1/invitations',data={'target_role':'doctor',
        'recipient_id':'doc_ther','categories':[]},headers={'X-CSRF-Token':boot['csrf_token']})
    assert issued.status==201,issued.text()[:500]
    token=issued.json()['registration_code']
    switch_demo_actor(page,'doc_ther','Демо психотерапевт',base)
    page.goto(base+'/#/invite/'+token)
    original=page.locator('form[data-form="accept-invite"]')
    expect(original).to_be_visible()
    expect(original.locator('[name="registration_code"]')).to_have_value(token)
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/v1/invitations/accept')) as accepted:
        original.locator('button[type="submit"]').click()
    assert accepted.value.status==200,accepted.value.text()[:500]
    assert accepted.value.json()['clinical_link_created'] is False
    assert page.request.get(base+'/api/v1/auth/me').json()['context']['role']=='doctor'


PX='/api/v1/patient-experience'


def phase3_login(page,base,persona):
    """Exercise password/session login; persona data stays in its own account."""
    from playwright.sync_api import expect
    page.goto(base+'/#/login')
    form=page.locator('form[data-form="ob-login"]')
    expect(form).to_be_visible()
    form.locator('[name="email"]').fill(persona+'@demo.test')
    form.locator('[name="password"]').fill('Synthetic-demo-pass-42')
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/v1/onboarding/login')) as logged:
        form.locator('button[type="submit"]').click()
    assert logged.value.status==200,logged.value.text()[:500]
    expect(page.locator('#cc-main h1')).to_have_text('Сегодня')
    return logged.value.json()


def phase3_capture_matrix(page,label):
    """Real persisted screen; six viewport/theme cases with overflow/contrast gates."""
    from pathlib import Path
    from playwright.sync_api import expect
    dest=Path(os.environ.get('CC_SCREENSHOT_DIR','/tmp/clinical_compass_live_screens'))
    dest.mkdir(parents=True,exist_ok=True)
    for width in (360,768,1280):
        page.set_viewport_size({'width':width,'height':900})
        for theme in ('light','dark'):
            page.evaluate('(theme)=>localStorage.setItem("cc-theme",theme)',theme)
            page.reload()
            expect(page.locator('#cc-main')).to_have_attribute('aria-busy','false')
            expect(page.locator('.px-head')).to_be_visible()
            assert page.evaluate('document.documentElement.dataset.theme')==theme
            assert_no_document_overflow(page)
            assert_public_text_contrast(page)
            if theme=='dark':
                for control in page.locator('#cc-main select,#cc-main textarea,#cc-main input:not([type=radio]):not([type=checkbox])').all():
                    if control.is_visible():
                        background=control.evaluate('e=>getComputedStyle(e).backgroundColor')
                        channels=background_channels(control)
                        assert len(channels)==3 and max(channels)<130,(background,label)
            filename=dest/f'phase3_{label}_{width}_{theme}.png'
            page.screenshot(path=str(filename),full_page=True)
            assert filename.stat().st_size>1000


def phase3_answer(page,base,assignment_id,question,value):
    from playwright.sync_api import expect
    endpoint=base+PX+'/questionnaires/assignments/'+assignment_id+'/draft'
    def acknowledges_answer(response):
        if response.request.method!='PUT' or response.url!=endpoint:
            return False
        payload=response.request.post_data_json
        return isinstance(payload,dict) and payload.get('answers',{}).get(question)==value
    # Pagination saves share this endpoint. Observe this specific answer mutation,
    # rather than an earlier Back/Next last_page acknowledgement.
    with page.expect_response(acknowledges_answer) as saved:
        page.locator(f'input[data-px-answer="{question}"][value="{value}"]').check()
    assert saved.value.status==200,saved.value.text()[:500]
    assert saved.value.json()['draft']['answers'][question]==value
    expect(page.locator('#px-save-status')).to_have_text('Сохранено на сервере')


def test_phase3_real_trends_both_questionnaires_and_visual_matrix(page):
    """No browser routing/response mocks: each answer and point commits to Flask."""
    from playwright.sync_api import expect
    base=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    phase3_login(page,base,'invited_empty')
    empty=page.request.get(base+PX+'/dashboard').json()
    assert empty['state']=='invited' and empty['series']==[]
    assert page.locator('.px-trend svg').count()==0
    phase3_capture_matrix(page,'invited_empty')
    # A truly new patient has no seeded history or links.
    fresh=page.context.browser.new_page()
    try:
        from uuid import uuid4
        fresh.goto(base+'/#/register/patient')
        register_live_patient(fresh,'phase3-empty-'+uuid4().hex+'@qa.test','Synthetic-new-account-pass-42')
        fresh.locator('form[data-form="ob-state"]').get_by_role('button',name='Пропустить').click()
        fresh.goto(base+'/#/patient')
        expect(fresh.locator('#cc-main h1')).to_have_text('Сегодня')
        dashboard=fresh.request.get(base+PX+'/dashboard').json()
        assert dashboard['state']=='empty' and dashboard['series']==[] and dashboard['assignments']==[]
        phase3_capture_matrix(fresh,'new_account_empty')
    finally:
        fresh.close()
    completed=[]
    for persona,start,count,value in [('trend_one',1,10,1),('trend_two',2,15,4)]:
        phase3_login(page,base,persona)
        observed=page.request.get(base+PX+'/observations').json()['series']
        primary=next(s for s in observed if s['scale_version']=='mood_1_5_v1')
        assert primary['point_count']==start
        if start==1:
            assert page.locator('.px-trend svg').count()==0
            expect(page.locator('#cc-main')).to_contain_text('Здесь появится ваша динамика')
        form=page.locator('form[data-form="px-observation"]')
        form.locator('select[name="value"]').select_option('4')
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith(PX+'/observations')) as added:
            form.locator('button[type="submit"]').click()
        assert added.value.status==201,added.value.text()[:500]
        expect(page.locator('.px-trend .px-point')).to_have_count(start+1)
        page.reload()
        expect(page.locator('.px-trend .px-point')).to_have_count(start+1)
        if persona=='trend_two':
            phase3_capture_matrix(page,'dashboard_history')
            page.goto(base+'/#/patient/trends')
            expect(page.locator('#cc-main h1')).to_have_text('Моя динамика')
            expect(page.locator('.px-trend .px-point')).to_have_count(3)
            phase3_capture_matrix(page,'longitudinal_trends')
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/onboarding/logout')) as logged_out:
            page.locator('.cc-account-menu > summary').click()
            page.locator('[data-action="ob-logout"]').click()
        assert logged_out.value.status==200
        phase3_login(page,base,persona)
        expect(page.locator('.px-trend .px-point')).to_have_count(start+1)
        assignment=next(a for a in page.request.get(base+PX+'/questionnaires/assignments').json()['items']
                        if a['definition_id']==f'demo_{count}_v1' and a['status']=='assigned')
        assignment_id=assignment['id']
        page.goto(base+'/#/patient/tasks')
        page.locator('a[href="#/patient/questionnaires/'+assignment_id+'"]').click()
        expect(page.locator('form[data-form="px-questionnaire"]')).to_be_visible()
        assert page.locator('[data-px-answer]').count()==40
        assert page.locator('#px-progress').get_attribute('max')==str(count)
        if count==10:
            expect(page.locator('form[data-form="px-questionnaire"]').get_by_role('button',name='Завершить',exact=True)).to_be_disabled()
        if count==15:
            expect(page.locator('input[name=q1][value="2"]')).to_be_checked()
            expect(page.locator('input[name=q2][value="3"]')).to_be_checked()
            phase3_capture_matrix(page,'questionnaire15_page1')
        for i in range(1,11):
            phase3_answer(page,base,assignment_id,'q'+str(i),value)
        page.reload()
        expect(page.locator('input[name=q10][value="'+str(value)+'"]')).to_be_checked()
        restored=page.request.get(base+PX+'/questionnaires/assignments/'+assignment_id).json()['draft']
        assert len(restored['answers'])==10
        if count==15:
            with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/onboarding/logout')) as draft_logout:
                page.locator('.cc-account-menu > summary').click()
                page.locator('[data-action="ob-logout"]').click()
            assert draft_logout.value.status==200
            phase3_login(page,base,persona)
            page.goto(base+'/#/patient/questionnaires/'+assignment_id)
            expect(page.locator('input[name=q10][value="4"]')).to_be_checked()
            assert page.request.get(base+PX+'/questionnaires/assignments/'+assignment_id).json()['draft']==restored
            page.locator('form[data-form="px-questionnaire"]').get_by_role('button',name='Далее',exact=True).click()
            expect(page.locator('input[name=q11]').first).to_be_visible()
            assert page.locator('[data-px-answer]').count()==20
            phase3_capture_matrix(page,'questionnaire15_page2')
            page.locator('[data-action="px-back"]').click()
            expect(page.locator('input[name=q10][value="4"]')).to_be_checked()
            page.locator('form[data-form="px-questionnaire"]').get_by_role('button',name='Далее',exact=True).click()
            expect(page.locator('input[name=q11]').first).to_be_visible()
            expect(page.locator('[data-px-answer]')).to_have_count(20)
            expect(page.locator('form[data-form="px-questionnaire"]').get_by_role('button',name='Завершить',exact=True)).to_be_disabled()
            for i in range(11,16):
                phase3_answer(page,base,assignment_id,'q'+str(i),value)
        expect(page.locator('form[data-form="px-questionnaire"]').get_by_role('button',name='Завершить',exact=True)).to_be_enabled()
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/'+assignment_id+'/submit')) as submitted:
            page.locator('form[data-form="px-questionnaire"]').get_by_role('button',name='Завершить',exact=True).click()
        assert submitted.value.status==201,submitted.value.text()[:500]
        body=submitted.value.json()
        assert body['score']==count*value and len(body['answers'])==count
        expect(page.locator('#cc-main h1')).to_have_text('Результат опросника')
        expect(page.locator('.px-score>strong')).to_have_text(str(count*value))
        expect(page.locator('.px-answers li')).to_have_count(count)
        if count==15:
            phase3_capture_matrix(page,'questionnaire_result')
            page.goto(base+'/#/patient?view=chart')
            expect(page.locator('#cc-main h1')).to_have_text('Моя карта')
            phase3_capture_matrix(page,'patient_chart')
        completed.append(body)
    switch_demo_actor(page,'doc_psy','Демо психиатр',base)
    for result in completed:
        response=page.request.get(base+PX+'/questionnaires/assignments/'+result['assignment_id']+'/result')
        assert response.status==200 and response.json()==result
    page.goto(base+'/#/doctor/questionnaires')
    button=page.locator('[data-action="px-result"][data-id="'+completed[-1]['assignment_id']+'"]')
    button.click()
    expect(page.locator('#cc-main h1')).to_have_text('Результат опросника')
    expect(page.locator('.px-score>strong')).to_have_text('60')
    # Result action is a local view; capture by navigating to the authorized chart,
    # whose URL and current scopes survive each screenshot reload.
    own=page.request.get(base+PX+'/questionnaires/assignments').json()['items']
    patient_id=next(a['patient_id'] for a in own if a['id']==completed[-1]['assignment_id'])
    page.goto(base+'/#/doctor/patients/'+patient_id)
    expect(page.locator('#cc-main h1').first).to_have_text('Карта пациента')
    phase3_capture_matrix(page,'physician_chart')


def phase4_capture_matrix(page,label,reload=True,heading='.dx-head'):
    """Six real API-driven physician views, preserving CSP and readable controls."""
    from pathlib import Path
    from playwright.sync_api import expect
    dest=Path(os.environ.get('CC_SCREENSHOT_DIR','/tmp/clinical_compass_live_screens'))
    dest.mkdir(parents=True,exist_ok=True)
    for width in (360,768,1280):
        page.set_viewport_size({'width':width,'height':900})
        for theme in ('light','dark'):
            page.evaluate('(theme)=>localStorage.setItem("cc-theme",theme)',theme)
            if reload:
                page.reload()
            else:
                # An unsaved editor is intentionally ephemeral; change the real
                # theme attribute without discarding its current user inputs.
                page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
            expect(page.locator('#cc-main')).to_have_attribute('aria-busy','false')
            expect(page.locator(heading)).to_be_visible()
            assert_no_document_overflow(page)
            assert_public_text_contrast(page)
            assert page.evaluate('document.documentElement.dataset.theme')==theme
            if theme=='dark':
                for control in page.locator('#cc-main select,#cc-main textarea,#cc-main input:not([type=hidden])').all():
                    if control.is_visible():
                        color=control.evaluate('e=>getComputedStyle(e).backgroundColor')
                        channels=background_channels(control)
                        assert len(channels)==3 and max(channels)<130,(label,color)
            page.evaluate('window.scrollTo(0,0)')
            filename=dest/f'phase4_{label}_{width}_{theme}.png'
            page.screenshot(path=str(filename),full_page=True)
            assert filename.stat().st_size>1000


def test_phase4_patient_event_to_physician_review_priority_and_visual_matrix(page):
    """Real patient writes, physician evidence/review, independent priority and reload."""
    from datetime import datetime,timedelta,timezone
    from uuid import uuid4
    from playwright.sync_api import expect
    base=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    identity=phase3_login(page,base,'history_12')
    own=page.request.get(base+PX+'/dashboard').json()
    csrf=page.request.get(base+'/api/v1/onboarding/bootstrap').json()['csrf_token']
    now=datetime.now(timezone.utc)-timedelta(seconds=2)
    ids=[]
    for index,value in enumerate((5,1)):
        response=page.request.post(base+PX+'/observations',data={
            'metric_key':'wellbeing','unit':'points','scale_version':'mood_1_5_v1',
            'value':value,'event_key':'phase4-browser-'+uuid4().hex,
            'observed_at':(now-timedelta(minutes=1-index)).isoformat()},
            headers={'X-CSRF-Token':csrf})
        assert response.status==201,response.text()[:500]
        ids.append(response.json()['id'])
    # Login through the current synthetic staff switch retains role/CSRF boundaries.
    switch_demo_actor(page,'doc_psy','Демо психиатр',base)
    page.goto(base+'/#/doctor')
    expect(page.locator('#cc-main h1')).to_have_text('Рабочий стол врача')
    dashboard=page.request.get(base+'/api/v1/doctor-experience/dashboard').json()
    matches=[s for s in dashboard['warnings'] if {o['id'] for o in s['evidence'].get('observations',[])}==set(ids)]
    assert len(matches)==1,dashboard['warnings']
    signal=matches[0]
    # Phase04 keeps the legacy event authority under explicitly collapsed provenance.
    legacy=page.locator('details[data-legacy-signals]')
    expect(legacy).not_to_have_attribute('open','')
    legacy.locator('summary').first.click()
    signal_card=page.locator('[data-signal-id="'+signal['id']+'"]')
    expect(signal_card).to_be_visible()
    assert page.locator('.dx-attention-section').evaluate('e=>e.compareDocumentPosition(document.querySelector(".dx-counters")) & Node.DOCUMENT_POSITION_FOLLOWING')
    phase4_capture_matrix(page,'doctor_dashboard')
    row=page.locator('li[data-patient-id="'+signal['patient_id']+'"]')
    if not row.is_visible():
        page.locator('details.ev-more > summary').click()
    expect(row).to_be_visible()
    row.locator('.dx-priority summary').click()
    form=row.locator('form[data-form="dx-priority"]')
    form.locator('[name="priority"]').select_option('3')
    form.locator('[name="note"]').fill('Синтетический независимый приоритет после просмотра')
    with page.expect_response(lambda r:r.request.method=='PUT' and r.url.endswith('/priority')) as saved:
        form.locator('button[type="submit"]').click()
    assert saved.value.status==200,saved.value.text()[:500]
    page.reload()
    expect(page.locator('#cc-main')).to_have_attribute('aria-busy','false')
    row=page.locator('li[data-patient-id="'+signal['patient_id']+'"]')
    if not row.is_visible():
        page.locator('details.ev-more > summary').click()
    expect(row).to_be_visible()
    expect(row.locator('.dx-priority summary')).to_contain_text('Рассмотреть первым')
    page.locator('details[data-legacy-signals] > summary').click()
    expect(page.locator('[data-signal-id="'+signal['id']+'"]')).to_be_visible()
    page.goto(base+'/#/doctor/alerts/'+signal['id'])
    expect(page.locator('#cc-main h1')).to_have_text('Рассмотреть сигнал')
    provenance=page.locator('[data-signal-id="'+signal['id']+'"] details.pd-audit')
    provenance.get_by_text('Источник и идентификаторы',exact=True).click()
    for source_id in ids:
        expect(provenance).to_contain_text(source_id)
    form=page.locator('form[data-form="dx-review"]')
    form.locator('[name="assessment"]').fill('Синтетический просмотр: исходные записи изучены')
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/review')) as reviewed:
        form.locator('button[type="submit"]').click()
    assert reviewed.value.status==200,reviewed.value.text()[:500]
    expect(page.locator('.dx-review-history')).to_contain_text('исходные записи изучены')
    phase4_capture_matrix(page,'doctor_signal_review')
    page.keyboard.press('Tab')
    assert page.evaluate('document.activeElement !== document.body')
    after=page.request.get(base+'/api/v1/doctor-experience/signals/'+signal['id']).json()
    assert after['evidence']==signal['evidence'] and after['status']=='acknowledged'
    assert len(after['reviews'])==1
    row=next(p for p in page.request.get(base+'/api/v1/doctor-experience/dashboard').json()['patients'] if p['id']==signal['patient_id'])
    assert row['physician_priority']==3


def test_phase4b_encounter_icd_treatment_sign_publish_and_visual_matrix(page):
    """Physician-authored real document, independent signing/release and patient ACL."""
    from uuid import uuid4
    from playwright.sync_api import expect
    base=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    cw=base+'/api/v1/clinical-workflow'
    page.goto(base+'/#/login')
    browser_login(page, base, 'doc_psy')
    page.goto(base+'/#/doctor/patients/pat_a/visits')
    expect(page.locator('#cc-main h1')).to_have_text('Приёмы и записи')
    phase4_capture_matrix(page,'physician_visits')
    page.get_by_role('button',name='Новая запись приёма',exact=True).click()
    form=page.locator('form[data-form="cw-save"]')
    text='Синтетическая запись E2E '+uuid4().hex
    form.locator('[name="narrative"]').fill(text)
    form.locator('[name="mode"]').select_option('extended')
    form.locator('[name="icd_query"]').fill('F32')
    with page.expect_response(lambda r:r.url.startswith(cw+'/icd10?') and r.request.method=='GET') as lookup:
        form.get_by_role('button',name='Найти код',exact=True).click()
    assert lookup.value.status==200
    selected=next(item for item in lookup.value.json()['items'] if item['code']=='F32')
    page.locator('#cw-icd-results [data-action="cw-icd-select"]').filter(has_text='F32').click()
    form=page.locator('form[data-form="cw-save"]')
    expect(form.locator('[name="diagnosis_0"]')).to_have_value('preliminary')
    expect(form).to_contain_text(selected['label'])
    phase4_capture_matrix(page,'icd10_encounter_editor',reload=False)
    with page.expect_response(lambda r:r.request.method=='POST' and r.url==cw+'/patients/pat_a/documents') as saved:
        form.get_by_role('button',name='Сохранить черновик',exact=True).click()
    assert saved.value.status==201,saved.value.text()[:500]
    doc=saved.value.json()
    card=page.locator('[data-document-id="'+doc['id']+'"]')
    expect(card).to_contain_text(text)
    patient_context=page.context.browser.new_context()
    try:
        patient=patient_context.new_page()
        patient.goto(base+'/#/login')
        browser_login(patient, base, 'pat_01')
        assert patient.request.get(cw+'/documents/'+doc['id']).status in (403,404)
        page.once('dialog',lambda dialog:dialog.accept())
        with page.expect_response(lambda r:r.request.method=='POST' and r.url==cw+'/documents/'+doc['id']+'/sign') as signed:
            card.get_by_role('button',name='Подписать',exact=True).click()
        assert signed.value.status==200,signed.value.text()[:500]
        expect(card).to_contain_text('Подписано')
        assert patient.request.get(cw+'/documents/'+doc['id']).status in (403,404)
        page.once('dialog',lambda dialog:dialog.accept())
        with page.expect_response(lambda r:r.request.method=='POST' and r.url==cw+'/documents/'+doc['id']+'/publish') as published:
            card.get_by_role('button',name='Опубликовать пациенту',exact=True).click()
        assert published.value.status==200,published.value.text()[:500]
        released=patient.request.get(cw+'/documents/'+doc['id'])
        assert released.status==200 and released.json()['content']['narrative']==text
        page.reload()
        expect(page.locator('[data-document-id="'+doc['id']+'"]')).to_contain_text('Опубликовано')
        phase4_capture_matrix(page,'published_clinical_document')
    finally:
        patient_context.close()
    page.goto(base+'/#/doctor/patients/pat_a/treatment')
    expect(page.locator('#cc-main h1')).to_have_text('План лечения')
    page.get_by_role('button',name='Создать план лечения',exact=True).click()
    form=page.locator('form[data-form="cw-save"]')
    form.get_by_role('button',name='Добавить препарат',exact=True).click()
    form=page.locator('form[data-form="cw-save"]')
    form.locator('[name="item_0_title"]').fill('Синтетическое ручное назначение врача')
    form.get_by_role('button',name='Добавить другой элемент',exact=True).click()
    form=page.locator('form[data-form="cw-save"]')
    form.locator('[name="item_1_title"]').fill('Синтетическая согласованная активность')
    phase4_capture_matrix(page,'modular_treatment_editor',reload=False)
    with page.expect_response(lambda r:r.request.method=='POST' and r.url==cw+'/patients/pat_a/documents') as treatment:
        form.get_by_role('button',name='Сохранить черновик',exact=True).click()
    assert treatment.value.status==201,treatment.value.text()[:500]
    assert len(treatment.value.json()['orders'])==1


def test_phase4c_real_reference_matching_explicit_order_patient_instruction_and_adherence(page):
    """Real eight-record catalogue to physician order and authorized patient report."""
    from uuid import uuid4
    from playwright.sync_api import expect
    base=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    cw=base+'/api/v1/clinical-workflow'
    refs=base+'/api/v1/references'
    page.goto(base+'/#/login')
    browser_login(page, base, 'doc_psy')
    page.goto(base+'/#/doctor/clinical-library')
    expect(page.locator('#cc-main h1')).to_have_text('Клинический справочник')
    expect(page.locator('.rf-card')).to_have_count(8)
    phase4_capture_matrix(page,'medication_catalogue')
    for rid,label,expected in [
        ('atomoxetine_canon_40mg','medication_capsule_detail','Атомоксетин Канон'),
        ('aviandr_maritupirdine_instruction','medication_tablet_detail','Авиандр')]:
        page.goto(base+'/#/doctor/clinical-library/'+rid)
        expect(page.locator('#cc-main h1')).to_have_text('Инструкция препарата')
        expect(page.locator('#cc-main')).to_contain_text(expected)
        details=page.locator('details.rf-section')
        assert details.count()>0
        details.first.locator('summary').click()
        phase4_capture_matrix(page,label,reload=False)
    page.goto(base+'/#/doctor/clinical-library/cbt_demo_v1')
    expect(page.locator('#cc-main')).to_contain_text('Иллюстративный материал')
    phase4_capture_matrix(page,'cbt_illustrative_reference')
    page.goto(base+'/#/doctor/patients/pat_a/treatment')
    expect(page.locator('#cc-main h1')).to_have_text('План лечения')
    before=page.request.get(cw+'/patients/pat_a/medication-orders').json()['items']
    page.get_by_role('button',name='Создать план лечения',exact=True).click()
    form=page.locator('form[data-form="cw-save"]')
    form.locator('[name="icd_query"]').fill('F32')
    with page.expect_response(lambda r:r.request.method=='GET' and r.url.startswith(cw+'/icd10?')) as lookup:
        form.get_by_role('button',name='Найти код',exact=True).click()
    assert lookup.value.status==200
    with page.expect_response(lambda r:r.request.method=='GET' and r.url.startswith(refs+'/matches?')) as match:
        page.locator('#cw-icd-results [data-action="cw-icd-select"]').filter(has_text='F32').click()
    assert match.value.status==200 and match.value.json()['items']
    expect(page.locator('.rf-match').first).to_be_visible()
    assert page.request.get(cw+'/patients/pat_a/medication-orders').json()['items']==before,'Looking up matches cannot create orders'
    assert page.locator('[name="item_0_title"]').count()==0
    candidate=page.locator('.rf-match').first
    candidate.locator('.rf-why summary').click()
    expect(candidate.locator('.rf-pointers')).to_contain_text('/icd10_codes/')
    phase4_capture_matrix(page,'diagnosis_reference_assistance',reload=False)
    selected_id=candidate.get_attribute('data-reference-id')
    candidate.get_by_role('button',name='Добавить в план',exact=True).click()
    form=page.locator('form[data-form="cw-save"]')
    expect(form.locator('[name="item_0_title"]')).not_to_have_value('')
    for key in ('dose','frequency','duration','route'):
        assert form.locator('[name="item_0_'+key+'"]').input_value()==''
    form.locator('[name="narrative"]').fill('Синтетическое E2E назначение '+uuid4().hex)
    with page.expect_response(lambda r:r.request.method=='POST' and r.url==cw+'/patients/pat_a/documents') as saved:
        form.get_by_role('button',name='Сохранить черновик',exact=True).click()
    assert saved.value.status==201,saved.value.text()[:500]
    draft=saved.value.json()
    order=draft['orders'][0]
    assert order['reference_id']==selected_id and order['reference_version'].startswith('sha256_')
    card=page.locator('[data-document-id="'+draft['id']+'"]')
    page.once('dialog',lambda dialog:dialog.accept())
    with page.expect_response(lambda r:r.request.method=='POST' and r.url==cw+'/documents/'+draft['id']+'/sign') as signed:
        card.get_by_role('button',name='Подписать',exact=True).click()
    assert signed.value.status==200
    patient_context=page.context.browser.new_context()
    try:
        patient=patient_context.new_page()
        patient.goto(base+'/#/login')
        browser_login(patient, base, 'pat_01')
        assert patient.request.get(cw+'/documents/'+draft['id']).status==404
        assert patient.request.get(refs+'/matches?code=F32&version='+lookup.value.json()['version']).status==403
        page.once('dialog',lambda dialog:dialog.accept())
        with page.expect_response(lambda r:r.request.method=='POST' and r.url==cw+'/documents/'+draft['id']+'/publish') as published:
            card.get_by_role('button',name='Опубликовать пациенту',exact=True).click()
        assert published.value.status==200,published.value.text()[:500]
        patient.goto(base+'/#/patient/treatment')
        prescribed=patient.locator('.rf-patient-order[data-order-id="'+order['id']+'"]')
        expect(prescribed).to_be_visible()
        with patient.expect_response(lambda r:r.request.method=='GET' and r.url.startswith(refs+'/medications/'+selected_id+'?version=')) as instruction:
            prescribed.locator('.rf-order-reference summary').click()
        assert instruction.value.status==200 and instruction.value.json()['version']==order['reference_version']
        expect(prescribed.locator('.rf-inline-reference')).not_to_be_empty()
        report=prescribed.locator('form[data-form="rf-report"]')
        report.locator('[name="outcome"]').select_option('partial')
        note='Синтетический отчёт по назначению '+uuid4().hex
        report.locator('[name="note"]').fill(note)
        with patient.expect_response(lambda r:r.request.method=='POST' and r.url==cw+'/medication-orders/'+order['id']+'/report') as reported:
            report.get_by_role('button',name='Сохранить отметку',exact=True).click()
        assert reported.value.status==201,reported.value.text()[:500]
        patient.reload()
        expect(patient.locator('.rf-patient-order[data-order-id="'+order['id']+'"]')).to_be_visible()
        reloaded_order=patient.locator('.rf-patient-order[data-order-id="'+order['id']+'"]')
        reloaded_order.locator('.rf-order-reference summary').click()
        expect(reloaded_order.locator('.rf-inline-reference')).not_to_be_empty()
        phase4_capture_matrix(patient,'patient_released_medication',reload=False,heading='#cc-main h1')
        patient_order=next(o for o in patient.request.get(cw+'/patients/pat_a/medication-orders').json()['items'] if o['id']==order['id'])
        assert any(r['note']==note and r['outcome']=='partial' for r in patient_order['reports'])
    finally:
        patient_context.close()
    page.reload()
    expect(page.locator('#cc-main')).to_have_attribute('aria-busy','false')
    actual=next(o for o in page.request.get(cw+'/patients/pat_a/medication-orders').json()['items'] if o['id']==order['id'])
    assert any(r['note']==note and r['outcome']=='partial' for r in actual['reports'])
    reviewed=page.locator('[data-document-id="'+draft['id']+'"]')
    reviewed.get_by_text('Отметки выполнения назначений',exact=True).click()
    expect(reviewed).to_contain_text(note)


def test_phase4d_clinical_persona_physician_chart_and_append_review_history_visual_matrix(page):
    from uuid import uuid4
    from playwright.sync_api import expect
    base=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8000')
    identity=phase3_login(page,base,'clinical_care')
    pid=identity['user']['patient_id']
    page.goto(base+'/#/patient/adverse-events/new')
    form=page.locator('form[data-form="p0-adverse"]')
    expect(form).to_be_visible()
    description='Синтетическое сообщение для последовательного разбора '+uuid4().hex
    form.locator('[name="description"]').fill(description)
    with page.expect_response(lambda r:r.request.method=='POST' and r.url==base+'/api/v1/p0/adverse-events') as submitted:
        form.get_by_role('button',name='Отправить врачу',exact=True).click()
    assert submitted.value.status==201,submitted.value.text()[:500]
    eid=submitted.value.json()['id']
    switch_demo_actor(page,'doc_psy','Демо психиатр',base)
    page.goto(base+'/#/doctor/patients/'+pid)
    expect(page.locator('#cc-main h1')).to_have_text('Карта пациента')
    expect(page.locator('#cc-main')).to_contain_text('Вера Андреевна Крылова')
    tabs=page.locator('nav[aria-label="Разделы карты пациента"]')
    expect(tabs.get_by_role('link')).to_have_count(7)
    phase4_capture_matrix(page,'clinical_persona_physician_chart',heading='.px-head')
    page.goto(base+'/#/doctor/patients/'+pid+'/adverse-events')
    expect(page.locator('#cc-main h1')).to_have_text('Сообщения о нежелательных явлениях')
    notes=['Синтетическая первичная врачебная оценка '+uuid4().hex,
        'Синтетическое дополнение врачебной оценки '+uuid4().hex]
    for status,note in zip(('assessed','closed'),notes):
        form=page.locator('form[data-form="p0-adverse-review"]').filter(
            has=page.locator('input[name="event_id"][value="'+eid+'"]'))
        form.locator('[name="status"]').select_option(status)
        form.locator('[name="review_text"]').fill(note)
        with page.expect_response(lambda r:r.request.method=='POST' and r.url==base+'/api/v1/p0/adverse-events/'+eid+'/review') as reviewed:
            form.get_by_role('button',name='Сохранить оценку',exact=True).click()
        assert reviewed.value.status==200,reviewed.value.text()[:500]
        expect(page.locator('[data-adverse-event-id="'+eid+'"]')).to_contain_text(note)
    history=page.locator('[data-adverse-event-id="'+eid+'"]')
    history.locator('details summary').click()
    for note in notes:expect(history).to_contain_text(note)
    phase4_capture_matrix(page,'adverse_event_append_history',reload=False,heading='#cc-main h1')
    page.reload()
    expect(page.locator('#cc-main')).to_have_attribute('aria-busy','false')
    preserved=page.request.get(base+'/api/v1/p0/adverse-events?patient_id='+pid)
    assert preserved.status==200
    saved=next(e for e in preserved.json()['items'] if e['id']==eid)
    assert [r['review_text'] for r in saved['reviews']]==notes
    patient_context=page.context.browser.new_context()
    try:
        patient=patient_context.new_page()
        phase3_login(patient,base,'clinical_care')
        own=patient.request.get(base+'/api/v1/p0/adverse-events')
        assert own.status==200
        assert all(note not in own.text() for note in notes)
    finally:patient_context.close()
