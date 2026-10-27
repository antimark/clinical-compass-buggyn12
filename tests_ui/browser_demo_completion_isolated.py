"""Static layout/interaction checks; never evidence of a working Flask or backend E2E."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'qa_demo_completion/screenshots'
OUT.mkdir(parents=True,exist_ok=True)
def read(p):return (ROOT/p).read_text(encoding='utf8')
styles='\n'.join(read('frontend/dist/assets/css/'+n) for n in ['tokens.css','themes.css','base.css','components.css','prototype.css','live_components.css','demo_completion_v1.css'])
boot="""window.CC={escape:x=>String(x??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]))};window.CCAPI={isMock:false};window.demoActor={user:{id:'demo_doctor_invited_01',display_name:'Дарья Лесная · синтетическая'},context:{role:'doctor'},features:{synthetic_onboarding_enabled:true}};function show(){document.getElementById('main').innerHTML=CCDemoCompletion.render('/demo/profile',demoActor)}"""
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
 for width,theme in [(360,'light'),(390,'dark'),(768,'light'),(768,'dark'),(1280,'light'),(1280,'dark')]:
  context=browser.new_context(viewport={'width':width,'height':850})
  page=context.new_page();page.set_content(f'<!doctype html><html lang="ru" data-theme="{theme}"><head><meta charset="utf-8"></head><body><div class="app-frame"><main class="main" id="main"></main></div></body></html>')
  page.add_style_tag(content=styles);page.add_script_tag(content=boot);page.add_script_tag(content=read('frontend/dist/assets/js/demo_completion_v1.js'));page.evaluate('show()')
  assert page.get_by_role('heading',name='Образование').count()==1
  assert page.get_by_role('heading',name='Публикации').count()==1
  assert page.locator('input[list="dc-specialties"]').count()>=2
  assert page.locator('form[data-form="dc-edit-education"]').count()==1
  assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2'),f'Overflow at {width}px'
  assert page.locator('input[name="institution"]').is_visible()
  page.keyboard.press('Tab');assert page.evaluate('document.activeElement !== document.body')
  page.screenshot(path=str(OUT/f'demo_profile_ISOLATED_COMPONENT_{width}_{theme}.png'),full_page=True)
  print('ISOLATED_COMPONENT_PASS',width,theme)
  context.close()
 browser.close()
