"""Actual absent-model UI fallback probe; never counted as successful AI inference."""
import json,os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from tests_e2e.test_jury_live import BASE,login,show
from tests_e2e.evidence import scenario,OUT
workspace=Path(os.environ['CC_QA_WORKSPACE']);actor=json.loads((workspace/'jury-actors.json').read_text())['doctor']
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True);context=browser.new_context();page=context.new_page()
    with scenario('container_absent_model_shows_honest_fallback_and_working_return',role='doctor',method='real Flask/Ollama missing-model response + Chromium'):
        login(page,actor['email'],actor['password']);expect(page).to_have_url(BASE+'/#/doctor');show(page,'/doctor/nlp-lab')
        with page.expect_response(lambda r:r.url.endswith('/nlp-v3/synthetic-extract') and r.request.method=='POST') as analyzed:page.locator('form[data-form=nlp] button').click()
        data=analyzed.value.json();assert analyzed.value.ok and data['fallback_used'] is True
        assert data['mode']=='deterministic_mock_fallback' and data['error_code']=='model_unavailable'
        expect(page.locator('#nlp-result')).to_contain_text('явно обозначенный детерминированный')
        page.locator('#nlp-result').get_by_role('link',name='Перейти к Clinical Copilot').click()
        expect(page).to_have_url(BASE+'/#/doctor/clinical-copilot')
        (OUT/'absent-model-metadata.json').write_text(json.dumps({k:data[k] for k in ('mode','error_code','fallback_used','diagnostics','persisted')},indent=2))
    context.close();browser.close()
