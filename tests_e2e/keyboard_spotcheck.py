"""Focused real-browser accessibility spotchecks, not a WCAG conformance claim."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from tests_e2e.test_jury_live import BASE,show
from tests_e2e.evidence import scenario
WS=Path(os.environ['CC_QA_WORKSPACE'])
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True);context=browser.new_context(storage_state=str(WS/'restart-session.json'));page=context.new_page()
    with scenario('guest_radio_labels_and_keyboard_focus',role='guest',method='live Chromium accessibility spotcheck'):
        show(page,'/assessments/phq_2')
        assert page.locator('fieldset legend').count()==2
        assert page.locator('input[type=radio]').evaluate_all('els=>els.every(e=>e.labels.length>0)')
        page.keyboard.press('Tab');assert page.evaluate('document.activeElement.tagName')!='BODY'
    with scenario('modal_escape_restores_account_trigger_focus',role='patient',method='live Chromium keyboard spotcheck'):
        show(page,'/patient/profile');page.locator('#avatar-button').click();page.locator('[data-command=settings]').click()
        expect(page.get_by_role('dialog')).to_be_visible()
        assert page.evaluate('document.activeElement.closest("[role=dialog]")!==null')
        page.keyboard.press('Escape');expect(page.get_by_role('dialog')).to_have_count(0)
        assert page.evaluate('document.activeElement.id')=='avatar-button','Modal close lost focus to document body'
    context.close();browser.close()
