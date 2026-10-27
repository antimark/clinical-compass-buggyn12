"""Keep full Playwright trace private; export only a redacted network/navigation timeline."""
import datetime as dt,json,os,re,time
from pathlib import Path
from urllib.parse import urlsplit,parse_qsl,urlencode
from playwright.sync_api import sync_playwright,expect
from tests_e2e.test_jury_live import BASE,show
from tests_e2e.evidence import ROOT,OUT,scenario
WS=Path(os.environ.get('CC_QA_WORKSPACE','/private/tmp/clinical-compass-jury-20261027'))

def safe_url(url):
    u=urlsplit(url);path=re.sub(r'[a-f0-9]{16,64}','OBJECT',u.path)
    query=urlencode([(k,'OBJECT' if k in ('patient_id','encounter_id','source_version','grant_version','token') else v) for k,v in parse_qsl(u.query)])
    return path+('?' + query if query else '')

def main():
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        context=browser.new_context(storage_state=str(WS/'restart-session.json'))
        context.tracing.start(screenshots=True,snapshots=True,sources=False)
        page=context.new_page()
        def response(r):
            with (OUT/'browser-timeline.jsonl').open('a') as f:
                f.write(json.dumps({'timestamp':dt.datetime.now(dt.timezone.utc).isoformat(),'method':r.request.method,'path':safe_url(r.url),'status':r.status})+'\n');f.flush();os.fsync(f.fileno())
        page.on('response',response)
        with scenario('traced_restart_history_and_catalog_controls',role='patient',method='real Chromium trace; redacted timeline exported'):
            data=json.loads((WS/'restart-probe.json').read_text());show(page,'/patient/profile')
            page.get_by_role('link',name='Открыть историю результатов').click()
            page.locator('a[href="/#/patient/questionnaires/'+data['assignment']+'/result"]').click()
            expect(page.locator('#main')).to_contain_text('4 из 6 баллов')
            show(page,'/clinical-library?type=medicine')
            page.get_by_role('link',name='Следующая',exact=True).click()
            expect(page.locator('#main')).to_contain_text('Страница 2 из 2')
        dest=WS/'traces';dest.mkdir(mode=0o700,exist_ok=True)
        trace=dest/('native-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.zip')
        context.tracing.stop(path=str(trace));trace.chmod(0o600)
        print('Private Playwright trace captured outside source; shared evidence has no headers, cookies or request bodies.')
        context.close();browser.close()
if __name__=='__main__':main()
