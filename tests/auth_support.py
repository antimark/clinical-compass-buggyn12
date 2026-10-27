"""Synthetic test identities via real CSRF-protected password/session endpoints."""
from functools import lru_cache
from pathlib import Path
import re
from werkzeug.security import generate_password_hash
from cc_api.onboarding_models import LocalIdentity

_TEST_PASSWORD = 'Isolated-synthetic-tests-42'

@lru_cache(maxsize=1)
def test_password_hash():
    return generate_password_hash(_TEST_PASSWORD, method='pbkdf2:sha256:600000')


def login_response(client, uid):
    # Change credentials only in the caller's TESTING disposable DB; never bypass auth.
    assert client.application.testing
    with client.application.extensions['cc_session_factory'].begin() as db:
        identity = db.get(LocalIdentity, uid)
        assert identity is not None, 'Synthetic test identity must exist'
        identity.password_hash = test_password_hash()
        email = identity.email
    boot = client.get('/api/v1/onboarding/bootstrap')
    assert boot.status_code == 200 and boot.json['enabled']
    response = client.post('/api/v1/onboarding/login', json={'email': email, 'password': _TEST_PASSWORD},
                           headers={'X-CSRF-Token': boot.json['csrf_token']})
    assert response.status_code == 200, 'Synthetic password login failed'
    assert response.json['user']['id'] == uid
    assert response.json['csrf_token'] != boot.json['csrf_token']
    return response


@lru_cache(maxsize=1)
def private_demo_passwords():
    # Live server has its original hashes. Plain credentials remain ignored by Git.
    path = Path(__file__).resolve().parents[1] / 'Clinical_Compass_Demo_Accounts.txt'
    return dict(re.findall(r'Email:\s*(\S+)\s+Пароль:\s*(\S+)', path.read_text()))


def browser_login(page, base, uid):
    from playwright.sync_api import expect
    page.goto(base + '/#/login')
    form = page.locator('form[data-form="ob-login"]')
    expect(form).to_be_visible()
    email = uid + '@compass-demo.test'
    form.locator('[name=email]').fill(email)
    form.locator('[name=password]').fill(private_demo_passwords()[email])
    with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/api/v1/onboarding/login')) as logged:
        form.locator('button[type=submit]').click()
    assert logged.value.status == 200, 'Synthetic browser login failed'
    result = logged.value.json()
    assert result['user']['id'] == uid
    expect(page.locator('#cc-main')).to_have_attribute('aria-busy', 'false')
    return result
