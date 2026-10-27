"""Cookie/CSRF guarded synthetic booking routes; no browser-only confirmations."""
from flask import abort,request
from sqlalchemy import select
from .verification import workspace_enabled
from .models import User
from .extension_models import Appointment,PrevisitCase
from .clinical_workflow_models import AvailabilitySlot,AppointmentProposal,RescheduleRequest
from .booking_services import (BookingFailure,create_slot,create_proposal,proposal_payload,accept_appointment,
    case_access,lock_actors,dto,stamp,uid,audit)
BASE='/api/v1/booking'

def register_booking_routes(app,SessionLocal,current_user,require_role,error,utc_now):
    @app.errorhandler(BookingFailure)
    def booking_error(exc):return error(exc.status,'BOOKING_CONFLICT' if exc.status==409 else 'INVALID_BOOKING',exc.message)
    @app.before_request
    def booking_guard():
        if request.path.startswith(BASE+'/') and not workspace_enabled(app.config):return error(403,'SYNTHETIC_PROFILE_REQUIRED','Доступно только в synthetic_dev')
    def actor(db):
        user=current_user(db)
        if not user:abort(401)
        return user
    def body(fields):
        value=request.get_json(silent=True)
        if not isinstance(value,dict) or set(value)-set(fields):abort(422)
        return value
    @app.get(BASE+'/slots')
    def booking_slots():
        with SessionLocal() as db:
            doctor=require_role(db,'doctor')
            return {'items':[dto(s) for s in db.scalars(select(AvailabilitySlot).where(AvailabilitySlot.doctor_id==doctor.id).order_by(AvailabilitySlot.starts_at)).all()]}
    @app.post(BASE+'/slots')
    def booking_new_slot():
        data=body(('starts_at','ends_at'))
        with SessionLocal.begin() as db:
            row=create_slot(db,require_role(db,'doctor'),data.get('starts_at'),data.get('ends_at'));result=dto(row)
        return result,201
    @app.get(BASE+'/cases/<case_id>/proposals')
    def booking_proposals(case_id):
        with SessionLocal() as db:
            user=actor(db);case_access(db,user,case_id)
            return {'items':[proposal_payload(db,p) for p in db.scalars(select(AppointmentProposal).where(AppointmentProposal.case_id==case_id).order_by(AppointmentProposal.created_at.desc())).all()]}
    @app.post(BASE+'/cases/<case_id>/proposals')
    def booking_new_proposal(case_id):
        data=body(('slot_ids','expires_at','format'))
        with SessionLocal.begin() as db:
            row=create_proposal(db,require_role(db,'doctor'),case_id,data.get('slot_ids'),data.get('expires_at'),fmt=data.get('format','video'));result=proposal_payload(db,row)
        return result,201
    @app.post(BASE+'/appointments/<appointment_id>/accept')
    def booking_accept(appointment_id):
        body(())
        with SessionLocal.begin() as db:result=dto(accept_appointment(db,require_role(db,'patient'),appointment_id))
        return result
    def appointment_access(db,user,aid):
        row=db.get(Appointment,aid)
        if user.role not in ('doctor','patient'):abort(403)
        if not row or user.id not in (row.doctor_id,row.patient_user_id):abort(404)
        case_access(db,user,row.case_id)
        return row
    @app.post(BASE+'/appointments/<appointment_id>/reschedule')
    def booking_reschedule(appointment_id):
        data=body(('reason',));reason=data.get('reason')
        if not isinstance(reason,str) or not 1<=len(reason.strip())<=2000:abort(422)
        with SessionLocal.begin() as db:
            user=actor(db);row=appointment_access(db,user,appointment_id);lock_actors(db,row.doctor_id,row.patient_user_id)
            row=appointment_access(db,user,appointment_id)
            if row.status!='confirmed':raise BookingFailure(409,'Перенос запрашивается для подтверждённого приёма')
            if db.scalar(select(RescheduleRequest.id).where(RescheduleRequest.appointment_id==row.id,RescheduleRequest.status=='requested')):raise BookingFailure(409,'Запрос переноса уже существует')
            item=RescheduleRequest(id=uid('resched_'),appointment_id=row.id,requester_id=user.id,reason=reason.strip(),status='requested',created_at=stamp(),resolved_at=None,replacement_appointment_id=None)
            db.add(item);db.flush();audit(db,user,'reschedule_requested','reschedule_request',item.id);result=dto(item)
        return result,201
    @app.get(BASE+'/reschedule-requests')
    def booking_reschedules():
        with SessionLocal() as db:
            user=actor(db)
            if user.role not in ('doctor','patient'):abort(403)
            owned=select(Appointment.id).where(Appointment.doctor_id==user.id if user.role=='doctor' else Appointment.patient_user_id==user.id)
            rows=db.execute(select(RescheduleRequest.id,RescheduleRequest.appointment_id).where(RescheduleRequest.appointment_id.in_(owned))).all();result=[]
            from werkzeug.exceptions import HTTPException
            for row in rows:
                try:appointment_access(db,user,row.appointment_id)
                except HTTPException:continue
                result.append(dto(db.get(RescheduleRequest,row.id)))
            return {'items':result}
    @app.post(BASE+'/reschedule-requests/<request_id>/propose')
    def booking_reschedule_proposal(request_id):
        data=body(('slot_ids','expires_at','format'))
        with SessionLocal.begin() as db:
            doctor=require_role(db,'doctor')
            aid=db.scalar(select(RescheduleRequest.appointment_id).where(RescheduleRequest.id==request_id))
            if not aid:abort(404)
            appointment=appointment_access(db,doctor,aid)
            lock_actors(db,doctor.id,appointment.patient_user_id)
            item=db.get(RescheduleRequest,request_id,populate_existing=True)
            if item.status!='requested' or appointment.status!='confirmed':raise BookingFailure(409,'Запрос переноса уже обработан')
            proposal=create_proposal(db,doctor,appointment.case_id,data.get('slot_ids'),data.get('expires_at'),fmt=data.get('format','video'),reschedule=item);result=proposal_payload(db,proposal)
        return result,201
