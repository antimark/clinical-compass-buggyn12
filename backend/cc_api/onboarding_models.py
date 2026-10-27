"""Additive synthetic-dev identity and explicit patient-consent stores."""
from sqlalchemy import String, Text, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base

class LocalIdentity(Base):
    __tablename__='ob_identities'
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    email_provider: Mapped[str] = mapped_column(String(80))
    email_status: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[str] = mapped_column(String(40))

class OnboardingJourney(Base):
    __tablename__='ob_journeys'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), ForeignKey('users.id'), nullable=True)
    doctor_id: Mapped[str | None] = mapped_column(String(64), ForeignKey('users.id'), nullable=True)
    subject: Mapped[str] = mapped_column(String(160), default='')
    message: Mapped[str] = mapped_column(Text, default='')
    step: Mapped[str] = mapped_column(String(32), default='draft')
    revision: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[str] = mapped_column(String(40))

class PatientOnboarding(Base):
    __tablename__='ob_patient_onboarding'
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default='pending')
    introduction_seen: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[str] = mapped_column(String(40))

class PatientInvitation(Base):
    __tablename__='ob_invitations'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    issuer_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    recipient_hash: Mapped[str] = mapped_column(String(64))
    organization_id: Mapped[str] = mapped_column(String(64))
    categories: Mapped[str] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(24), default='pending')
    created_at: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[str] = mapped_column(String(40))
    accepted_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    revoked_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    patient_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey('users.id'), nullable=True)

class PatientConsent(Base):
    __tablename__='ob_consents'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_user_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    invitation_id: Mapped[str] = mapped_column(String(64), ForeignKey('ob_invitations.id'), unique=True)
    categories: Mapped[str] = mapped_column(String(400))
    version: Mapped[str] = mapped_column(String(32), default='clinical-link-v1')
    accepted_at: Mapped[str] = mapped_column(String(40))
    revoked_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

class PreparedOnboardingDraft(Base):
    __tablename__='ob_prepared_drafts'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    invitation_id: Mapped[str] = mapped_column(String(64), ForeignKey('ob_invitations.id'))
    clinician_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    content: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(24), default='draft')
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40))
    signed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    published_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

class StaffVerification(Base):
    __tablename__='ob_staff_verifications'
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'), primary_key=True)
    provider: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40))
    verified_at: Mapped[str] = mapped_column(String(40))


class LocalAuthSession(Base):
    __tablename__='ob_auth_sessions'
    token_hash: Mapped[str] = mapped_column(String(64),primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    expires_at: Mapped[str] = mapped_column(String(40))
    revoked_at: Mapped[str | None] = mapped_column(String(40),nullable=True)
