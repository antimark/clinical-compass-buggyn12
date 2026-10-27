"""Explicit synthetic fixture: use normal authenticated HTTP to build four-form history."""
import json,os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from tests_e2e.test_jury_live import BASE,login,mutate
from tests_e2e.evidence import scenario
WS=Path(os.environ['CC_QA_WORKSPACE'])
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True);context=browser.new_context();page=context.new_page()
    actor=json.loads((WS/'jury-linked-patient.json').read_text());login(page,actor['email'],actor['password']);expect(page).to_have_url(BASE+'/#/patient')
    for code in ('phq_9','phq_2','gad_7','gad_2'):
        with scenario('coherent_fixture_history_'+code,role='patient',method='real authenticated HTTP; explicit synthetic fixture'):
            prefix='/api/v1/patient-experience/questionnaires';key='coherent-fixture-'+code
            assigned=mutate(page,'POST',prefix+'/self-assign',{'definition_id':'eval_'+code+'_v1','idempotency_key':key});assert assigned.ok;aid=assigned.json()['id'];base=prefix+'/assignments/'+aid
            detail=page.request.get(BASE+base).json();version=detail['assignment']['definition_version']
            if detail['assignment']['status']!='submitted':
                answers={q['id']:1 for q in detail['definition']['questions']}
                draft=mutate(page,'PUT',base+'/draft',{'definition_version':version,'revision':detail['draft']['revision'],'answers':answers,'last_page':0});assert draft.ok
                result=mutate(page,'POST',base+'/submit',{'definition_version':version,'revision':draft.json()['draft']['revision'],'idempotency_key':key});assert result.ok
            result=page.request.get(BASE+base+'/result');assert result.ok and result.json()['score']==len(detail['definition']['questions'])
    context.close();browser.close()
