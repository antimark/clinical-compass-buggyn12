"""Additive manual referrals and private physician copilot; no new medical document."""
from sqlalchemy import String, Text, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base

class Referral(Base):
    __tablename__='ci_referrals'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    actor_id:Mapped[str]=mapped_column(String(64),ForeignKey('users.id'))
    tenant_id:Mapped[str]=mapped_column(String(64))
    patient_id:Mapped[str]=mapped_column(String(64),ForeignKey('patients.id'))
    case_id:Mapped[str]=mapped_column(String(64),ForeignKey('cc_previsit_cases.id'))
    source_version:Mapped[str]=mapped_column(String(64))
    grant_version:Mapped[str]=mapped_column(String(64))
    revision:Mapped[int]=mapped_column(Integer)
    status:Mapped[str]=mapped_column(String(24))
    content_json:Mapped[str]=mapped_column(Text)
    confirmation_hash:Mapped[str]=mapped_column(String(64))
    created_at:Mapped[str]=mapped_column(String(40))
    updated_at:Mapped[str]=mapped_column(String(40))

class ReferralEvent(Base):
    __tablename__='ci_referral_events'
    __table_args__=(UniqueConstraint('referral_id','revision'),)
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    referral_id:Mapped[str]=mapped_column(String(64),ForeignKey('ci_referrals.id'))
    revision:Mapped[int]=mapped_column(Integer)
    actor_id:Mapped[str]=mapped_column(String(64),ForeignKey('users.id'))
    action:Mapped[str]=mapped_column(String(24))
    reason:Mapped[str]=mapped_column(Text)
    created_at:Mapped[str]=mapped_column(String(40))

class CopilotReceipt(Base):
    __tablename__='ci_operation_receipts'
    __table_args__=(UniqueConstraint('actor_id','key_hash'),)
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    actor_id:Mapped[str]=mapped_column(String(64),ForeignKey('users.id'))
    key_hash:Mapped[str]=mapped_column(String(64))
    request_digest:Mapped[str]=mapped_column(String(64))
    response_json:Mapped[str]=mapped_column(Text)
    created_at:Mapped[str]=mapped_column(String(40))

class CopilotThread(Base):
    __tablename__='ci_chat_threads'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    actor_id:Mapped[str]=mapped_column(String(64),ForeignKey('users.id'))
    tenant_id:Mapped[str]=mapped_column(String(64))
    patient_id:Mapped[str]=mapped_column(String(64),ForeignKey('patients.id'))
    case_id:Mapped[str|None]=mapped_column(String(64),ForeignKey('cc_previsit_cases.id'),nullable=True)
    audience:Mapped[str]=mapped_column(String(16),default='doctor',server_default='doctor')
    source_type:Mapped[str]=mapped_column(String(24),default='intake',server_default='intake')
    source_id:Mapped[str]=mapped_column(String(64),default='',server_default='')
    source_version:Mapped[str]=mapped_column(String(64))
    grant_version:Mapped[str]=mapped_column(String(64))
    revision:Mapped[int]=mapped_column(Integer)
    status:Mapped[str]=mapped_column(String(24))
    retention_state:Mapped[str]=mapped_column(String(24))
    created_at:Mapped[str]=mapped_column(String(40))
    updated_at:Mapped[str]=mapped_column(String(40))

class CopilotMessage(Base):
    __tablename__='ci_chat_messages'
    __table_args__=(UniqueConstraint('thread_id','ordinal'),)
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    thread_id:Mapped[str]=mapped_column(String(64),ForeignKey('ci_chat_threads.id'))
    ordinal:Mapped[int]=mapped_column(Integer)
    role:Mapped[str]=mapped_column(String(16))
    content:Mapped[str]=mapped_column(Text)
    provenance_json:Mapped[str]=mapped_column(Text)
    created_at:Mapped[str]=mapped_column(String(40))

class CopilotJob(Base):
    __tablename__='ci_chat_jobs'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    thread_id:Mapped[str]=mapped_column(String(64),ForeignKey('ci_chat_threads.id'))
    input_id:Mapped[str]=mapped_column(String(64),ForeignKey('ci_chat_messages.id'))
    status:Mapped[str]=mapped_column(String(24))
    safe_error_code:Mapped[str]=mapped_column(String(40))
    queued_at:Mapped[str]=mapped_column(String(40))
    started_at:Mapped[str]=mapped_column(String(40))
    finished_at:Mapped[str]=mapped_column(String(40))
    timings_json:Mapped[str]=mapped_column(Text)

class PatientDiary(Base):
    __tablename__='ci_patient_diaries'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    actor_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    tenant_id:Mapped[str]=mapped_column(String(64))
    content:Mapped[str]=mapped_column(Text)
    revision:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[str]=mapped_column(String(40))
    updated_at:Mapped[str]=mapped_column(String(40))
