"""Explicit field review and immutable clinical review provenance."""
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base


class SummaryField(Base):
    __tablename__ = 'cr_summary_fields'
    __table_args__ = (UniqueConstraint('draft_id', 'field_key'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey('cc_ai_summary_drafts.id'))
    field_key: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(160))
    scope: Mapped[str] = mapped_column(String(24))
    source_version: Mapped[int] = mapped_column(Integer)
    value_json: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    reviewed_value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class SummaryFieldRevision(Base):
    __tablename__ = 'cr_summary_field_revisions'
    __table_args__ = (UniqueConstraint('field_id', 'revision'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    field_id: Mapped[str] = mapped_column(ForeignKey('cr_summary_fields.id'))
    revision: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(24))
    snapshot_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))


class EncounterAddendum(Base):
    __tablename__ = 'cr_encounter_addenda'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    encounter_id: Mapped[str] = mapped_column(ForeignKey('p0_encounters.id'))
    author_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    text: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))


class DecisionClassification(Base):
    __tablename__ = 'cr_decision_classifications'
    decision_id: Mapped[str] = mapped_column(ForeignKey('p0_decisions.id'), primary_key=True)
    code: Mapped[str] = mapped_column(String(24))
    version: Mapped[str] = mapped_column(String(120))
    label: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[str] = mapped_column(String(40))


class NotificationDestination(Base):
    __tablename__ = 'cr_notification_destinations'
    notification_id: Mapped[str] = mapped_column(ForeignKey('p0_notifications.id'), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64))


class ClinicalReviewPacket(Base):
    __tablename__ = 'cr_review_packets'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(String(100))
    source_version: Mapped[str] = mapped_column(String(120))
    content_sha256: Mapped[str] = mapped_column(String(64))
    packet_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    creator_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    requested_at: Mapped[str] = mapped_column(String(40))
