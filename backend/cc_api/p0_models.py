"""Additive synthetic-only P0 entities; no real identity, clinical or AI validation."""
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base

class CarePlan(Base):
    __tablename__ = 'p0_care_plans'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), index=True)
    clinician_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(24), default='draft')
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40))

class PlanItem(Base):
    __tablename__ = 'p0_plan_items'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey('p0_care_plans.id'), index=True)
    item_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    scheduled_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    frequency: Mapped[str] = mapped_column(String(120), default='once')
    completion_criteria: Mapped[str] = mapped_column(String(300), default='')
    created_at: Mapped[str] = mapped_column(String(40))

class PlanEvent(Base):
    __tablename__ = 'p0_plan_events'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey('p0_plan_items.id'), index=True)
    patient_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    outcome: Mapped[str] = mapped_column(String(32))
    reported_at: Mapped[str] = mapped_column(String(40))

class AdverseEvent(Base):
    __tablename__ = 'p0_adverse_events'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), index=True)
    reporter_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default='reported')
    review_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    reviewed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

class Encounter(Base):
    __tablename__ = 'p0_encounters'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), index=True)
    clinician_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    mode: Mapped[str] = mapped_column(String(20))
    content_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='draft')
    created_at: Mapped[str] = mapped_column(String(40))
    signed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

class ClinicalDecision(Base):
    __tablename__ = 'p0_decisions'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), index=True)
    clinician_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    text: Mapped[str] = mapped_column(Text)
    confirmed_at: Mapped[str] = mapped_column(String(40))

class AlertReview(Base):
    __tablename__ = 'p0_alert_reviews'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey('alerts.id'), index=True)
    clinician_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    assessment: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[str] = mapped_column(String(40))

class DatasetDefinition(Base):
    __tablename__ = 'p0_dataset_definitions'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    researcher_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    study_id: Mapped[str] = mapped_column(String(50))
    definition_json: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40))

class UserNotification(Base):
    __tablename__ = 'p0_notifications'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    recipient_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    text: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[str] = mapped_column(String(40))
    read_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

class SummaryRevision(Base):
    __tablename__ = 'p0_summary_revisions'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey('cc_ai_summary_drafts.id'), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))

class ReferenceArticle(Base):
    __tablename__ = 'p0_reference_articles'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    publisher: Mapped[str] = mapped_column(String(100))
    original_url: Mapped[str] = mapped_column(String(600))
    version: Mapped[str] = mapped_column(String(50))
    reviewed_at: Mapped[str] = mapped_column(String(40))
    licensing: Mapped[str] = mapped_column(String(120))
    limitations: Mapped[str] = mapped_column(Text)
    approval_status: Mapped[str] = mapped_column(String(20))

P0_MODELS = (CarePlan, PlanItem, PlanEvent, AdverseEvent, Encounter, ClinicalDecision,
             AlertReview, DatasetDefinition, UserNotification, SummaryRevision, ReferenceArticle)
