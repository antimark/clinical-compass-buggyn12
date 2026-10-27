"""Versioned clinician documents, orders and atomic synthetic scheduling."""
from sqlalchemy import ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base


class ClinicalDocument(Base):
    __tablename__ = 'cd_documents'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64), ForeignKey('patients.id'))
    clinician_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    kind: Mapped[str] = mapped_column(String(24))
    mode: Mapped[str] = mapped_column(String(24))
    content_json: Mapped[str] = mapped_column(Text())
    required_scopes: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(24))
    revision: Mapped[int] = mapped_column(Integer())
    parent_id: Mapped[str | None] = mapped_column(String(64), ForeignKey('cd_documents.id'), nullable=True)
    amendment_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    signed_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
    signed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    published_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

class ClinicalDocumentRevision(Base):
    __tablename__ = 'cd_document_revisions'
    __table_args__ = (UniqueConstraint('document_id', 'revision'), )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey('cd_documents.id'))
    revision: Mapped[int] = mapped_column(Integer())
    action: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    snapshot_json: Mapped[str] = mapped_column(Text())
    created_at: Mapped[str] = mapped_column(String(40))

class MedicationOrder(Base):
    __tablename__ = 'cd_medication_orders'
    __table_args__ = (ForeignKeyConstraint(['reference_id','reference_version'],
        ['sr_medication_references.id','sr_medication_references.version'], name='fk_cd_order_reference'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey('cd_documents.id'))
    patient_id: Mapped[str] = mapped_column(String(64), ForeignKey('patients.id'))
    clinician_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    title: Mapped[str] = mapped_column(String(200))
    reference_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reference_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    regimen_json: Mapped[str] = mapped_column(Text())
    created_at: Mapped[str] = mapped_column(String(40))

class MedicationAdherence(Base):
    __tablename__ = 'cd_medication_adherence'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey('cd_medication_orders.id'))
    patient_user_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    outcome: Mapped[str] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(Text())
    recorded_at: Mapped[str] = mapped_column(String(40))

class AvailabilitySlot(Base):
    __tablename__ = 'cd_availability_slots'
    __table_args__ = (UniqueConstraint('doctor_id', 'starts_at'), )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    starts_at: Mapped[str] = mapped_column(String(40))
    ends_at: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24))
    revision: Mapped[int] = mapped_column(Integer())

class RescheduleRequest(Base):
    __tablename__ = 'cd_reschedule_requests'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    appointment_id: Mapped[str] = mapped_column(String(64), ForeignKey('cc_appointments.id'))
    requester_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(Text())
    status: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[str] = mapped_column(String(40))
    resolved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    replacement_appointment_id: Mapped[str | None] = mapped_column(String(64), ForeignKey('cc_appointments.id'), nullable=True)

class AppointmentProposal(Base):
    __tablename__ = 'cd_appointment_proposals'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey('cc_previsit_cases.id'))
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    patient_user_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    slot_ids_json: Mapped[str] = mapped_column(Text())
    expires_at: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[str] = mapped_column(String(40))
    accepted_appointment_id: Mapped[str | None] = mapped_column(String(64), ForeignKey('cc_appointments.id'), nullable=True)
    reschedule_request_id: Mapped[str | None] = mapped_column(String(64), ForeignKey('cd_reschedule_requests.id'), nullable=True)

class ProposalCandidate(Base):
    __tablename__ = 'cd_proposal_candidates'
    appointment_id: Mapped[str] = mapped_column(String(64), ForeignKey('cc_appointments.id'), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(64), ForeignKey('cd_appointment_proposals.id'))
    slot_id: Mapped[str] = mapped_column(String(64), ForeignKey('cd_availability_slots.id'))

class SlotBooking(Base):
    __tablename__ = 'cd_slot_bookings'
    __table_args__ = (UniqueConstraint('appointment_id'), )
    slot_id: Mapped[str] = mapped_column(String(64), ForeignKey('cd_availability_slots.id'), primary_key=True)
    appointment_id: Mapped[str] = mapped_column(String(64), ForeignKey('cc_appointments.id'))
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    patient_user_id: Mapped[str] = mapped_column(String(64), ForeignKey('users.id'))
    starts_at: Mapped[str] = mapped_column(String(40))
    ends_at: Mapped[str] = mapped_column(String(40))
