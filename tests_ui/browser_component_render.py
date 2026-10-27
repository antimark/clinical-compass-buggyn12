"""Isolated static CI component rendering with mocked adapter, NOT a live product journey."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'qa_clinical_intelligence/screenshots'
OUT.mkdir(parents=True,exist_ok=True)
def load(p):return (ROOT/p).read_text(encoding='utf8')
styles='\n'.join(load('frontend/dist/assets/css/'+name) for name in ['tokens.css','themes.css','base.css','components.css','clinical_intelligence_v1.css'])
boot='''window.CCAPI={async get(path){if(path.includes('/capabilities'))return {enabled:true};if(path.endsWith('/dashboard'))return {patients:[{id:'pxp_history_02',scope:['symptoms']}],cases:[{id:'dx_fixture_incoming_case'}],appointments:[{id:'dx_fixture_offer'}]};throw Error(path);}};window.fetch=async()=>({ok:true,json:async()=>JSON.parse(window.fixtureText)});'''
import json
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--disable-gpu'])
 for width,height,theme in [(1280,900,'light'),(390,844,'dark')]:
  ctx=browser.new_context(viewport={'width':width,'height':height})
  page=ctx.new_page()
  page.set_content('<!doctype html><html lang="ru" data-theme="'+theme+'"><head><meta charset="utf-8"></head><body><main id="main" class="main"></main></body></html>')
  page.add_style_tag(content=styles)
  page.add_script_tag(content=load('frontend/dist/assets/js/components.js'))
  page.evaluate('window.fixtureText='+json.dumps(load('frontend/dist/assets/fixtures/clinical_intelligence_synthetic_v1.json'),ensure_ascii=False))
  page.add_script_tag(content=boot)
  page.add_script_tag(content=load('frontend/dist/assets/js/clinical_intelligence_adapter_v1.js'))
  page.add_script_tag(content=load('frontend/dist/assets/js/clinical_intelligence_v1.js'))
  page.evaluate('''async()=>{const html=await window.CCClinicalIntelligence.enhance('/doctor/patients/pxp_history_02/visits','<h1>Карта пациента · учебный экран</h1>',{context:{role:'doctor'},user:{id:'doc_psy'}});document.getElementById('main').innerHTML=html;}''')
  assert page.locator('#ci-panel').count()==1
  page.locator('[data-ci-tab="routing"]').click(force=True)
  page.evaluate("window.CCClinicalIntelligence.action(document.querySelector('[data-ci-tab=\"routing\"]'))")
  assert page.locator('#ci-pane-routing').is_visible()
  page.screenshot(path=str(OUT/f'ci_isolated_{width}_{theme}.png'),full_page=True)
  page.evaluate("""() => {document.getElementById('main').insertAdjacentHTML('afterbegin','<form data-form="cw-save"><textarea name="narrative"></textarea></form>');window.confirm=()=>true;}""")
  page.evaluate("window.CCClinicalIntelligence.action(document.querySelector('[data-ci-tab=\"draft\"]'))")
  page.evaluate("window.CCClinicalIntelligence.action(document.querySelector('[data-ci-id=\"draft-complaints\"]'))")
  assert page.locator('form[data-form="cw-save"] textarea[name="narrative"]').input_value().startswith('[CI / учебная заметка')
  assert 'Сервер ничего не сохранил' in page.locator('#ci-feedback').inner_text()
  print('ISOLATED_RENDER_PASS',width,theme)
  ctx.close()
 browser.close()
