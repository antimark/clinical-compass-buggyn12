"""Wiring for existing domain API modules, preserving registration order."""
from __future__ import annotations
from .extension_routes import register_extension_routes
from .utilities import utc_now


def register_feature_routes(app, SessionLocal, current_user, require_role, api_error):
    register_extension_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .profile_routes import register_profile_routes
    register_profile_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .integrated_routes import register_integrated_routes
    register_integrated_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .p0_routes import register_p0_routes
    register_p0_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .p1_routes import register_p1_routes
    register_p1_routes(app, SessionLocal, require_role)

    from .onboarding_routes import register_onboarding_routes
    register_onboarding_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .patient_experience_routes import register_patient_experience_routes
    register_patient_experience_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .doctor_experience_routes import register_doctor_experience_routes
    register_doctor_experience_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .clinical_workflow_routes import register_clinical_workflow_routes
    register_clinical_workflow_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .booking_routes import register_booking_routes
    register_booking_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .reference_routes import register_reference_routes
    register_reference_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .pitch_routes import register_pitch_routes
    register_pitch_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .admin_privacy_routes import register_admin_privacy_routes
    register_admin_privacy_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .research_workflow_routes import register_research_workflow_routes
    register_research_workflow_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .clinical_review_routes import register_clinical_review_routes
    register_clinical_review_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .staff_enrollment_routes import register_staff_enrollment_routes
    register_staff_enrollment_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .admin_booking_routes import register_admin_booking_routes
    register_admin_booking_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .clinical_catalog_routes_v3 import register_clinical_catalog_routes_v3
    register_clinical_catalog_routes_v3(app)
    from .research_demo_routes_v3 import register_research_demo_v3
    register_research_demo_v3(app, SessionLocal, require_role)
    from .clinical_intelligence_routes import register_clinical_intelligence_routes
    register_clinical_intelligence_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .clinical_intelligence_review_routes import register_clinical_intelligence_review_routes
    register_clinical_intelligence_review_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .clinical_copilot_routes import register_clinical_copilot_routes
    register_clinical_copilot_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
    from .nlp_lab_routes_v3 import register_nlp_lab_v3
    register_nlp_lab_v3(app, SessionLocal, require_role)
    from .oidc_browser import register_oidc_browser
    register_oidc_browser(app, SessionLocal)

    from .safety_routes import register_safety_routes
    register_safety_routes(app, SessionLocal, current_user, require_role, api_error, utc_now)
