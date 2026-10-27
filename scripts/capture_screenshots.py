"""Capture actual Buggy-based screens in a local dev environment, not fabricated assets.
Run after serving frontend/dist via python -m http.server or Flask demo.
Requires playwright and Chromium installed on the operator's machine.
"""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

url=os.environ.get('CC_SCREENSHOT_URL','http://127.0.0.1:8000/?mode=mock')
output=Path('docs/screenshots');output.mkdir(parents=True,exist_ok=True)
with sync_playwright() as playwright:
    browser=playwright.chromium.launch(headless=True)
    for width in (360,768,1280):
        page=browser.new_page(viewport={'width':width,'height':900},device_scale_factor=1)
        for theme in ('light','dark'):
            page.goto(url,wait_until='domcontentloaded')
            page.evaluate('(theme) => localStorage.setItem("cc-theme",theme)',theme)
            page.reload()
            page.wait_for_selector('h1')
            page.screenshot(path=str(output/f'landing_{width}_{theme}.png'),full_page=True)
            page.goto(url.split('#')[0]+'#/doctors',wait_until='domcontentloaded')
            page.wait_for_selector('h1')
            page.screenshot(path=str(output/f'directory_{width}_{theme}.png'),full_page=True)
        page.close()
    browser.close()
print('Saved actual screenshot grid under docs/screenshots/')
