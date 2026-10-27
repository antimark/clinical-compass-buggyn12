"""Real Flask + SQLite browser gates. No simulated successful API responses.
Run against a private evaluation workspace: PYTHONPATH=backend:. python -m pytest -q -p tests_e2e.pytest_evidence tests_e2e/test_jury_live.py
"""
import json
import os
import secrets
from pathlib import Path
from urllib.parse import quote, urlsplit
import pytest
from playwright.sync_api import sync_playwright, expect
BASE=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8766')
if urlsplit(BASE).hostname not in ('127.0.0.1','localhost','::1'):
    raise RuntimeError('Jury E2E is restricted to loopback')
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as pw:
        b=pw.chromium.launch(headless=True)
        yield b
        b.close()

@pytest.fixture
def page(browser):
    context=browser.new_context(viewport={'width':1280,'height':900},locale='ru-RU')
    page=context.new_page();page.set_default_timeout(12000)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    yield page
    context.close()
    assert not errors,errors

def show(page,route):
    page.goto(BASE+'/#'+route)
    expect(page.locator('#main [aria-busy=true]')).to_have_count(0)
    expect(page.locator('#main h1')).to_be_visible()

def csrf(page):
    r=page.request.get(BASE+'/api/v1/onboarding/bootstrap');assert r.ok
    return r.json()['csrf_token']

def mutate(page,method,path,data=None):
    return page.request.fetch(BASE+path,method=method,data=data or {},headers={'X-CSRF-Token':csrf(page)})

def register(page,email,password):
    show(page,'/register/patient')
    page.locator('#reg-name').fill('Вымышленный участник')
    page.locator('#reg-email').fill(email)
    page.locator('[data-command=next-registration]').click()
    page.locator('#reg-pass').fill(password);page.locator('#reg-pass2').fill(password)
    page.locator('[name=terms_consent]').check()
    with page.expect_response(lambda r:r.url.endswith('/onboarding/register') and r.request.method=='POST') as response:
        page.get_by_role('button',name='Создать аккаунт',exact=True).click()
    assert response.value.status==201
    return response.value.json()

def login(page,email,password):
    page.goto(BASE+'/#/login');page.reload();expect(page.locator('#login-email')).to_be_visible();page.locator('#login-email').fill(email);page.locator('#login-pass').fill(password)
    with page.expect_response(lambda r:r.url.endswith('/onboarding/login') and r.request.method=='POST') as response:
        page.locator('form[data-form=login] button').click()
    assert response.value.status==200

def fill_guest(page,code,value):
    show(page,'/assessments/'+code)
    form=page.locator('form[data-form=guest-questionnaire]');expect(form).to_be_visible()
    for field in form.locator('fieldset').all():field.locator(f'input[value="{value}"]').check()
    form.locator('button[type=submit]').click()
    expect(page).to_have_url(BASE+'/#/assessments/'+code+'/result')
    expect(page.get_by_text('Предварительный локальный результат · ещё не сохранён в профиль',exact=True)).to_be_visible()

def test_health_and_public_contract(page):
    for path in ['/api/v1/health','/api/v1/evaluation/questionnaires/public-definitions','/api/v1/clinical-catalog/search']:
        r=page.request.get(BASE+path);assert r.status==200,(path,r.status)
    r=page.request.get(BASE+'/api/v1/patient-experience/questionnaires/assignments');assert r.status==401
    defs=page.request.get(BASE+'/api/v1/evaluation/questionnaires/public-definitions').json()
    assert len(defs['items'])==4 and defs['clinical_release'] is False

@pytest.mark.parametrize('code,count',[('phq_9',9),('phq_2',2),('gad_7',7),('gad_2',2)])
@pytest.mark.parametrize('auth_path,value',[('register',3),('login',0)])
def test_guest_account_durable_history(page,code,count,auth_path,value):
    email='jury-'+secrets.token_hex(5)+'@evaluation.test';password=secrets.token_urlsafe(24)
    if auth_path=='login':
        register(page,email,password);expect(page).to_have_url(BASE+'/#/patient')
        assert mutate(page,'POST','/api/v1/onboarding/logout').ok
        page.reload()
    fill_guest(page,code,value)
    expect(page.locator('#main h2')).to_have_text(f'{count*value} из {count*3} баллов')
    page.reload();expect(page.locator('#main h2')).to_have_text(f'{count*value} из {count*3} баллов')
    other=page.context.new_page();show(other,'/assessments/'+code+'/result')
    expect(other.locator('#main h1')).to_have_text('Нет результата');other.close()
    if auth_path=='register':
        page.get_by_role('link',name='Зарегистрироваться и сохранить',exact=True).click()
        register(page,email,password)
    else:
        page.get_by_role('link',name='Войти и сохранить',exact=True).click();login(page,email,password)
    expect(page).to_have_url(__import__('re').compile(r'/#/patient/questionnaires/dq_[^/]+/result$'))
    canonical=page.url;aid=canonical.split('/')[-2]
    result=page.request.get(BASE+'/api/v1/patient-experience/questionnaires/assignments/'+aid+'/result')
    assert result.ok and result.json()['score']==count*value and len(result.json()['answers'])==count
    assert page.evaluate('sessionStorage.getItem("cc_pilot_guest_result_v1")') is None
    page.reload();expect(page.locator('#main')).to_contain_text(f'{count*value}')
    assert mutate(page,'POST','/api/v1/onboarding/logout').ok
    login(page,email,password);expect(page).to_have_url(BASE+'/#/patient')
    show(page,'/patient/profile');page.get_by_role('link',name='Открыть историю результатов').click()
    expect(page.locator(f'a[href="/#/patient/questionnaires/{aid}/result"]')).to_be_visible()
    page.locator(f'a[href="/#/patient/questionnaires/{aid}/result"]').click();expect(page).to_have_url(canonical)

@pytest.mark.parametrize('code',[ 'phq_9','phq_2','gad_7','gad_2'])
def test_missing_guest_answers_stay_unsaved(page,code):
    show(page,'/assessments/'+code)
    page.locator('form[data-form=guest-questionnaire] button[type=submit]').click()
    expect(page).to_have_url(BASE+'/#/assessments/'+code)
    assert page.evaluate('sessionStorage.getItem("cc_pilot_guest_result_v1")') is None

def test_guest_retry_after_lost_submit_response_is_not_duplicate(page):
    fill_guest(page,'phq_2',2)
    def lose_response(route):
        # Real request reaches Flask and commits; inject only transport failure.
        response=route.fetch();assert response.status==201
        route.abort('failed')
    pattern='**/api/v1/patient-experience/questionnaires/assignments/*/submit'
    page.route(pattern,lose_response)
    register(page,'retry-'+secrets.token_hex(5)+'@evaluation.test',secrets.token_urlsafe(24))
    expect(page).to_have_url(BASE+'/#/assessments/phq_2/result')
    expect(page.locator('#guest-save-error')).to_contain_text('ещё не сохранён')
    page.unroute(pattern,lose_response)
    page.get_by_role('button',name='Сохранить в мой профиль').click()
    expect(page).to_have_url(__import__('re').compile(r'/#/patient/questionnaires/dq_[^/]+/result$'))
    assignments=page.request.get(BASE+'/api/v1/patient-experience/questionnaires/assignments').json()['items']
    assert len(assignments)==1,'Transport retry created duplicate questionnaire results'

MEDICINES=sorted((ROOT/'clinical_catalog_data/v5/medicines/by_inn').glob('*.json'))+sorted((ROOT/'clinical_catalog_data/v5/medicines/source_product_instructions').glob('*.json'))

def scalar_leaves(value):
    if value is None or value=='':return []
    if isinstance(value,bool):return ['да' if value else 'нет']
    if isinstance(value,(str,int,float)):return [str(value)]
    if isinstance(value,list):return [s for child in value for s in scalar_leaves(child)]
    if isinstance(value,dict):return [s for child in value.values() for s in scalar_leaves(child)]
    return []

@pytest.mark.parametrize('source',MEDICINES,ids=lambda p:p.stem)
def test_all_medicine_source_fields_render_in_browser(page,source):
    identifier=('product:' if source.parent.name=='source_product_instructions' else '')+source.stem
    show(page,'/clinical-library?type=medicine&item='+quote('medicine:'+identifier))
    detail=page.locator('#catalog-detail');expect(detail.locator('h2')).to_be_visible()
    text=' '.join(detail.inner_text().split())
    assert '[object Object]' not in text
    raw=json.loads(source.read_text())
    for key,value in raw.items():
        for scalar in scalar_leaves(value):
            assert ' '.join(scalar.split()) in text,(source.name,key,scalar[:90])
    for anchor in detail.locator('a[target=_blank]').all():
        assert anchor.get_attribute('href').startswith('https://')
        assert 'noopener' in anchor.get_attribute('rel')

@pytest.mark.parametrize('kind,total',[('medicine',77),('diagnosis',77),('therapy',58),('instrument',30)])
def test_live_catalog_pages_counts_and_internal_links(page,kind,total):
    rows=[]
    for number in range(1,(total+49)//50+1):
        response=page.request.get(BASE+f'/api/v1/clinical-catalog/search?type={kind}&page={number}&per_page=50')
        assert response.ok;data=response.json();assert data['total']==total;rows+=data['items']
    assert len(rows)==total and len({x['id'] for x in rows})==total
    for row in rows:
        detail=page.request.get(BASE+'/api/v1/clinical-catalog/'+kind+'/'+quote(row['id'],safe='')).json()
        for link in detail.get('links',[]):
            assert page.request.get(BASE+'/api/v1/clinical-catalog/'+link['kind']+'/'+quote(link['id'],safe='')).ok
    show(page,'/clinical-library?type='+kind)
    if total>50:
        page.get_by_role('link',name='Следующая',exact=True).click()
        expect(page.locator('#main')).to_contain_text(f'Страница 2 из 2 · показаны {total-50} из {total}')

@pytest.mark.parametrize('code,count',[('phq_9',9),('phq_2',2),('gad_7',7),('gad_2',2)])
def test_live_server_validation_csrf_revision_and_idempotency(page,code,count):
    register(page,'validation-'+secrets.token_hex(5)+'@evaluation.test',secrets.token_urlsafe(24))
    expect(page).to_have_url(BASE+'/#/patient')
    prefix='/api/v1/patient-experience/questionnaires'
    response=mutate(page,'POST',prefix+'/self-assign',{'definition_id':'eval_'+code+'_v1'})
    assert response.status==201;aid=response.json()['id'];base=prefix+'/assignments/'+aid
    current=page.request.get(BASE+base).json();definition=current['definition'];version=current['assignment']['definition_version']
    data={'definition_version':version,'revision':0,'answers':{q['id']:1 for q in definition['questions']},'last_page':0}
    # No CSRF or bad answer must not advance the revision.
    assert page.request.put(BASE+base+'/draft',data=data).status==403
    bad={**data,'answers':{**data['answers'],definition['questions'][0]['id']:4}}
    assert mutate(page,'PUT',base+'/draft',bad).status==422
    assert page.request.get(BASE+base).json()['draft']['revision']==0
    assert mutate(page,'POST',base+'/submit',{'definition_version':version,'revision':0,'idempotency_key':'incomplete'}).status==422
    draft=mutate(page,'PUT',base+'/draft',data);assert draft.ok
    assert mutate(page,'PUT',base+'/draft',data).status==409
    body={'definition_version':version,'revision':draft.json()['draft']['revision'],'idempotency_key':'live-once'}
    submitted=mutate(page,'POST',base+'/submit',body);assert submitted.status==201 and submitted.json()['score']==count
    again=mutate(page,'POST',base+'/submit',body);assert again.status==200 and again.json()['score']==count
    assert mutate(page,'POST',base+'/submit',{**body,'idempotency_key':'different'}).status==409
    outsider=page.context.browser.new_context()
    try:
        r=outsider.request.get(BASE+base+'/result');assert r.status==401
    finally:outsider.close()
