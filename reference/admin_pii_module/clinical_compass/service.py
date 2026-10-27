"""One authorization boundary for lists, search, export, notifications and scheduling.

All admin-visible values are created here after DB-backed, current-request checks.
Do not expose raw SQLAlchemy entities or serialize a patient's __dict__.
"""
from __future__ import annotations
from datetime import datetime, timezone
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    User, Organization, Membership, Patient, PatientClinicLink,
    DoctorPatientLink, FieldDefinition, PatientFieldValue,
    FeatureFlag, AdminPiiTemplate, AdminPiiTemplateRule, AdminPiiPolicy,
    AdminPiiOverride, Appointment, Notification, AuditEvent, now_utc,
)
from .security import PiiCipher

FEATURE = "clinic_admin_identifying_data"
ELIGIBLE_CATEGORIES = {"IDENTITY", "CONTACT"}
ADMIN_NOTIFICATION_KINDS = {"APPOINTMENT_REQUESTED", "APPOINTMENT_CANCELLED", "APPOINTMENT_RESCHEDULED"}
BASE_FIELDS = {"first_name", "last_name", "middle_name", "phone", "email"}


class AccessDenied(Exception):
    pass


class NotFound(Exception):
    pass


class InvalidInput(Exception):
    pass


def audit(db: Session, actor: int, action: str, kind: str, ref: str | int):
    db.add(AuditEvent(actor_user_id=actor, action=action, target_kind=kind, target_id=str(ref)))


def ensure_platform_admin(db: Session, actor_id: int) -> None:
    actor = db.get(User, actor_id)
    if actor is None or not actor.active or not actor.is_platform_admin:
        raise AccessDenied("Platform administrator required")


def ensure_clinic_admin(db: Session, actor_id: int, org_id: int) -> None:
    actor = db.get(User, actor_id)
    org = db.get(Organization, org_id)
    if actor is None or not actor.active or org is None or not org.active:
        raise AccessDenied("Clinic administrator required")
    grant = db.scalar(select(Membership.id).where(
        Membership.user_id == actor_id,
        Membership.organization_id == org_id,
        Membership.role == "CLINIC_ADMIN", Membership.active.is_(True),
    ))
    if grant is None:
        raise AccessDenied("Clinic administrator required")


def ensure_patient_owner(db: Session, actor_id: int, link: PatientClinicLink) -> None:
    actor = db.get(User, actor_id)
    patient = db.get(Patient, link.patient_id)
    if actor is None or not actor.active or patient is None or patient.user_id != actor_id:
        raise AccessDenied("Patient ownership required")
    if not link.active or not db.get(Organization, link.organization_id).active:
        raise AccessDenied("Inactive patient-clinic relationship")


def get_link(db: Session, org_id: int, ref: str) -> PatientClinicLink:
    link = db.scalar(select(PatientClinicLink).where(
        PatientClinicLink.organization_id == org_id,
        PatientClinicLink.local_ref == ref,
        PatientClinicLink.active.is_(True),
    ))
    if link is None:
        raise NotFound("Patient reference not found in this clinic")
    return link


def set_flag(db: Session, actor_id: int, org_id: int | None, enabled: bool) -> None:
    ensure_platform_admin(db, actor_id)
    if type(enabled) is not bool:
        raise InvalidInput("enabled must be boolean")
    kind = "GLOBAL" if org_id is None else "ORGANIZATION"
    scope_id = 0 if org_id is None else org_id
    if org_id is not None and db.get(Organization, org_id) is None:
        raise NotFound("Organization not found")
    flag = db.scalar(select(FeatureFlag).where(
        FeatureFlag.scope_kind == kind, FeatureFlag.scope_id == scope_id,
        FeatureFlag.feature_key == FEATURE,
    ))
    if flag is None:
        db.add(FeatureFlag(scope_kind=kind, scope_id=scope_id, feature_key=FEATURE, enabled=enabled))
    else:
        flag.enabled = enabled
    audit(db, actor_id, "ADMIN_PII_FLAG_CHANGED", kind, scope_id)


def feature_enabled(db: Session, org_id: int) -> bool:
    """Fail closed: absent flags, deactivated organization or stale scopes deny."""
    org = db.get(Organization, org_id)
    if org is None or not org.active:
        return False
    flags = db.scalars(select(FeatureFlag).where(
        FeatureFlag.feature_key == FEATURE,
        ((FeatureFlag.scope_kind == "GLOBAL") & (FeatureFlag.scope_id == 0)) |
        ((FeatureFlag.scope_kind == "ORGANIZATION") & (FeatureFlag.scope_id == org_id)),
    )).all()
    state = {(f.scope_kind, f.scope_id): f.enabled for f in flags}
    return state.get(("GLOBAL", 0), False) and state.get(("ORGANIZATION", org_id), False)


def valid_pii_definition(db: Session, field_key: str) -> FieldDefinition:
    if not isinstance(field_key, str) or not field_key or len(field_key) > 96:
        raise InvalidInput("Invalid field_key")
    d = db.get(FieldDefinition, field_key)
    if d is None or not d.admin_pii_eligible or d.category not in ELIGIBLE_CATEGORIES:
        raise InvalidInput("Field is not explicitly eligible for clinic admin identification")
    return d


def register_field(db: Session, actor_id: int, field_key: str, category: str,
                   admin_pii_eligible: bool) -> None:
    ensure_platform_admin(db, actor_id)
    if (not isinstance(field_key, str) or not field_key.isidentifier()
            or len(field_key) > 96):
        raise InvalidInput("field_key must be a short identifier")
    if not isinstance(category, str) or category not in {"IDENTITY", "CONTACT", "CLINICAL", "OTHER"}:
        raise InvalidInput("Unknown category")
    if type(admin_pii_eligible) is not bool:
        raise InvalidInput("admin_pii_eligible must be boolean")
    if admin_pii_eligible and category not in ELIGIBLE_CATEGORIES:
        raise InvalidInput("Clinical or generic fields cannot be exposed")
    if db.get(FieldDefinition, field_key) is not None:
        raise InvalidInput("Field already registered; metadata is immutable in this API")
    db.add(FieldDefinition(field_key=field_key, category=category,
                           admin_pii_eligible=admin_pii_eligible))
    audit(db, actor_id, "FIELD_REGISTERED", "field", field_key)


def create_template(db: Session, actor_id: int, org_id: int, template_key: str,
                    version: int, read_fields: list[str]) -> AdminPiiTemplate:
    ensure_platform_admin(db, actor_id)
    if db.get(Organization, org_id) is None:
        raise NotFound("Organization not found")
    if not isinstance(template_key, str) or not template_key.isidentifier() or len(template_key) > 80:
        raise InvalidInput("Invalid template_key")
    if type(version) is not int or version < 1:
        raise InvalidInput("version must be positive integer")
    if (not isinstance(read_fields, list) or not all(isinstance(x, str) for x in read_fields)
            or len(set(read_fields)) != len(read_fields)):
        raise InvalidInput("read_fields must be a unique list")
    for field_key in read_fields:
        valid_pii_definition(db, field_key)
    if db.scalar(select(AdminPiiTemplate.id).where(
        AdminPiiTemplate.organization_id == org_id,
        AdminPiiTemplate.template_key == template_key,
        AdminPiiTemplate.version == version,
    )) is not None:
        raise InvalidInput("Template version exists; publish a new version")
    template = AdminPiiTemplate(organization_id=org_id,
                                template_key=template_key, version=version)
    template.rules = [AdminPiiTemplateRule(field_key=key, allow_read=True) for key in read_fields]
    db.add(template)
    db.flush()
    audit(db, actor_id, "ADMIN_PII_TEMPLATE_CREATED", "template", template.id)
    return template


def accept_template(db: Session, actor_id: int, link_id: int, template_id: int,
                    confirmed: bool) -> None:
    link = db.get(PatientClinicLink, link_id)
    if link is None:
        raise NotFound("Patient-clinic relationship not found")
    ensure_patient_owner(db, actor_id, link)
    if confirmed is not True:
        raise InvalidInput("Explicit confirmation of the exact template version required")
    template = db.get(AdminPiiTemplate, template_id)
    if template is None or not template.active or template.organization_id != link.organization_id:
        raise InvalidInput("Template is inactive or belongs to another clinic")
    # We do not silently transfer old overrides across changed policy versions.
    policy = db.scalar(select(AdminPiiPolicy).where(AdminPiiPolicy.patient_clinic_link_id == link_id))
    if policy is None:
        db.add(AdminPiiPolicy(patient_clinic_link_id=link_id, template_id=template.id))
    else:
        policy.template_id = template.id
        policy.active = True
        policy.accepted_at = now_utc()
        for item in db.scalars(select(AdminPiiOverride).where(
            AdminPiiOverride.patient_clinic_link_id == link_id,
        )).all():
            db.delete(item)
    audit(db, actor_id, "ADMIN_PII_POLICY_ACCEPTED", "patient_clinic_link", link.local_ref)


def update_override(db: Session, actor_id: int, link_id: int, field_key: str,
                    effect: str, expires_at: datetime | None = None) -> None:
    link = db.get(PatientClinicLink, link_id)
    if link is None:
        raise NotFound("Patient-clinic relationship not found")
    ensure_patient_owner(db, actor_id, link)
    policy = db.scalar(select(AdminPiiPolicy).where(
        AdminPiiPolicy.patient_clinic_link_id == link_id, AdminPiiPolicy.active.is_(True),
    ))
    if policy is None:
        raise InvalidInput("Patient must first accept a template")
    valid_pii_definition(db, field_key)
    if not isinstance(effect, str) or effect not in {"ALLOW", "DENY", "REMOVE"}:
        raise InvalidInput("Invalid effect")
    if expires_at is not None and (expires_at.replace(tzinfo=timezone.utc)
                                       if expires_at.tzinfo is None else
                                       expires_at.astimezone(timezone.utc)) <= now_utc():
        raise InvalidInput("expires_at must be in the future")
    existing = db.scalar(select(AdminPiiOverride).where(
        AdminPiiOverride.patient_clinic_link_id == link_id,
        AdminPiiOverride.field_key == field_key,
    ))
    if effect == "REMOVE":
        if existing is not None:
            db.delete(existing)
    elif existing is not None:
        existing.effect = effect
        existing.expires_at = expires_at
    else:
        db.add(AdminPiiOverride(patient_clinic_link_id=link_id, field_key=field_key,
                                effect=effect, expires_at=expires_at))
    audit(db, actor_id, "ADMIN_PII_OVERRIDE_CHANGED", "patient_clinic_link", link.local_ref)


def revoke_policy(db: Session, actor_id: int, link_id: int) -> None:
    link = db.get(PatientClinicLink, link_id)
    if link is None:
        raise NotFound("Patient-clinic relationship not found")
    ensure_patient_owner(db, actor_id, link)
    p = db.scalar(select(AdminPiiPolicy).where(AdminPiiPolicy.patient_clinic_link_id == link_id))
    if p:
        p.active = False
    audit(db, actor_id, "ADMIN_PII_POLICY_REVOKED", "patient_clinic_link", link.local_ref)


def effective_keys(db: Session, org_id: int, link: PatientClinicLink) -> set[str]:
    """Must be called behind admin membership check; never read plaintext here."""
    if not link.active or link.organization_id != org_id or not feature_enabled(db, org_id):
        return set()
    policy = db.scalar(select(AdminPiiPolicy).where(
        AdminPiiPolicy.patient_clinic_link_id == link.id, AdminPiiPolicy.active.is_(True),
    ))
    if policy is None:
        return set()
    template = db.get(AdminPiiTemplate, policy.template_id)
    if template is None or template.organization_id != org_id:
        return set()
    # Template active flag does not retroactively revoke accepted versions;
    # patient revocation, inactive relationship and feature flags do revoke.
    rules = db.scalars(select(AdminPiiTemplateRule).where(
        AdminPiiTemplateRule.template_id == policy.template_id,
        AdminPiiTemplateRule.allow_read.is_(True),
    )).all()
    allowed = {rule.field_key for rule in rules}
    for override in db.scalars(select(AdminPiiOverride).where(
        AdminPiiOverride.patient_clinic_link_id == link.id,
    )).all():
        expires = override.expires_at
        if expires is not None:
            # SQLite returns naive datetimes even for timezone-aware columns.
            if (expires.replace(tzinfo=timezone.utc) if expires.tzinfo is None else
                    expires.astimezone(timezone.utc)) <= now_utc():
                continue
        if override.effect == "DENY":
            allowed.discard(override.field_key)
        elif override.effect == "ALLOW":
            allowed.add(override.field_key)
    if not allowed:
        return set()
    definitions = db.scalars(select(FieldDefinition).where(
        FieldDefinition.field_key.in_(allowed),
        FieldDefinition.admin_pii_eligible.is_(True),
        FieldDefinition.category.in_(ELIGIBLE_CATEGORIES),
    )).all()
    return {d.field_key for d in definitions}


def patient_view(db: Session, actor_id: int, org_id: int,
                 link: PatientClinicLink, cipher: PiiCipher,
                 requested_fields: Iterable[str] | None = None) -> dict:
    ensure_clinic_admin(db, actor_id, org_id)
    if not link.active or link.organization_id != org_id:
        raise NotFound("Patient not in clinic")
    granted = effective_keys(db, org_id, link)
    if requested_fields is not None:
        granted &= set(requested_fields)
    result = {"patient_ref": link.local_ref, "fields": {}}
    if not granted:
        return result
    values = db.scalars(select(PatientFieldValue).where(
        PatientFieldValue.patient_id == link.patient_id,
        PatientFieldValue.field_key.in_(granted),
    )).all()
    result["fields"] = {item.field_key: cipher.decrypt(item.encrypted_value) for item in values}
    return result


def patient_list(db: Session, actor_id: int, org_id: int, cipher: PiiCipher,
                 *, filter_field: str | None = None, filter_value: str | None = None,
                 sort_field: str | None = None, offset: int = 0, limit: int = 50,
                 requested_fields: list[str] | None = None) -> dict:
    ensure_clinic_admin(db, actor_id, org_id)
    if not (0 <= offset <= 100_000 and 1 <= limit <= 500):
        raise InvalidInput("Invalid pagination")
    if filter_field is not None:
        valid_pii_definition(db, filter_field)
        if not isinstance(filter_value, str) or len(filter_value) > 200 or not filter_value:
            raise InvalidInput("Nonempty filter_value required")
    elif filter_value is not None:
        raise InvalidInput("filter_field required")
    if sort_field is not None:
        valid_pii_definition(db, sort_field)
    if requested_fields is not None:
        for key in requested_fields:
            valid_pii_definition(db, key)
    # Each row is projected BEFORE filtering/sorting/pagination, so no
    # forbidden value can influence inclusion or ordering.
    links = db.scalars(select(PatientClinicLink).where(
        PatientClinicLink.organization_id == org_id,
        PatientClinicLink.active.is_(True),
    ).order_by(PatientClinicLink.local_ref)).all()
    projection_fields = set(requested_fields) if requested_fields is not None else None
    required_fields = {x for x in (filter_field, sort_field) if x is not None}
    views = []
    for link in links:
        view = patient_view(db, actor_id, org_id, link, cipher,
                            None if projection_fields is None else projection_fields | required_fields)
        if filter_field is not None and filter_value.casefold() not in view["fields"].get(filter_field, "").casefold():
            continue
        views.append(view)
    if sort_field is not None:
        # Unauthorized/missing keys are treated as missing, never consulted.
        views.sort(key=lambda v: (sort_field not in v["fields"],
                                  v["fields"].get(sort_field, "").casefold(), v["patient_ref"]))
    total = len(views)
    page = views[offset:offset + limit]
    if requested_fields is not None:
        for view in page:
            view["fields"] = {k: v for k, v in view["fields"].items() if k in projection_fields}
    else:
        # sort_field/filter_field were already safely projected using all granted fields.
        pass
    return {"items": page, "total": total, "limit": limit, "offset": offset}


def notification_list(db: Session, actor_id: int, org_id: int,
                      cipher: PiiCipher, *, offset: int = 0, limit: int = 50) -> dict:
    ensure_clinic_admin(db, actor_id, org_id)
    rows = db.execute(select(Notification, PatientClinicLink).join(
        PatientClinicLink, Notification.patient_clinic_link_id == PatientClinicLink.id,
    ).where(PatientClinicLink.organization_id == org_id,
            PatientClinicLink.active.is_(True),
            Notification.kind.in_(ADMIN_NOTIFICATION_KINDS))).all()
    if offset < 0 or limit < 1 or limit > 500:
        raise InvalidInput("Invalid pagination")
    page = rows[offset:offset + limit]
    return {"items": [{"id": n.id, "kind": n.kind, "patient": patient_view(db, actor_id, org_id, link, cipher)}
                      for n, link in page], "total": len(rows), "offset": offset, "limit": limit}


def appointment_list(db: Session, actor_id: int, org_id: int,
                     cipher: PiiCipher, *, offset: int = 0, limit: int = 50) -> dict:
    ensure_clinic_admin(db, actor_id, org_id)
    rows = db.execute(select(Appointment, PatientClinicLink).join(
        PatientClinicLink, Appointment.patient_clinic_link_id == PatientClinicLink.id,
    ).where(PatientClinicLink.organization_id == org_id,
            PatientClinicLink.active.is_(True))).all()
    if offset < 0 or limit < 1 or limit > 500:
        raise InvalidInput("Invalid pagination")
    page = rows[offset:offset + limit]
    return {"items": [{"id": app.id, "doctor_user_id": app.doctor_user_id,
                       "start_at": app.start_at.isoformat(), "status": app.status,
                       "patient": patient_view(db, actor_id, org_id, link, cipher)}
                      for app, link in page], "total": len(rows), "offset": offset, "limit": limit}


def request_appointment(db: Session, actor_id: int, org_id: int, patient_ref: str,
                        doctor_user_id: int, start_at: datetime) -> Appointment:
    ensure_clinic_admin(db, actor_id, org_id)
    link = get_link(db, org_id, patient_ref)
    doctor = db.get(User, doctor_user_id)
    member = db.scalar(select(Membership.id).where(
        Membership.user_id == doctor_user_id, Membership.organization_id == org_id,
        Membership.role == "DOCTOR", Membership.active.is_(True),
    ))
    # Admin cannot schedule an unrelated patient to an unrelated doctor.
    relation = db.scalar(select(DoctorPatientLink.id).where(
        DoctorPatientLink.patient_id == link.patient_id,
        DoctorPatientLink.doctor_user_id == doctor_user_id,
        DoctorPatientLink.organization_id == org_id,
        DoctorPatientLink.active.is_(True),
    ))
    if doctor is None or not doctor.active or member is None or relation is None:
        raise AccessDenied("No active clinician-patient relationship in this clinic")
    if start_at.tzinfo is None or start_at <= now_utc():
        raise InvalidInput("start_at must be future timezone-aware ISO 8601")
    app = Appointment(patient_clinic_link_id=link.id, doctor_user_id=doctor_user_id,
                      start_at=start_at)
    db.add(app)
    db.flush()
    db.add(Notification(patient_clinic_link_id=link.id,
                        kind="APPOINTMENT_REQUESTED", appointment_id=app.id))
    audit(db, actor_id, "APPOINTMENT_REQUESTED", "appointment", app.id)
    return app


def write_patient_field(db: Session, patient_actor: int, field_key: str,
                        value: str, cipher: PiiCipher) -> None:
    actor = db.get(User, patient_actor)
    patient = db.scalar(select(Patient).where(Patient.user_id == patient_actor))
    if actor is None or not actor.active or patient is None:
        raise AccessDenied("Patient required")
    definition = db.get(FieldDefinition, field_key)
    if definition is None or definition.category not in ELIGIBLE_CATEGORIES:
        raise InvalidInput("This endpoint accepts identity/contact fields only")
    if not isinstance(value, str) or len(value) > 500:
        raise InvalidInput("Expected short string")
    entry = db.scalar(select(PatientFieldValue).where(
        PatientFieldValue.patient_id == patient.id, PatientFieldValue.field_key == field_key,
    ))
    encrypted = cipher.encrypt(value)
    if entry is None:
        db.add(PatientFieldValue(patient_id=patient.id, field_key=field_key,
                                 encrypted_value=encrypted))
    else:
        entry.encrypted_value = encrypted
    audit(db, patient_actor, "PATIENT_IDENTITY_FIELD_UPDATED", "field", field_key)


def seed_base_fields(db: Session):
    """Initializer only; never overwrites existing field metadata."""
    categories = {"first_name": "IDENTITY", "last_name": "IDENTITY",
                  "middle_name": "IDENTITY", "phone": "CONTACT", "email": "CONTACT"}
    for field, category in categories.items():
        if db.get(FieldDefinition, field) is None:
            db.add(FieldDefinition(field_key=field, category=category,
                                   admin_pii_eligible=True))
