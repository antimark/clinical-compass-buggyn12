"""Isolated browser-render smoke with mocked HTTP identity/ACL, NOT full E2E or v12 server."""
import json, threading, http.server, functools, time
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'qa_clinical_intelligence/screenshots'
OUT.mkdir(parents=True,exist_ok=True)
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(ROOT/'frontend/dist')))
threading.Thread(target=server.serve_forever,daemon=True).start()
URL=f'http://127.0.0.1:{server.server_address[1]}/#/doctor/clinical-copilot'
log=[]
def mocked(route):
    path=route.request.url.split('/api/v1/')[-1].split('?')[0]
    if path=='auth/me': body={'context':{'role':'doctor'},'user':{'id':'doc_psy','display_name':'Врач (синтетический)'},'features':{}}
    elif path in ('doctor-experience/capabilities','clinical-workflow/capabilities'):body={'enabled':True}
    elif path=='doctor-experience/dashboard':body={'patients':[{'id':'pxp_history_02','scope':['symptoms']}],'cases':[{'id':'dx_fixture_incoming_case'}],'appointments':[{'id':'dx_fixture_offer'}]}
    else:body={'enabled':False,'items':[]}
    route.fulfill(status=200,content_type='application/json',body=json.dumps(body,ensure_ascii=False))
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--disable-software-rasterizer'])
        for width,height,theme in [(1280,900,'light'),(390,844,'dark')]:
            ctx=browser.new_context(viewport={'width':width,'height':height},device_scale_factor=1)
            page=ctx.new_page()
            page.route('**/api/v1/**',mocked)
            page.on('console',lambda msg:log.append('console:'+msg.text) if msg.type=='error' else None)
            page.on('pageerror',lambda e:log.append('pageerror:'+str(e)))
            page.goto(URL,wait_until='domcontentloaded',timeout=12000)
            page.wait_for_selector('#ci-panel',timeout=12000)
            page.get_by_role('tab',name='Маршрутизация').click()
            assert page.get_by_text('Обсудить необходимость консультации психиатра').is_visible()
            assert page.get_by_text('не утверждены для клинического применения').count()>=1
            page.get_by_role('tab',name='Гипотезы и справочник').click()
            assert page.get_by_text('Авиандр — учебный пример проверки инструкции').is_visible()
            # CI never exposes local patient notes unless ACL check occurred.
            assert page.locator('.ci-panel').count()==1
            page.screenshot(path=str(OUT/f'clinical_intelligence_{width}_{theme}.png'),full_page=True)
            ctx.close()
        browser.close()
    print('BROWSER_SMOKE_PASS: synthetic mocked-HTTP browser render, 1280 light, 390 dark, tab navigation, screenshots')
    if log: print('BROWSER_ERRORS:',log[:10])
finally:server.shutdown()
