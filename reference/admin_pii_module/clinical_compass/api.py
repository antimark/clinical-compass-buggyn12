"""REST adapter. All personal data projections flow through service.py.

In a host Clinical Compass application register this Blueprint and inject the
existing db session and authenticated principal; do not trust identity headers.
"""
from __future__ import annotations
import os
import secrets
from datetime import datetime
from functools import wraps

from flask import Blueprint, Flask, request, jsonify, session, g
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from .models import (
    User, Organization, Patient, PatientClinicLink, AdminPiiTemplate,
    Membership, configure_sqlite,
)
from .security import PiiCipher, verify_password
from . import service as svc

api = Blueprint("clinic_access", __name__, url_prefix="/api/v1")


def data() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise svc.InvalidInput("JSON object expected")
    return payload


def no_extra_keys(payload: dict, allowed: set[str]):
    if set(payload) - allowed:
        raise svc.InvalidInput("Unrecognized input fields")


def actor_id() -> int:
    uid = session.get("uid")
    if type(uid) is not int:
        raise svc.AccessDenied("Authentication required")
    actor = g.db.get(User, uid)
    if actor is None or not actor.active:
        raise svc.AccessDenied("Authentication required")
    return uid


def db():
    return g.db


def pagination(default_limit: int = 50, max_limit: int = 500) -> tuple[int, int]:
    try:
        limit = int(request.args.get("limit", str(default_limit)))
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        raise svc.InvalidInput("Invalid pagination") from None
    if not (0 <= offset <= 100_000 and 1 <= limit <= max_limit):
        raise svc.InvalidInput("Invalid pagination")
    return offset, limit


@api.get("/auth/csrf")
def csrf():
    token = session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf"] = token
    return jsonify({"csrf_token": token})


@api.post("/auth/login")
def login():
    body = data()
    no_extra_keys(body, {"username", "password"})
    username = body.get("username")
    password = body.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        raise svc.InvalidInput("username and password required")
    user = db().scalar(select(User).where(User.username == username))
    # Authenticate in constant-time-ish fashion for missing usernames.
    if user is None or not user.active or not verify_password(password, user.password_hash):
        return jsonify({"error": "UNAUTHORIZED", "message": "Invalid credentials"}), 401
    session.clear()
    session["uid"] = user.id
    session["csrf"] = secrets.token_urlsafe(32)
    return jsonify({"ok": True, "csrf_token": session["csrf"]})


@api.post("/auth/logout")
def logout():
    actor_id()
    session.clear()
    return jsonify({"ok": True})


@api.get("/auth/me")
def me():
    uid = actor_id()
    return jsonify({"user_id": uid})


@api.post("/admin/fields")
def register_field():
    b = data()
    no_extra_keys(b, {"field_key", "category", "admin_pii_eligible"})
    svc.register_field(db(), actor_id(), b.get("field_key"), b.get("category"),
                       b.get("admin_pii_eligible", False))
    db().commit()
    return jsonify({"ok": True}), 201


@api.patch("/admin/features/clinic-admin-pii")
def configure_feature():
    b = data()
    no_extra_keys(b, {"organization_id", "enabled"})
    org_id = b.get("organization_id")
    if org_id is not None and (type(org_id) is not int or org_id < 1):
        raise svc.InvalidInput("organization_id must be integer or null")
    svc.set_flag(db(), actor_id(), org_id, b.get("enabled"))
    db().commit()
    return jsonify({"ok": True})


@api.post("/admin/clinics/<int:org_id>/pii-templates")
def create_template(org_id: int):
    b = data()
    no_extra_keys(b, {"template_key", "version", "read_fields"})
    template = svc.create_template(db(), actor_id(), org_id,
                                   b.get("template_key"), b.get("version"),
                                   b.get("read_fields"))
    template_id = template.id
    db().commit()
    return jsonify({"template_id": template_id}), 201


@api.get("/me/clinic-links")
def my_clinic_links():
    uid = actor_id()
    pat = db().scalar(select(Patient).where(Patient.user_id == uid))
    if pat is None:
        raise svc.AccessDenied("Patient required")
    links = db().scalars(select(PatientClinicLink).where(
        PatientClinicLink.patient_id == pat.id,
        PatientClinicLink.active.is_(True),
    )).all()
    return jsonify({"items": [{"link_id": l.id, "clinic_id": l.organization_id,
                               "patient_ref": l.local_ref} for l in links]})


@api.get("/me/clinic-links/<int:link_id>/pii-templates")
def available_patient_templates(link_id: int):
    uid = actor_id()
    link = db().get(PatientClinicLink, link_id)
    if link is None:
        raise svc.NotFound("Patient-clinic relationship not found")
    svc.ensure_patient_owner(db(), uid, link)
    templates = db().scalars(select(AdminPiiTemplate).where(
        AdminPiiTemplate.organization_id == link.organization_id,
        AdminPiiTemplate.active.is_(True),
    )).all()
    return jsonify({"items": [{"id": t.id, "key": t.template_key,
                               "version": t.version,
                               "read_fields": [r.field_key for r in t.rules if r.allow_read]}
                              for t in templates]})


@api.put("/me/clinic-links/<int:link_id>/pii-policy")
def accept_policy(link_id: int):
    b = data()
    no_extra_keys(b, {"template_id", "confirmed"})
    if type(b.get("template_id")) is not int:
        raise svc.InvalidInput("template_id must be integer")
    svc.accept_template(db(), actor_id(), link_id, b["template_id"], b.get("confirmed"))
    db().commit()
    return jsonify({"ok": True})


@api.delete("/me/clinic-links/<int:link_id>/pii-policy")
def revoke_policy(link_id: int):
    svc.revoke_policy(db(), actor_id(), link_id)
    db().commit()
    return jsonify({"ok": True})


@api.put("/me/clinic-links/<int:link_id>/pii-overrides/<field_key>")
def override_policy(link_id: int, field_key: str):
    b = data()
    no_extra_keys(b, {"effect", "expires_at"})
    expires = b.get("expires_at")
    if expires is not None:
        try:
            expires = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if expires.tzinfo is None:
                raise ValueError("timezone missing")
        except (ValueError, AttributeError):
            raise svc.InvalidInput("expires_at must be timezone-aware ISO 8601") from None
    svc.update_override(db(), actor_id(), link_id, field_key, b.get("effect"), expires)
    db().commit()
    return jsonify({"ok": True})


@api.patch("/me/profile-fields/<field_key>")
def write_field(field_key: str):
    b = data()
    no_extra_keys(b, {"value"})
    svc.write_patient_field(db(), actor_id(), field_key, b.get("value"), g.pii_cipher)
    db().commit()
    return jsonify({"ok": True})


@api.get("/clinics/<int:org_id>/patients")
def list_patients(org_id: int):
    offset, limit = pagination()
    return jsonify(svc.patient_list(db(), actor_id(), org_id, g.pii_cipher,
                                   filter_field=request.args.get("filter_field"),
                                   filter_value=request.args.get("filter_value"),
                                   sort_field=request.args.get("sort_field"),
                                   limit=limit, offset=offset))


@api.get("/clinics/<int:org_id>/patients/<patient_ref>")
def patient_detail(org_id: int, patient_ref: str):
    uid = actor_id()
    svc.ensure_clinic_admin(db(), uid, org_id)
    link = svc.get_link(db(), org_id, patient_ref)
    return jsonify(svc.patient_view(db(), uid, org_id, link, g.pii_cipher))


@api.get("/clinics/<int:org_id>/patients/export")
def patient_export(org_id: int):
    # Intentional explicit schema with no free-form column names or raw SQL.
    offset, limit = pagination(default_limit=500)
    keys = request.args.get("fields", "")
    fields = [] if not keys else keys.split(",")
    if len(fields) > 100 or len(fields) != len(set(fields)):
        raise svc.InvalidInput("Duplicate or excessive fields")
    # This API exports JSON, avoiding spreadsheet formula injection in CSV.
    projection = svc.patient_list(db(), actor_id(), org_id, g.pii_cipher,
                                  requested_fields=fields, limit=limit, offset=offset)
    return jsonify(projection)


@api.get("/clinics/<int:org_id>/notifications")
def notifications(org_id: int):
    offset, limit = pagination()
    return jsonify(svc.notification_list(db(), actor_id(), org_id, g.pii_cipher,
                                         offset=offset, limit=limit))


@api.get("/clinics/<int:org_id>/appointments")
def appointments(org_id: int):
    offset, limit = pagination()
    return jsonify(svc.appointment_list(db(), actor_id(), org_id, g.pii_cipher,
                                        offset=offset, limit=limit))


@api.post("/clinics/<int:org_id>/appointments")
def schedule(org_id: int):
    b = data()
    no_extra_keys(b, {"patient_ref", "doctor_user_id", "start_at"})
    if not isinstance(b.get("patient_ref"), str) or type(b.get("doctor_user_id")) is not int:
        raise svc.InvalidInput("patient_ref and doctor_user_id required")
    try:
        start = datetime.fromisoformat(b["start_at"].replace("Z", "+00:00"))
    except (ValueError, KeyError, AttributeError):
        raise svc.InvalidInput("start_at must be ISO 8601") from None
    appointment = svc.request_appointment(db(), actor_id(), org_id,
                                          b["patient_ref"], b["doctor_user_id"], start)
    appointment_id = appointment.id
    db().commit()
    return jsonify({"appointment_id": appointment_id}), 201


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SESSION_SECRET"),
        DATABASE_URL=os.environ.get("DATABASE_URL", "sqlite:///data/core.sqlite"),
        PII_ENCRYPTION_KEY=os.environ.get("PII_ENCRYPTION_KEY"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("APP_ENV", "production") != "development",
        MAX_CONTENT_LENGTH=128 * 1024,
    )
    if config:
        app.config.update(config)
    if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("SESSION_SECRET must be provided (>=32 chars)")
    if not app.config["PII_ENCRYPTION_KEY"]:
        raise RuntimeError("PII_ENCRYPTION_KEY must be provided outside the database")
    cipher = PiiCipher(app.config["PII_ENCRYPTION_KEY"])
    engine = create_engine(app.config["DATABASE_URL"], pool_pre_ping=True)
    configure_sqlite(engine)
    app.extensions["cc_engine"] = engine
    app.register_blueprint(api)

    @app.before_request
    def bind_request():
        g.db = Session(engine, expire_on_commit=True)
        g.pii_cipher = cipher
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            expected = session.get("csrf")
            received = request.headers.get("X-CSRF-Token")
            if not expected or not received or not secrets.compare_digest(received, expected):
                raise svc.AccessDenied("CSRF token required")

    @app.teardown_request
    def close_request(_exc):
        if getattr(g, "db", None) is not None:
            g.db.rollback()
            g.db.close()

    @app.after_request
    def secure_output(response):
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.errorhandler(svc.AccessDenied)
    def forbidden(exc):
        return jsonify({"error": "FORBIDDEN", "message": str(exc)}), 403

    @app.errorhandler(svc.NotFound)
    def not_found(exc):
        return jsonify({"error": "NOT_FOUND", "message": str(exc)}), 404

    @app.errorhandler(svc.InvalidInput)
    def bad_request(exc):
        return jsonify({"error": "BAD_REQUEST", "message": str(exc)}), 400

    @app.errorhandler(404)
    def unknown_route(_exc):
        return jsonify({"error": "NOT_FOUND", "message": "Route not found"}), 404

    @app.errorhandler(405)
    def unsupported_method(_exc):
        return jsonify({"error": "METHOD_NOT_ALLOWED", "message": "Method not allowed"}), 405

    return app
