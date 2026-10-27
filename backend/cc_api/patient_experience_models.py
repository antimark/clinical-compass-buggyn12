"""Additive synthetic patient observations and versioned technical questionnaires."""
from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base


class MetricObservation(Base):
    __tablename__ = 'px_observations'
    __table_args__ = (UniqueConstraint('patient_id', 'event_key', name='uq_px_observation_event'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64), ForeignKey('patients.id'), index=True)
    metric_key: Mapped[str] = mapped_column(String(64))
    unit: Mapped[str] = mapped_column(String(32))
    scale_version: Mapped[str] = mapped_column(String(64))
    value: Mapped[float] = mapped_column(Float)
    observed_at: Mapped[str] = mapped_column(String(40))
    recorded_at: Mapped[str] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(40))
    event_key: Mapped[str] = mapped_column(String(80))


class DemoQuestionnaireDefinition(Base):
    __tablename__ = 'px_questionnaire_definitions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    definition_json: Mapped[str] = mapped_column(Text)


class DemoQuestionnaireAssignment(Base):
    __tablename__ = 'px_questionnaire_assignments'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64), ForeignKey('patients.id'), index=True)
    clinician_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    definition_id: Mapped[str] = mapped_column(String(64), ForeignKey('px_questionnaire_definitions.id'))
    definition_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default='assigned')
    created_at: Mapped[str] = mapped_column(String(40))


class DemoQuestionnaireDraft(Base):
    __tablename__ = 'px_questionnaire_drafts'
    assignment_id: Mapped[str] = mapped_column(String(64), ForeignKey('px_questionnaire_assignments.id'), primary_key=True)
    answers_json: Mapped[str] = mapped_column(Text, default='{}')
    last_page: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[str] = mapped_column(String(40))


class DemoQuestionnaireSubmission(Base):
    __tablename__ = 'px_questionnaire_submissions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    assignment_id: Mapped[str] = mapped_column(String(64), ForeignKey('px_questionnaire_assignments.id'), unique=True)
    definition_id: Mapped[str] = mapped_column(String(64), ForeignKey('px_questionnaire_definitions.id'))
    definition_version: Mapped[str] = mapped_column(String(32))
    definition_snapshot_json: Mapped[str] = mapped_column(Text)
    answers_json: Mapped[str] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer)
    submitted_at: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(80))


class SyntheticPersona(Base):
    __tablename__ = 'px_personas'
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'), primary_key=True)
    persona_key: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(String(300))
    state: Mapped[str] = mapped_column(String(32))
