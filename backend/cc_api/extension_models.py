"""Synthetic demo domain extension. This is not a clinical-production migration."""
from sqlalchemy import String, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base

class Invitation(Base):
    __tablename__='cc_invitations'
    id: Mapped[str]=mapped_column(String(60),primary_key=True)
    code_hash: Mapped[str]=mapped_column(String(64),unique=True)
    issuer_id: Mapped[str]=mapped_column(String(64))
    target_role: Mapped[str]=mapped_column(String(40))
    recipient_id: Mapped[str|None]=mapped_column(String(64),nullable=True)
    patient_id: Mapped[str|None]=mapped_column(String(64),nullable=True)
    categories: Mapped[str]=mapped_column(String(400),default='symptoms')
    expires_at: Mapped[str]=mapped_column(String(40))
    status: Mapped[str]=mapped_column(String(20),default='pending')
    organization_id: Mapped[str]=mapped_column(String(64),default='org_demo')
    revoked_at: Mapped[str|None]=mapped_column(String(40),nullable=True)
    accepted_at: Mapped[str|None]=mapped_column(String(40),nullable=True)

class PrevisitCase(Base):
    __tablename__='cc_previsit_cases'
    id: Mapped[str]=mapped_column(String(60),primary_key=True)
    patient_user_id: Mapped[str]=mapped_column(String(64))
    doctor_id: Mapped[str]=mapped_column(String(64))
    status: Mapped[str]=mapped_column(String(32),default='submitted')
    intake_json: Mapped[str]=mapped_column(Text)
    created_at: Mapped[str]=mapped_column(String(40))
    allowed_until: Mapped[str]=mapped_column(String(40))
    consent_version: Mapped[str]=mapped_column(String(32),default='case-1')
    first_patient_message: Mapped[int]=mapped_column(Integer,default=0)
    doctor_replied: Mapped[int]=mapped_column(Integer,default=0)

class Message(Base):
    __tablename__='cc_messages'
    id: Mapped[str]=mapped_column(String(60),primary_key=True)
    thread_type: Mapped[str]=mapped_column(String(20))
    context_id: Mapped[str]=mapped_column(String(60))
    sender_id: Mapped[str]=mapped_column(String(60))
    recipient_id: Mapped[str]=mapped_column(String(60))
    text: Mapped[str]=mapped_column(Text)
    created_at: Mapped[str]=mapped_column(String(40))

class Appointment(Base):
    __tablename__='cc_appointments'
    id: Mapped[str]=mapped_column(String(60),primary_key=True)
    case_id: Mapped[str]=mapped_column(String(60))
    doctor_id: Mapped[str]=mapped_column(String(60))
    patient_user_id: Mapped[str]=mapped_column(String(60))
    proposed_at: Mapped[str]=mapped_column(String(40))
    format: Mapped[str]=mapped_column(String(20))
    status: Mapped[str]=mapped_column(String(20),default='offered')

class CareTeamVisibility(Base):
    __tablename__='cc_care_team_visibility'
    id: Mapped[str]=mapped_column(String(60),primary_key=True)
    patient_id: Mapped[str]=mapped_column(String(60))
    doctor_a: Mapped[str]=mapped_column(String(60))
    doctor_b: Mapped[str]=mapped_column(String(60))
    active: Mapped[int]=mapped_column(Integer,default=1)

class Audit(Base):
    __tablename__='cc_audit'
    id: Mapped[str]=mapped_column(String(60),primary_key=True)
    actor: Mapped[str]=mapped_column(String(60))
    action: Mapped[str]=mapped_column(String(90))
    object_type: Mapped[str]=mapped_column(String(40))
    object_id: Mapped[str]=mapped_column(String(60))
    created_at: Mapped[str]=mapped_column(String(40))

class ClinicalCondition(Base):
    """Multiple clinician-confirmed diagnoses; never equate patient report with confirmation."""
    __tablename__ = 'cc_clinical_conditions'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64))
    clinician_id: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(30), default='active')
    confirmed_at: Mapped[str] = mapped_column(String(40))

class MedicationRecord(Base):
    __tablename__ = 'cc_medications'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64))
    clinician_id: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(160))
    source: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30))

class QuestionnaireAssignment(Base):
    __tablename__ = 'cc_questionnaire_assignments'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64))
    clinician_id: Mapped[str] = mapped_column(String(64))
    instrument_id: Mapped[str] = mapped_column(String(40))
    instrument_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default='assigned')
    response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

class ResearchObservation(Base):
    __tablename__ = 'cc_research_observations'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    study_id: Mapped[str] = mapped_column(String(50))
    study_subject: Mapped[str] = mapped_column(String(64))
    cohort: Mapped[str] = mapped_column(String(30))
    measure: Mapped[str] = mapped_column(String(50))
    value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(60), default='synthetic_fixture')
    recorded_at: Mapped[str] = mapped_column(String(40))

class IdentityVault(Base):
    """Nonmedical demo identity partition. Never expose through clinical/research APIs."""
    __tablename__ = 'cc_identity_vault'
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    verified_subject: Mapped[str] = mapped_column(String(200), unique=True)
    synthetic_contact: Mapped[str] = mapped_column(String(200))
    organization_id: Mapped[str] = mapped_column(String(64))

class ClinicalDataShare(Base):
    """Independent scoped grant; not inferred from pair visibility."""
    __tablename__ = 'cc_clinical_data_shares'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64))
    sender_doctor: Mapped[str] = mapped_column(String(64))
    recipient_doctor: Mapped[str] = mapped_column(String(64))
    scope: Mapped[str] = mapped_column(String(300))
    active: Mapped[int] = mapped_column(Integer, default=0)

class AISummaryDraft(Base):
    __tablename__ = 'cc_ai_summary_drafts'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    patient_user_id: Mapped[str] = mapped_column(String(64))
    recipient_doctor_id: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(30), default='needs_review')
    created_at: Mapped[str] = mapped_column(String(40))
