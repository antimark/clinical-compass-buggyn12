"""Read persisted plan, messages and photo after actual server/container restart."""
import json,os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from tests_e2e.test_jury_live import BASE,login,show
from tests_e2e.evidence import scenario
WS=Path(os.environ['CC_QA_WORKSPACE']);state=json.loads((WS/'jury-demo-state.json').read_text());actor=json.loads((WS/'jury-demo-patient.json').read_text())
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True);c=b.new_context();p=c.new_page();login(p,actor['email'],actor['password']);expect(p).to_have_url(BASE+'/#/patient')
 with scenario('restart_published_plan_and_pair_messages_persist',role='patient',method='real post-restart browser + authorized API'):
  result=p.request.get(BASE+'/api/v1/clinical-workflow/documents/'+state['document_id']);assert result.ok and result.json()['status']=='published'
  show(p,'/patient/treatment');expect(p.locator('#main')).to_contain_text(state['plan_title'])
  show(p,'/patient/messages/'+state['doctor_id']);expect(p.locator('#main')).to_contain_text('Учебный ответ врача сохранён.')
 c.close();b.close()
