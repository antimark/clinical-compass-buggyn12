"""Authorization-code/S256 browser login with one-use database state.

Wiring: register_oidc_browser(app, SessionLocal); call browser_user(db) before
resource-server authentication and revoke_browser_session(db) on logout or role
switch. Configure CC_OIDC_BROWSER_ENABLED=1, issuer/client/redirect plus pinned
JWKS. No discovery redirects, dynamic issuer, token persistence or role creation.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from flask import abort, jsonify, redirect, request, session
from sqlalchemy import select, update
from .identity import decode_identity_token, has_staff_assurance
from .models import User
from .extension_models import Audit
from .oidc_models import OidcBrowserSession, OidcLoginAttempt


PREFIX = '/api/v1/auth/oidc'


def now():
    return datetime.now(timezone.utc)


def stamp(value):
    return value.isoformat(timespec='microseconds').replace('+00:00', 'Z')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def settings():
    if os.environ.get('CC_OIDC_BROWSER_ENABLED') != '1':
        return None
    issuer = os.environ.get('CC_OIDC_ISSUER', '').rstrip('/')
    client = os.environ.get('CC_OIDC_CLIENT_ID', '')
    target = os.environ.get('CC_OIDC_REDIRECT_URI', '')
    for value in (issuer, target):
        parsed = urlsplit(value)
        # Explicit loopback HTTP is solely for the isolated real-IdP test stack.
        local = (os.environ.get('CC_OIDC_ALLOW_LOOPBACK_HTTP') == '1' and
                 parsed.hostname in ('127.0.0.1', 'localhost') and parsed.scheme == 'http')
        if not parsed.netloc or parsed.username or parsed.password or parsed.fragment or parsed.query or (parsed.scheme != 'https' and not local):
            raise RuntimeError('OIDC requires trusted absolute HTTPS endpoints')
    if not client or not os.environ.get('CC_OIDC_JWKS_JSON'):
        raise RuntimeError('OIDC client and pinned JWKS required')
    return issuer, client, target


def browser_user(db):
    """Return only the current provisioned identity; role remains in User."""
    if not settings():
        return None
    token = session.get('oidc_session')
    if not isinstance(token, str):
        return None
    row = db.scalar(select(OidcBrowserSession).where(OidcBrowserSession.token_hash == digest(token)))
    if not row or row.revoked_at or row.expires_at <= stamp(now()) or row.issuer != settings()[0]:
        return None
    user = db.get(User, row.user_id)
    if not user or user.external_subject != row.external_subject:
        return None
    claims = {'amr': json.loads(row.amr_json), 'acr': row.acr}
    return user if user.role == 'patient' or has_staff_assurance(claims) else None


def revoke_browser_session(db):
    token = session.get('oidc_session')
    if isinstance(token, str):
        db.execute(update(OidcBrowserSession).where(
            OidcBrowserSession.token_hash == digest(token), OidcBrowserSession.revoked_at.is_(None)
        ).values(revoked_at=stamp(now())))


def exchange_code(issuer, client, target, code, verifier):
    data = urlencode({'grant_type': 'authorization_code', 'client_id': client,
        'redirect_uri': target, 'code': code, 'code_verifier': verifier}).encode()
    req = Request(issuer + '/protocol/openid-connect/token', data=data,
                  headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'})
    # Default TLS verification remains enabled; endpoint is operator pinned.
    with urlopen(req, timeout=10) as response:
        value = response.read(131073)
    if len(value) > 131072:
        raise ValueError('Oversized identity response')
    return json.loads(value)


def register_oidc_browser(app, SessionLocal):
    # Validate once at startup, so malformed configuration cannot silently turn
    # a configured deployment into an unauthenticated prototype.
    settings()

    @app.get(PREFIX + '/capabilities')
    def oidc_capabilities():
        return {'enabled': settings() is not None, 'login_url': PREFIX + '/login',
                'staff_mfa_required': True, 'role_source': 'preprovisioned_user'}

    @app.post(PREFIX + '/logout')
    def oidc_logout():
        if not settings():
            abort(404)
        # Self-contained CSRF check also protects callers if central middleware
        # changes; logout is a persisted revocation before cookie removal.
        supplied = request.headers.get('X-CSRF-Token', '')
        expected = session.get('csrf_token')
        if not isinstance(expected, str) or not hmac.compare_digest(expected, supplied):
            abort(403)
        with SessionLocal.begin() as db:
            user = browser_user(db)
            revoke_browser_session(db)
            if user:
                db.add(Audit(id=uuid.uuid4().hex, actor=user.id, action='oidc.logout',
                    object_type='oidc_session', object_id=user.id, created_at=stamp(now())))
        session.clear()
        return {'status': 'logged_out'}

    @app.get(PREFIX + '/login')
    def oidc_login():
        config = settings()
        if not config:
            abort(404)
        issuer, client, target = config
        return_to = request.args.get('return_to', '/')
        # Only local fragment routes are accepted. No open redirect or host path.
        if return_to != '/' and (not return_to.startswith('/#/') or len(return_to) > 256 or '\\' in return_to or '\r' in return_to or '\n' in return_to):
            abort(422)
        state, nonce, verifier, binding = [secrets.token_urlsafe(40) for _ in range(4)]
        created = now()
        with SessionLocal.begin() as db:
            db.execute(update(OidcLoginAttempt).where(
                OidcLoginAttempt.expires_at <= stamp(created)).values(verifier=''))
            db.add(OidcLoginAttempt(id='oidc_' + uuid.uuid4().hex, state_hash=digest(state),
                nonce_hash=digest(nonce), verifier=verifier, browser_hash=digest(binding),
                return_to=return_to, created_at=stamp(created), expires_at=stamp(created + timedelta(minutes=5))))
        session['oidc_binding'] = binding
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        return redirect(issuer + '/protocol/openid-connect/auth?' + urlencode({
            'client_id': client, 'redirect_uri': target, 'response_type': 'code',
            'scope': 'openid', 'state': state, 'nonce': nonce,
            'code_challenge': challenge, 'code_challenge_method': 'S256'}))

    @app.get(PREFIX + '/callback')
    def oidc_callback():
        config = settings()
        if not config:
            abort(404)
        state, binding = request.args.get('state', ''), session.get('oidc_binding')
        if not isinstance(binding, str) or not 20 <= len(state) <= 200:
            return jsonify(error={'code': 'OIDC_STATE_INVALID', 'message': 'Вход устарел. Начните заново.'}), 400
        timestamp = stamp(now())
        with SessionLocal.begin() as db:
            # Consumption committed before network I/O. Failed exchanges cannot
            # replay state; concurrent callbacks admit at most one request.
            attempt = db.scalar(select(OidcLoginAttempt).where(OidcLoginAttempt.state_hash == digest(state)))
            if not attempt or not hmac.compare_digest(attempt.browser_hash, digest(binding)):
                abort(400)
            verifier, nonce_hash, return_to = attempt.verifier, attempt.nonce_hash, attempt.return_to
            consumed = db.execute(update(OidcLoginAttempt).where(
                OidcLoginAttempt.id == attempt.id, OidcLoginAttempt.consumed_at.is_(None),
                OidcLoginAttempt.expires_at > timestamp).values(consumed_at=timestamp, verifier='')).rowcount
            if consumed != 1:
                abort(400)
        session.pop('oidc_binding', None)
        if request.args.get('error') or not request.args.get('code'):
            return jsonify(error={'code': 'OIDC_DECLINED', 'message': 'Вход не завершён.'}), 400
        try:
            issuer, client, target = config
            token_data = exchange_code(issuer, client, target, request.args['code'], verifier)
            claims = decode_identity_token(token_data['id_token'], audience=client)
            if not hmac.compare_digest(digest(claims.get('nonce', '')), nonce_hash):
                raise ValueError('Nonce mismatch')
            if claims.get('azp', client) != client or (isinstance(claims['aud'], list) and len(claims['aud']) > 1 and claims.get('azp') != client):
                raise ValueError('Authorized party mismatch')
            with SessionLocal.begin() as db:
                user = db.scalar(select(User).where(User.external_subject == claims['sub']))
                if not user or (user.role != 'patient' and not has_staff_assurance(claims)):
                    raise ValueError('Identity not provisioned or staff assurance absent')
                revoke_browser_session(db)
                created = now()
                expiry = min(datetime.fromtimestamp(claims['exp'], timezone.utc), created + timedelta(hours=8))
                opaque = secrets.token_urlsafe(48)
                db.add(OidcBrowserSession(id='oids_' + uuid.uuid4().hex, token_hash=digest(opaque),
                    user_id=user.id, external_subject=claims['sub'], issuer=issuer,
                    auth_time=stamp(datetime.fromtimestamp(claims.get('auth_time', claims['iat']), timezone.utc)),
                    expires_at=stamp(expiry), created_at=stamp(created), amr_json=json.dumps(claims.get('amr', [])),
                    acr=claims.get('acr')))
                db.add(Audit(id=uuid.uuid4().hex, actor=user.id, action='oidc.login',
                    object_type='oidc_session', object_id=user.id, created_at=stamp(created)))
                user_role = user.role
        except Exception:
            # Never echo token, code, verifier, subject or IdP error details.
            return jsonify(error={'code': 'OIDC_LOGIN_REJECTED', 'message': 'Не удалось подтвердить вход или права доступа.'}), 401
        session.clear()
        session['oidc_session'] = opaque
        session['csrf_token'] = secrets.token_urlsafe(24)
        if return_to == '/':
            return_to = '/#/patient' if user_role == 'patient' else '/#/doctor' if user_role == 'doctor' else '/#/settings'
        return redirect(return_to)
