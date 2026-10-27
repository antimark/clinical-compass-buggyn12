"""Evidence-linked demonstration signals and independent clinician assessments."""
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base


class DoctorSignal(Base):
    __tablename__ = 'dx_signals'
    __table_args__ = (UniqueConstraint('doctor_id', 'event_key', name='uq_dx_signal_event'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'))
    kind: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(64))
    event_key: Mapped[str] = mapped_column(String(160))
    rule_version: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), default='open')
    created_at: Mapped[str] = mapped_column(String(40))


class DoctorSignalReview(Base):
    __tablename__ = 'dx_signal_reviews'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    signal_id: Mapped[str] = mapped_column(ForeignKey('dx_signals.id'), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(24))
    assessment: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))


class PhysicianPriority(Base):
    __tablename__ = 'dx_priorities'
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), primary_key=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(500), default='')
    revision: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[str] = mapped_column(String(40))
