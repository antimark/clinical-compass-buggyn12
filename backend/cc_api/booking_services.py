"""Persisted synthetic availability, proposals and serialized appointment transitions."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from flask import abort
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .models import User
from .extension_models import Appointment, PrevisitCase, Audit
from .clinical_workflow_models import (AvailabilitySlot, AppointmentProposal, ProposalCandidate,
    SlotBooking, RescheduleRequest)

class BookingFailure(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message

def uid(prefix): return prefix + uuid.uuid4().hex

def now(): return datetime.now(timezone.utc)

def parse(value):
    try:
        if not isinstance(value, str): raise ValueError()
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None: raise ValueError()
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise BookingFailure(422, 'Укажите дату и время с часовым поясом')

def stamp(value=None): return (value or now()).isoformat(timespec='microseconds').replace('+00:00', 'Z')

def dto(row): return {c.name:getattr(row,c.name) for c in row.__table__.columns}

def audit(db, actor, action, kind, key):
    db.add(Audit(id=uid('bka_'),actor=actor.id,action=action,object_type=kind,object_id=key,created_at=stamp()))

def lock_actors(db, *ids):
    for ident in sorted(set(ids)):
        db.execute(update(User).where(User.id==ident).values(display_name=User.display_name))

def case_access(db, actor, case_id, mutation=False):
    if actor.role not in ('doctor','patient'): abort(403)
    if mutation:
        db.execute(update(PrevisitCase).where(PrevisitCase.id==case_id,
            (PrevisitCase.doctor_id==actor.id)|(PrevisitCase.patient_user_id==actor.id)).values(status=PrevisitCase.status))
    case=db.execute(select(PrevisitCase.id,PrevisitCase.doctor_id,PrevisitCase.patient_user_id,
        PrevisitCase.status,PrevisitCase.allowed_until).where(PrevisitCase.id==case_id,
        (PrevisitCase.doctor_id==actor.id)|(PrevisitCase.patient_user_id==actor.id))).first()
    if not case or actor.id not in (case.doctor_id,case.patient_user_id): abort(404)
    doctor=db.get(User,case.doctor_id); patient=db.get(User,case.patient_user_id)
    if not doctor or not patient or doctor.organization_id!=patient.organization_id or actor.organization_id!=doctor.organization_id: abort(404)
    if case.status in ('declined','withdrawn','expired','closed','cancelled') or parse(case.allowed_until)<=now(): abort(403)
    return db.get(PrevisitCase,case.id,populate_existing=True)

def overlap(a,b,c,d): return a<d and c<b

def appointment_conflict(db, doctor_id, patient_id, start, end, exclude=()):
    q=select(Appointment).where(Appointment.status=='confirmed',Appointment.id.not_in(exclude))
    q=q.where((Appointment.doctor_id==doctor_id)|(Appointment.patient_user_id==patient_id)) if patient_id else q.where(Appointment.doctor_id==doctor_id)
    for appointment in db.scalars(q).all():
        booking=db.scalar(select(SlotBooking).where(SlotBooking.appointment_id==appointment.id))
        at=parse(booking.starts_at if booking else appointment.proposed_at)
        till=parse(booking.ends_at) if booking else at+timedelta(minutes=30)
        if overlap(start,end,at,till): return True
    return False

def create_slot(db, doctor, starts_at, ends_at):
    if doctor.role!='doctor': abort(403)
    start,end=parse(starts_at),parse(ends_at)
    if start<=now() or not timedelta(minutes=15)<=end-start<=timedelta(minutes=120):
        raise BookingFailure(422,'Слот должен быть в будущем, длительность 15–120 минут')
    lock_actors(db,doctor.id)
    for old in db.scalars(select(AvailabilitySlot).where(AvailabilitySlot.doctor_id==doctor.id,AvailabilitySlot.status!='cancelled')).all():
        if overlap(start,end,parse(old.starts_at),parse(old.ends_at)): raise BookingFailure(409,'Время пересекается с существующим слотом')
    if appointment_conflict(db,doctor.id,None,start,end): raise BookingFailure(409,'Время уже занято')
    row=AvailabilitySlot(id=uid('slot_'),doctor_id=doctor.id,starts_at=stamp(start),ends_at=stamp(end),status='available',revision=0)
    db.add(row);db.flush();audit(db,doctor,'availability_created','availability',row.id)
    return row

def free_slot(db, doctor, patient, row):
    if not row or row.doctor_id!=doctor.id: abort(404)
    if row.status!='available' or db.get(SlotBooking,row.id) or parse(row.starts_at)<=now(): raise BookingFailure(409,'Слот больше не доступен')
    if appointment_conflict(db,doctor.id,patient.id,parse(row.starts_at),parse(row.ends_at)): raise BookingFailure(409,'Время врача или пациента занято')

def proposal_payload(db, row):
    candidates=[]
    for candidate in db.scalars(select(ProposalCandidate).where(ProposalCandidate.proposal_id==row.id)).all():
        appointment=db.get(Appointment,candidate.appointment_id);slot=db.get(AvailabilitySlot,candidate.slot_id)
        candidates.append(dict(appointment_id=appointment.id,slot_id=slot.id,starts_at=slot.starts_at,ends_at=slot.ends_at,status=appointment.status))
    status='expired' if row.status=='pending' and parse(row.expires_at)<=now() else row.status
    return dict(id=row.id,case_id=row.case_id,expires_at=row.expires_at,status=status,candidates=candidates,
        reschedule_request_id=row.reschedule_request_id,accepted_appointment_id=row.accepted_appointment_id)

def create_proposal(db, doctor, case_id, slot_ids, expires_at=None, *, legacy=False, fmt='video', reschedule=None):
    if doctor.role!='doctor': abort(403)
    if not isinstance(slot_ids,list) or any(not isinstance(x,str) for x in slot_ids) or len(set(slot_ids))!=len(slot_ids) or len(slot_ids) not in ((1,) if legacy else (2,3)):
        raise BookingFailure(422,'Выберите два или три разных свободных слота')
    if fmt not in ('video','audio','in_person'): raise BookingFailure(422,'Неизвестный формат')
    metadata=db.execute(select(PrevisitCase.doctor_id,PrevisitCase.patient_user_id).where(PrevisitCase.id==case_id)).first()
    if not metadata or metadata.doctor_id!=doctor.id: abort(404)
    lock_actors(db,doctor.id,metadata.patient_user_id)
    case=case_access(db,doctor,case_id,True);patient=db.get(User,case.patient_user_id)
    slots=[db.get(AvailabilitySlot,ident,populate_existing=True) for ident in slot_ids]
    for slot in slots:free_slot(db,doctor,patient,slot)
    limit=min([parse(s.starts_at) for s in slots]+[parse(case.allowed_until)])
    expiry=parse(expires_at) if expires_at is not None else limit
    if expiry<=now() or expiry>limit: raise BookingFailure(422,'Предложение истекает не позднее начала каждого слота и срока доступа к обращению')
    row=AppointmentProposal(id=uid('proposal_'),case_id=case.id,doctor_id=doctor.id,patient_user_id=patient.id,
        slot_ids_json=json.dumps(slot_ids),expires_at=stamp(expiry),status='pending',created_at=stamp(),
        accepted_appointment_id=None,reschedule_request_id=reschedule.id if reschedule else None)
    db.add(row);db.flush()
    for slot in slots:
        appointment=Appointment(id=uid('appt_'),case_id=case.id,doctor_id=doctor.id,patient_user_id=patient.id,
            proposed_at=slot.starts_at,format=fmt,status='offered')
        db.add(appointment);db.flush();db.add(ProposalCandidate(appointment_id=appointment.id,proposal_id=row.id,slot_id=slot.id))
    audit(db,doctor,'appointment_proposal_created','appointment_proposal',row.id);db.flush()
    return row

def legacy_offer(db,doctor,case_id,at,fmt):
    start=parse(at);case=case_access(db,doctor,case_id)
    if case.doctor_id!=doctor.id:abort(404)
    lock_actors(db,doctor.id,case.patient_user_id)
    slot=db.scalar(select(AvailabilitySlot).where(AvailabilitySlot.doctor_id==doctor.id,AvailabilitySlot.starts_at==stamp(start)))
    if slot is None:slot=create_slot(db,doctor,stamp(start),stamp(start+timedelta(minutes=30)))
    proposal=create_proposal(db,doctor,case_id,[slot.id],legacy=True,fmt=fmt)
    return db.get(Appointment,db.scalar(select(ProposalCandidate.appointment_id).where(ProposalCandidate.proposal_id==proposal.id)))

def accept_appointment(db,patient,appointment_id):
    if patient.role!='patient':abort(403)
    metadata=db.get(Appointment,appointment_id)
    if not metadata:abort(404)
    if metadata.patient_user_id!=patient.id:abort(403)
    lock_actors(db,metadata.doctor_id,patient.id)
    appointment=db.get(Appointment,appointment_id,populate_existing=True)
    case=case_access(db,patient,appointment.case_id,True)
    if appointment.status!='offered':raise BookingFailure(409,'Предложение уже обработано')
    candidate=db.get(ProposalCandidate,appointment.id)
    doctor=db.get(User,appointment.doctor_id)
    if candidate is None:
        # Adopt only an actual persisted legacy physician offer. No client-created booking.
        start=parse(appointment.proposed_at)
        slot=create_slot(db,doctor,stamp(start),stamp(start+timedelta(minutes=30)))
        proposal=AppointmentProposal(id=uid('proposal_'),case_id=case.id,doctor_id=doctor.id,patient_user_id=patient.id,
            slot_ids_json=json.dumps([slot.id]),expires_at=stamp(min(start,parse(case.allowed_until))),status='pending',
            created_at=stamp(),accepted_appointment_id=None,reschedule_request_id=None)
        db.add(proposal);db.flush();candidate=ProposalCandidate(appointment_id=appointment.id,proposal_id=proposal.id,slot_id=slot.id);db.add(candidate);db.flush()
    proposal=db.get(AppointmentProposal,candidate.proposal_id,populate_existing=True)
    if proposal.status!='pending' or parse(proposal.expires_at)<=now():raise BookingFailure(409,'Срок предложения истёк или оно уже принято')
    slot=db.get(AvailabilitySlot,candidate.slot_id,populate_existing=True)
    free_slot(db,doctor,patient,slot)
    changed=db.execute(update(Appointment).where(Appointment.id==appointment.id,Appointment.status=='offered').values(status='confirmed')).rowcount
    if changed!=1:raise BookingFailure(409,'Предложение уже обработано')
    slot.status='booked';slot.revision+=1;proposal.status='accepted';proposal.accepted_appointment_id=appointment.id
    try:
        db.add(SlotBooking(slot_id=slot.id,appointment_id=appointment.id,doctor_id=doctor.id,patient_user_id=patient.id,starts_at=slot.starts_at,ends_at=slot.ends_at));db.flush()
    except IntegrityError:raise BookingFailure(409,'Слот уже занят')
    for other in db.scalars(select(ProposalCandidate).where(ProposalCandidate.proposal_id==proposal.id,ProposalCandidate.appointment_id!=appointment.id)).all():
        sibling=db.get(Appointment,other.appointment_id)
        if sibling.status=='offered':sibling.status='cancelled'
    if proposal.reschedule_request_id:
        request=db.get(RescheduleRequest,proposal.reschedule_request_id,populate_existing=True)
        original=db.get(Appointment,request.appointment_id,populate_existing=True)
        if request.status!='requested' or original.status!='confirmed':raise BookingFailure(409,'Запрос переноса уже обработан')
        original.status='cancelled';old_booking=db.scalar(select(SlotBooking).where(SlotBooking.appointment_id==original.id))
        if old_booking:
            old_slot=db.get(AvailabilitySlot,old_booking.slot_id);old_slot.status='available';old_slot.revision+=1;db.delete(old_booking)
        request.status='resolved';request.resolved_at=stamp();request.replacement_appointment_id=appointment.id
        audit(db,patient,'reschedule_resolved','reschedule_request',request.id)
    from .clinical_review_services import event_notice
    for recipient in (patient.id,doctor.id):
        event_notice(db,recipient,'appointment','Запись подтверждена после выбора пациентом предложенного времени','appointment',appointment.id)
    audit(db,patient,'appointment_confirmed','appointment',appointment.id);db.flush();db.refresh(appointment)
    return appointment
