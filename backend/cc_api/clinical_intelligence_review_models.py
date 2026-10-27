"""Immutable source claims, physician-specific versioned review and native handoff receipts."""
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base


class CiSuggestionClaim(Base):
    __tablename__ = 'ci_suggestion_claims'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    organization_id: Mapped[str] = mapped_column(String(64))
    patient_id: Mapped[str] = mapped_column(String(64), ForeignKey('patients.id'))
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey('cc_previsit_cases.id'))
    source_version: Mapped[str] = mapped_column(String(64))
    grant_version: Mapped[str] = mapped_column(String(64))
    provenance_json: Mapped[str] = mapped_column(Text())
    created_at: Mapped[str] = mapped_column(String(40))


class CiReview(Base):
    __tablename__ = 'ci_reviews'
    suggestion_id: Mapped[str] = mapped_column(String(64), ForeignKey('ci_suggestion_claims.id'), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer())
    state_json: Mapped[str] = mapped_column(Text())
    updated_at: Mapped[str] = mapped_column(String(40))


class CiReviewEvent(Base):
    __tablename__ = 'ci_review_events'
    __table_args__ = (UniqueConstraint('suggestion_id', 'revision'), UniqueConstraint('actor_id', 'key_hash'))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    suggestion_id: Mapped[str] = mapped_column(String(64), ForeignKey('ci_suggestion_claims.id'))
    actor_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    revision: Mapped[int] = mapped_column(Integer())
    key_hash: Mapped[str] = mapped_column(String(64))
    request_digest: Mapped[str] = mapped_column(String(64))
    prior_digest: Mapped[str] = mapped_column(String(64))
    state_json: Mapped[str] = mapped_column(Text())
    created_at: Mapped[str] = mapped_column(String(40))


class CiDraftTransfer(Base):
    __tablename__ = 'ci_draft_transfers'
    __table_args__ = (UniqueConstraint('actor_id', 'key_hash'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    suggestion_id: Mapped[str] = mapped_column(String(64), ForeignKey('ci_suggestion_claims.id'))
    actor_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    review_revision: Mapped[int] = mapped_column(Integer())
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey('cd_documents.id'))
    document_revision: Mapped[int] = mapped_column(Integer())
    target_field: Mapped[str] = mapped_column(String(32))
    text_digest: Mapped[str] = mapped_column(String(64))
    key_hash: Mapped[str] = mapped_column(String(64))
    request_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))
