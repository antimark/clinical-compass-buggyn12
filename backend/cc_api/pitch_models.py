"""Guided demonstration metadata, separate from patient clinical records."""
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base


class PitchRun(Base):
    __tablename__ = 'pt_runs'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    patient_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    started_at: Mapped[str] = mapped_column(String(40))


class PitchEscalationConfig(Base):
    __tablename__ = 'pt_escalation_configs'
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    signal_id: Mapped[str] = mapped_column(ForeignKey('dx_signals.id'), primary_key=True)
    delay_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    revision: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[str] = mapped_column(String(40))


class PitchEscalationSimulation(Base):
    __tablename__ = 'pt_escalation_simulations'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    signal_id: Mapped[str] = mapped_column(ForeignKey('dx_signals.id'))
    config_revision: Mapped[int] = mapped_column(Integer)
    config_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
