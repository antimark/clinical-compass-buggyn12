"""Live catalog-only regression: preserve all77 medicine source fields, real browser."""
import argparse,datetime,json,os
from pathlib import Path
from urllib.parse import urlsplit,quote
from playwright.sync_api import sync_playwright,expect

def main():
 p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8769');p.add_argument('--smoke-only',action='store_true');a=p.parse_args();assert urlsplit(a.base).hostname in ('127.0.0.1','localhost');os.environ['CC_E2E_BASE_URL']=a.base
 from tests_e2e.test_jury_live import show,test_all_medicine_source_fields_render_in_browser,MEDICINES
 root=Path(__file__).resolve().parents[1];raw=root/'reports/phase2/raw/catalog_visual_20261028.jsonl';raw.parent.mkdir(exist_ok=True,parents=True);shots=root/'docs/final_demo/screenshots/catalog_visual_20261028';shots.mkdir(exist_ok=True,parents=True);count=0
 def record(scenario,status='PASS',**extra):
  nonlocal count
  count+=1
  with raw.open('a') as f:f.write(json.dumps(dict(timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),base=a.base,scenario=scenario,status=status,**extra),ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
  if count%5==0:
   note=f'\nCatalog-only {a.base}:n={count};last={scenario} {status}; raw {raw.relative_to(root)} flushed. Existing tests reused; no full app audit.\n'
   for n in ['.agent/CHECKPOINT.md','.agent/EXECPLAN_ACTIVE.md','reports/phase2/PROGRESS.md']:
    with (root/n).open('a') as f:f.write(note)
 with sync_playwright() as pw:
  b=pw.chromium.launch();c=b.new_context(viewport={'width':1440,'height':1000},locale='ru-RU');page=c.new_page();page.set_default_timeout(15000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  for source in (MEDICINES if not a.smoke_only else [s for s in MEDICINES if s.stem in ['aviandr_maritupirdine_instruction','sertraline','lamictal_lamotrigine_25mg']]):
   try:
    test_all_medicine_source_fields_render_in_browser(page,source)
    fields=page.locator('.medicine-key-card');expect(fields).to_have_count(6);assert fields.locator('h3').all_text_contents()==['Показания и диагнозы','Дозировка','Как применять','Состав препарата','Противопоказания','Применять с осторожностью'];record('all_source_fields_'+source.stem)
   except Exception as e:record('all_source_fields_'+source.stem,'FAIL',error_class=type(e).__name__);raise
  route='/clinical-library?type=medicine&item='+quote('medicine:product:aviandr_maritupirdine_instruction')
  for theme,width,height in [('light',1440,1000),('dark',1440,1000),('light',390,844)]:
   page.set_viewport_size({'width':width,'height':height});page.evaluate('(theme)=>localStorage.setItem("cc.theme",theme)',theme);show(page,route);page.reload();expect(page.locator('.medicine-key-card')).to_have_count(6);page.wait_for_timeout(500)
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(theme,width)
   prefix='' if urlsplit(a.base).port==8769 else 'docker_';page.screenshot(path=str(shots/f'{prefix}aviandr_{theme}_{width}.png'));original=page.url
   page.get_by_role('button',name='Противопоказания',exact=True).click();target=page.locator('#medicine-contraindications');expect(target).to_be_focused();page.wait_for_timeout(500);assert page.url==original;assert 85<=target.bounding_box()['y']<=150;
   if width==1440:page.screenshot(path=str(shots/f'{prefix}aviandr_warnings_{theme}.png'))
   record('visual_jump_'+theme+'_'+str(width),screenshot=f'{prefix}aviandr_{theme}_{width}.png')
  assert not errors,errors;record('no_browser_exceptions',n=len(errors));b.close()
 print('PASS',count,'catalog-only browser checks',a.base,flush=True)
if __name__=='__main__':main()
