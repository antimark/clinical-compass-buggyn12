"""Cross-cutting request IDs, CSRF check, response headers and API errors."""
from __future__ import annotations
import hmac
import uuid
from flask import request, session


def register_http_hooks(app, api_error):
    @app.before_request
    def before_api():
        request.environ['cc.request_id'] = uuid.uuid4().hex[:12]
        if request.path.startswith('/api/v1/') and request.method in ('POST', 'PATCH', 'PUT', 'DELETE'):
            # Bearer identity has precedence and cannot fall back to a cookie.
            # Cookie mutations require CSRF in both demo and real-IdP profiles.
            if not app.config['DEMO_MODE'] and request.headers.get('Authorization'):
                return None
            expected = session.get('csrf_token')
            supplied = request.headers.get('X-CSRF-Token', '')
            if not expected or not hmac.compare_digest(expected, supplied):
                return api_error(403, 'CSRF_FAILED', 'CSRF token required')

    @app.after_request
    def after_api(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if request.path == '/' or request.path.startswith('/assets/'):
            response.headers['Content-Security-Policy'] = "default-src 'self'; base-uri 'self'; object-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        if app.config['SESSION_COOKIE_SECURE']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        if request.path.startswith('/api/v1/'):
            response.headers['X-Request-ID'] = request.environ.get('cc.request_id', '')
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(401)
    def handler_401(_):
        return api_error(401, 'UNAUTHORIZED', 'Требуется вход')

    @app.errorhandler(403)
    def handler_403(_):
        return api_error(403, 'FORBIDDEN', 'Недостаточно прав')

    @app.errorhandler(422)
    def handler_422(exc):
        if request.path.startswith('/api/v1/'):
            detail = getattr(exc, 'description', '')
            generic = ('The request was well-formed', 'Unprocessable Entity')
            message = detail if detail and not any(x in detail for x in generic) else 'Проверьте обязательные поля и ограничения формы.'
            return api_error(422, 'INVALID_INPUT', message)
        return 'Invalid input', 422

    @app.errorhandler(404)
    def handler_404(_):
        if request.path.startswith('/api/v1/'):
            return api_error(404, 'NOT_FOUND', 'Ресурс не найден')
        return 'Not found', 404

