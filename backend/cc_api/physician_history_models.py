"""Append-only clinician reviews; account aliases remain stable."""
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base


class AdverseEventReviewRevision(Base):
    __tablename__ = 'dx_adverse_event_revisions'
    __table_args__ = (UniqueConstraint('event_id', 'version', name='uq_dx_adverse_review_version'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey('p0_adverse_events.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    review_text: Mapped[str] = mapped_column(Text)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[str] = mapped_column(String(40))


class PhysicianProfile(Base):
    __tablename__ = 'dx_physician_profiles'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150))
    synthetic: Mapped[int] = mapped_column(Integer, default=1)
    published_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProfilePhoto(Base):
    __tablename__ = 'profile_photos'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), unique=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[str] = mapped_column(String(40))
