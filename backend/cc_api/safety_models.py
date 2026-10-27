"""Durable detection/outbox metadata, reusing the existing DoctorSignal entity."""
from sqlalchemy import String, Text, Integer, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base

class SafetyDetection(Base):
    __tablename__='cc_safety_detections'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    signal_id:Mapped[str|None]=mapped_column(ForeignKey('dx_signals.id'),nullable=True,unique=True)
    source_id:Mapped[str]=mapped_column(ForeignKey('cc_previsit_cases.id'))
    patient_id:Mapped[str]=mapped_column(ForeignKey('patients.id'))
    recipient_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    tenant_id:Mapped[str]=mapped_column(String(64))
    source_version:Mapped[str]=mapped_column(String(64))
    grant_version:Mapped[str]=mapped_column(String(64))
    trace_json:Mapped[str]=mapped_column(Text)
    status:Mapped[str]=mapped_column(String(32))
    workflow_status:Mapped[str]=mapped_column(String(24))
    revision:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[str]=mapped_column(String(40))

class SafetyOutbox(Base):
    __tablename__='cc_safety_outbox'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    detection_id:Mapped[str]=mapped_column(ForeignKey('cc_safety_detections.id'),unique=True)
    status:Mapped[str]=mapped_column(String(24))
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    next_at:Mapped[float]=mapped_column(Float,default=0)
    lease_until:Mapped[float]=mapped_column(Float,default=0)
    lease_token:Mapped[str]=mapped_column(String(64),default='')
    receipt:Mapped[str]=mapped_column(String(64),default='')
    delivered_at:Mapped[str]=mapped_column(String(40),default='')
    created_at:Mapped[str]=mapped_column(String(40))

class SafetyAttempt(Base):
    __tablename__='cc_safety_attempts'
    __table_args__=(UniqueConstraint('outbox_id','number'),)
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    outbox_id:Mapped[str]=mapped_column(ForeignKey('cc_safety_outbox.id'))
    number:Mapped[int]=mapped_column(Integer)
    status:Mapped[str]=mapped_column(String(32))
    created_at:Mapped[str]=mapped_column(String(40))
    finished_at:Mapped[str]=mapped_column(String(40),default='')
    receipt:Mapped[str]=mapped_column(String(64),default='')

class SafetyInbox(Base):
    """Separate idempotent receiver, never stores source text/patient identifiers."""
    __tablename__='cc_safety_inbox'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    outbox_id:Mapped[str]=mapped_column(String(64),unique=True)
    recipient_id:Mapped[str]=mapped_column(String(64))
    envelope_json:Mapped[str]=mapped_column(Text)
    received_at:Mapped[str]=mapped_column(String(40))

class SafetyAction(Base):
    __tablename__='cc_safety_actions'
    __table_args__=(UniqueConstraint('detection_id','revision'),UniqueConstraint('actor_id','key_hash'))
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    detection_id:Mapped[str]=mapped_column(ForeignKey('cc_safety_detections.id'))
    actor_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    revision:Mapped[int]=mapped_column(Integer)
    action:Mapped[str]=mapped_column(String(24))
    key_hash:Mapped[str|None]=mapped_column(String(64),nullable=True)
    request_digest:Mapped[str]=mapped_column(String(64),default='')
    created_at:Mapped[str]=mapped_column(String(40))
