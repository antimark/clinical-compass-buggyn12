"""Optional administrative identity disclosure; core identity is never duplicated.

Templates are append-only versions. The coordinator migration also installs DB
immutability triggers. These tables contain no clinical payload.
"""
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base


class AdminPrivacyFlag(Base):
    __tablename__ = 'ap_flags'
    scope: Mapped[str] = mapped_column(String(80), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class AdminPrivacyTemplate(Base):
    __tablename__ = 'ap_templates'
    __table_args__ = (UniqueConstraint('organization_id', 'template_key', 'version', name='uq_ap_template_version'),
                      CheckConstraint('version > 0', name='ck_ap_template_version'))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(64))
    template_key: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)
    read_fields_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))


class AdminPrivacyPolicy(Base):
    __tablename__ = 'ap_policies'
    patient_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    template_id: Mapped[str] = mapped_column(ForeignKey('ap_templates.id'))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    accepted_at: Mapped[str] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(Integer, default=1)


class AdminPrivacyOverride(Base):
    __tablename__ = 'ap_overrides'
    __table_args__ = (CheckConstraint("effect IN ('ALLOW','DENY')", name='ck_ap_override_effect'),)
    patient_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    field_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    effect: Mapped[str] = mapped_column(String(5))
    expires_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class AdminPrivacyValue(Base):
    __tablename__ = 'ap_values'
    patient_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    field_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(String(40))


@event.listens_for(AdminPrivacyTemplate, 'before_update')
@event.listens_for(AdminPrivacyTemplate, 'before_delete')
def immutable_template(*_args):
    raise ValueError('Administrative disclosure templates are immutable; publish a new version')
