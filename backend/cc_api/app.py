"""Flask application factory: configuration, persistence, fixtures and routing."""
from __future__ import annotations
from pathlib import Path
from flask import Flask, abort, render_template

# Import model modules before Alembic schema initialization; do not remove.
from . import (extension_models, p0_models, onboarding_models,
               patient_experience_models, doctor_experience_models,
               clinical_workflow_models, reference_models,
               physician_history_models, pitch_models, admin_privacy_models,
               oidc_models, research_workflow_models, clinical_review_models,
               staff_enrollment_models, clinical_copilot_models)
from . import safety_models
from .config import configure_app
from .database import initialize_database
from .demo_fixtures import initialize_demo_fixtures
from .core_routes import register_core_routes
from .feature_registry import register_feature_routes


def create_app(test_config: dict | None = None):
    project_root = Path(__file__).resolve().parents[2]
    dist = project_root / 'frontend' / 'dist'
    # Keep the original Flask import name, template root and static behavior.
    app = Flask('cc_api', template_folder=str(dist), static_folder=None)
    configure_app(app, project_root, test_config)
    SessionLocal = initialize_database(app, project_root)
    initialize_demo_fixtures(app, SessionLocal)
    current_user, require_role, api_error = register_core_routes(app, SessionLocal)
    register_feature_routes(app, SessionLocal, current_user, require_role, api_error)
    from .evaluation_workspace import register_evaluation_policy
    register_evaluation_policy(app)

    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def frontend(path):
        # Serve the checked-in vanilla frontend assets through Flask.
        if path.startswith('api/'):
            abort(404)
        if not (dist / 'index.html').exists():
            return 'Build frontend first (npm run build). API is available at /api/v1/health.', 404
        if path and (dist / path).is_file():
            from flask import send_from_directory
            return send_from_directory(dist, path)
        return render_template('index.html')

    return app
