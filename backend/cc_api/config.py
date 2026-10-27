"""Flask runtime settings and explicit demo/non-demo safety gates."""
from __future__ import annotations
import os


def configure_app(app, project_root, test_config: dict | None = None):
    app.config.update(
        SECRET_KEY=os.environ.get('CC_SECRET_KEY', 'UNSAFE_SYNTHETIC_DEMO_ONLY'),
        DB_PATH=os.environ.get('CC_DB_PATH', str(project_root / 'backend' / 'data' / 'dev.sqlite')),
        DEMO_MODE=os.environ.get('CC_DEMO_MODE', '0') == '1',
        APP_ENV=os.environ.get('CC_APP_ENV', 'development'),
        SEED_PATIENT_PERSONAS=os.environ.get('CC_SEED_PATIENT_PERSONAS', '0') == '1',
        PUBLIC_BASE_URL=os.environ.get('CC_PUBLIC_BASE_URL', 'http://127.0.0.1:8765'),
        EVALUATION_ACKNOWLEDGED=os.environ.get('CC_EVALUATION_ACKNOWLEDGED', '0') == '1',
        EVALUATION_TENANT='evaluation_sandbox',
        CI_REFERRALS_V1=os.environ.get('CC_CI_REFERRALS_V1', '0') == '1',
        CI_SAFETY_V1=os.environ.get('CC_CI_SAFETY_V1', '0') == '1',
        CI_CHAT_V1=os.environ.get('CC_CI_CHAT_V1', '0') == '1',
        CI_CHAT_PROVIDER=os.environ.get('CC_CI_CHAT_PROVIDER','ollama'),
        CI_CHAT_TIMEOUT=90,
        CI_REVIEW_V1=os.environ.get('CC_CI_REVIEW_V1', '0') == '1',
        CI_PROPOSALS_V1=os.environ.get('CC_CI_PROPOSALS_V1', '0') == '1',
        CI_API_V1=os.environ.get('CC_CI_API_V1', '0') == '1',
        CI_NLP_PROVIDER=os.environ.get('CC_CI_NLP_PROVIDER', 'ollama'),
        CI_NLP_MODEL=os.environ.get('CC_CI_NLP_MODEL', 'qwen3:4b-instruct'),
        CI_NLP_TIMEOUT=45,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('CC_HTTPS', '0') == '1',
    )
    if test_config:
        app.config.update(test_config)
    if app.config.get('APP_ENV') == 'evaluation_sandbox':
        from .verification import evaluation_enabled
        from pathlib import Path
        if not evaluation_enabled(app.config):
            raise RuntimeError('Evaluation requires explicit acknowledgement and isolated tenant')
        if app.config['SECRET_KEY'] == 'UNSAFE_SYNTHETIC_DEMO_ONLY':
            raise RuntimeError('Evaluation requires a unique session secret')
        if os.environ.get('CC_DATABASE_URL') or Path(app.config['DB_PATH']).resolve() == (project_root/'backend/data/dev.sqlite').resolve():
            raise RuntimeError('Evaluation requires its own explicit SQLite DB path; external DB requires separate acceptance')
        app.config['AUTO_SEED_DEMO'] = False
        # Functional availability defaults on in the explicitly isolated evaluation deployment.
        for key in ('CI_API_V1','CI_REVIEW_V1','CI_PROPOSALS_V1','CI_REFERRALS_V1','CI_CHAT_V1','CI_SAFETY_V1'):
            if (not test_config or key not in test_config) and 'CC_'+key not in os.environ:
                app.config[key] = True
    if not app.config['DEMO_MODE']:
        if app.config['SECRET_KEY'] == 'UNSAFE_SYNTHETIC_DEMO_ONLY':
            raise RuntimeError('Set a unique CC_SECRET_KEY before disabling synthetic demo mode')
        if not all(os.environ.get(n) for n in ('CC_OIDC_JWKS_JSON','CC_OIDC_ISSUER','CC_OIDC_AUDIENCE')):
            raise RuntimeError('OIDC issuer, audience and pinned JWKS are required for non-demo deployment')
        if not app.config['SESSION_COOKIE_SECURE']:
            raise RuntimeError('Set CC_HTTPS=1 and use HTTPS for non-demo deployment')

