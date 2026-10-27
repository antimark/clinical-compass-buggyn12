"""Actual invitation copy action; no token or clipboard value is exported."""
import json,os,secrets
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from tests_e2e.test_jury_live import BASE,show,login,mutate
from tests_e2e.evidence import scenario
WS=Path(os.environ['CC_QA_WORKSPACE'])
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True);c=b.new_context(permissions=['clipboard-read','clipboard-write']);p=c.new_page();actor=json.loads((WS/'jury-actors.json').read_text())['doctor'];login(p,actor['email'],actor['password']);expect(p).to_have_url(BASE+'/#/doctor')
 with scenario('invitation_copy_action_actual_clipboard',role='doctor',method='real browser clipboard; token retained privately and invitation revoked after check'):
  show(p,'/doctor/invitations');f=p.locator('[data-form=create-invitation]');f.locator('[name=recipient_email]').fill('clipboard-'+secrets.token_hex(5)+'@evaluation.test');f.locator('[name=category]').first.check()
  with p.expect_response(lambda r:r.url.endswith('/onboarding/invitations') and r.request.method=='POST') as made:f.locator('button').click()
  assert made.value.status==201;data=made.value.json()
  try:
   p.locator('#created-invitation [data-command=copy-invite]').click()
   assert p.evaluate('navigator.clipboard.readText()')==data['absolute_url']
  finally:assert mutate(p,'POST','/api/v1/onboarding/invitations/'+data['id']+'/revoke',{}).ok
 c.close();b.close()
