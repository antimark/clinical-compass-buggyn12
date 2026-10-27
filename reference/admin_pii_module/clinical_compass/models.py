"""Core sample entities plus removable clinic-admin identity access models.

In an existing backend, import the project's User, Organization, Patient,
PatientClinicLink, FieldDefinition and PatientFieldValue instead of duplicating them.
Only AdminPii* and FeatureFlag belong to the optional feature.
"""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String,
    Text, UniqueConstraint, JSON, event, Engine
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Membership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", "role"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)


class PatientClinicLink(Base):
    __tablename__ = "patient_clinic_links"
    __table_args__ = (
        UniqueConstraint("patient_id", "organization_id"),
        UniqueConstraint("organization_id", "local_ref"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    local_ref: Mapped[str] = mapped_column(String(36), nullable=False, default=lambda: str(uuid4()))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DoctorPatientLink(Base):
    __tablename__ = "patient_doctor_links"
    __table_args__ = (UniqueConstraint("patient_id", "doctor_user_id", "organization_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False)
    doctor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FieldDefinition(Base):
    __tablename__ = "field_registry"
    field_key: Mapped[str] = mapped_column(String(96), primary_key=True)
    category: Mapped[str] = mapped_column(String(24), nullable=False)  # IDENTITY, CONTACT, CLINICAL, OTHER
    admin_pii_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (CheckConstraint("category IN ('IDENTITY', 'CONTACT', 'CLINICAL', 'OTHER')"),)


class PatientFieldValue(Base):
    __tablename__ = "patient_field_values"
    __table_args__ = (UniqueConstraint("patient_id", "field_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False)
    field_key: Mapped[str] = mapped_column(ForeignKey("field_registry.field_key"), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)


class ClinicalRecord(Base):
    __tablename__ = "clinical_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False)
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)


class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    __table_args__ = (
        UniqueConstraint("scope_kind", "scope_id", "feature_key"),
        CheckConstraint("scope_kind IN ('GLOBAL', 'ORGANIZATION')"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[int] = mapped_column(Integer, nullable=False)  # GLOBAL = 0
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AdminPiiTemplate(Base):
    __tablename__ = "admin_pii_templates"
    __table_args__ = (UniqueConstraint("organization_id", "template_key", "version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    template_key: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    rules: Mapped[list["AdminPiiTemplateRule"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class AdminPiiTemplateRule(Base):
    __tablename__ = "admin_pii_template_rules"
    __table_args__ = (UniqueConstraint("template_id", "field_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("admin_pii_templates.id", ondelete="CASCADE"), nullable=False)
    field_key: Mapped[str] = mapped_column(ForeignKey("field_registry.field_key"), nullable=False)
    allow_read: Mapped[bool] = mapped_column(Boolean, nullable=False)


class AdminPiiPolicy(Base):
    __tablename__ = "admin_pii_policies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_clinic_link_id: Mapped[int] = mapped_column(ForeignKey("patient_clinic_links.id"), unique=True, nullable=False)
    template_id: Mapped[int] = mapped_column(ForeignKey("admin_pii_templates.id"), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AdminPiiOverride(Base):
    __tablename__ = "admin_pii_overrides"
    __table_args__ = (
        UniqueConstraint("patient_clinic_link_id", "field_key"),
        CheckConstraint("effect IN ('ALLOW', 'DENY')"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_clinic_link_id: Mapped[int] = mapped_column(ForeignKey("patient_clinic_links.id"), nullable=False)
    field_key: Mapped[str] = mapped_column(ForeignKey("field_registry.field_key"), nullable=False)
    effect: Mapped[str] = mapped_column(String(5), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (CheckConstraint("status IN ('REQUESTED', 'CONFIRMED', 'CANCELLED')"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_clinic_link_id: Mapped[int] = mapped_column(ForeignKey("patient_clinic_links.id"), nullable=False)
    doctor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="REQUESTED")


class Notification(Base):
    __tablename__ = "administrative_notifications"
    __table_args__ = (CheckConstraint("kind IN ('APPOINTMENT_REQUESTED', 'APPOINTMENT_CANCELLED', 'APPOINTMENT_RESCHEDULED')"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_clinic_link_id: Mapped[int] = mapped_column(ForeignKey("patient_clinic_links.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    # no PII or clinical payload in audit


def configure_sqlite(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


# Enforce version immutability in application sessions. For the SQLite deployment,
# equivalent DB-level triggers are installed by the Alembic revision.
@event.listens_for(AdminPiiTemplateRule, "before_update")
@event.listens_for(AdminPiiTemplateRule, "before_delete")
def _freeze_rule(*_args):
    raise ValueError("Published admin PII template rules are immutable; create a new version")


@event.listens_for(AdminPiiTemplate, "before_update")
def _freeze_template_identity(_mapper, _connection, target):
    from sqlalchemy import inspect as sa_inspect
    state = sa_inspect(target)
    for name in ("organization_id", "template_key", "version"):
        if state.attrs[name].history.has_changes():
            raise ValueError("Template identity/version cannot be changed")
