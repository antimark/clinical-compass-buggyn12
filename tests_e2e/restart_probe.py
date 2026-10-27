"""Capture/verify one actual patient session + score across a native/container restart.
All cookie/session storage remains private outside the source tree.
"""
import argparse,hashlib,json,os,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from tests_e2e.test_jury_live import BASE,login,mutate,show
from tests_e2e.evidence import scenario
WS=Path(os.environ.get('CC_QA_WORKSPACE','/private/tmp/clinical-compass-jury-20261027'))

def private_json(path,data):
    fd=os.open(path,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:json.dump(data,f)

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['capture','verify']);args=p.parse_args()
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        if args.mode=='capture':
            context=browser.new_context();page=context.new_page()
            actor=json.loads((WS/'jury-linked-patient.json').read_text())
            with scenario('restart_capture_actual_patient_score_and_session',role='patient',method='live Flask + SQLite + Chromium'):
                login(page,actor['email'],actor['password']);expect(page).to_have_url(BASE+'/#/patient')
                prefix='/api/v1/patient-experience/questionnaires'
                assigned=mutate(page,'POST',prefix+'/self-assign',{'definition_id':'eval_phq_2_v1'}).json();aid=assigned['id'];base=prefix+'/assignments/'+aid
                detail=page.request.get(BASE+base).json();answers={q['id']:2 for q in detail['definition']['questions']};version=detail['assignment']['definition_version']
                draft=mutate(page,'PUT',base+'/draft',{'definition_version':version,'revision':detail['draft']['revision'],'answers':answers,'last_page':0});assert draft.ok
                submitted=mutate(page,'POST',base+'/submit',{'definition_version':version,'revision':draft.json()['draft']['revision'],'idempotency_key':'restart-proof'});assert submitted.ok and submitted.json()['score']==4
                private_json(WS/'restart-session.json',context.storage_state())
                private_json(WS/'restart-probe.json',{'assignment':aid,'score':4,'key_hashes':{name:hashlib.sha256((WS/name).read_bytes()).hexdigest() for name in ('session.secret','identity-fernet.key')}})
        else:
            data=json.loads((WS/'restart-probe.json').read_text())
            context=browser.new_context(storage_state=str(WS/'restart-session.json'));page=context.new_page()
            with scenario('restart_preserves_actual_session_score_history_and_keys',role='patient',method='live Flask + SQLite + Chromium'):
                me=page.request.get(BASE+'/api/v1/auth/me');assert me.ok,'Session invalid after restart'
                result=page.request.get(BASE+'/api/v1/patient-experience/questionnaires/assignments/'+data['assignment']+'/result')
                assert result.ok and result.json()['score']==data['score']
                show(page,'/patient/profile');page.get_by_role('link',name='Открыть историю результатов').click()
                target=page.locator('a[href="/#/patient/questionnaires/'+data['assignment']+'/result"]');expect(target).to_be_visible();target.click()
                expect(page.locator('#main')).to_contain_text('4 из 6 баллов')
                for name,digest in data['key_hashes'].items():assert hashlib.sha256((WS/name).read_bytes()).hexdigest()==digest
        context.close();browser.close()
if __name__=='__main__':main()
