"""Clinic scheduling metadata, with no clinical chart or silent confirmation."""
from flask import abort,request
from sqlalchemy import select
from .models import User
from .extension_models import Appointment,PrevisitCase
from .clinical_workflow_models import AvailabilitySlot,RescheduleRequest,AppointmentProposal
from .booking_services import BookingFailure,lock_actors,stamp,uid,audit,proposal_payload
from .verification import workspace_enabled
BASE='/api/v1/clinic-workflow'


def admin_appointment(db,admin,appointment_id):
    if admin.role!='clinic_admin':abort(403)
    metadata=db.execute(select(Appointment.id,Appointment.doctor_id,Appointment.patient_user_id,
        Appointment.case_id,Appointment.proposed_at,Appointment.status,Appointment.format)
        .where(Appointment.id==appointment_id)).first()
    if not metadata:abort(404)
    doctor=db.get(User,metadata.doctor_id);patient=db.get(User,metadata.patient_user_id)
    if not doctor or not patient or doctor.role!='doctor' or patient.role!='patient' or doctor.organization_id!=admin.organization_id or patient.organization_id!=admin.organization_id:abort(404)
    return metadata


def request_admin_reschedule(db,admin,appointment_id,reason,doctor_id=None):
    metadata=admin_appointment(db,admin,appointment_id)
    if doctor_id is not None and doctor_id!=metadata.doctor_id:
        # A first-contact consent names its recipient physician. Admin cannot
        # transfer it or silently create a new treating relationship.
        raise BookingFailure(409,'Для другого врача нужно новое обращение и явное согласие пациента')
    if not isinstance(reason,str) or not 1<=len(reason.strip())<=2000:abort(422)
    lock_actors(db,metadata.doctor_id,metadata.patient_user_id)
    metadata=admin_appointment(db,admin,appointment_id)
    if metadata.status not in ('confirmed','requested','offered'):
        raise BookingFailure(409,'Запись больше не допускает запрос переноса')
    existing=db.scalar(select(RescheduleRequest).where(RescheduleRequest.appointment_id==appointment_id,
        RescheduleRequest.status=='requested'))
    if existing:return existing
    row=RescheduleRequest(id=uid('resched_'),appointment_id=appointment_id,requester_id=admin.id,
        reason=reason.strip(),status='requested',created_at=stamp(),resolved_at=None,replacement_appointment_id=None)
    db.add(row);db.flush();audit(db,admin,'clinic_reschedule_requested','reschedule_request',row.id)
    return row


def register_admin_booking_routes(app,SessionLocal,current_user,require_role,error,utc_now):
    @app.before_request
    def clinic_booking_guard():
        if request.path.startswith(BASE+'/') and not workspace_enabled(app.config):
            return error(403,'SYNTHETIC_PROFILE_REQUIRED','Доступно только в синтетической среде')

    @app.get(BASE+'/slots')
    def clinic_booking_slots():
        with SessionLocal() as db:
            admin=require_role(db,'clinic_admin')
            doctors=select(User.id).where(User.role=='doctor',User.organization_id==admin.organization_id)
            rows=db.scalars(select(AvailabilitySlot).where(AvailabilitySlot.doctor_id.in_(doctors)).order_by(AvailabilitySlot.starts_at)).all()
            return {'items':[dict(id=x.id,doctor_id=x.doctor_id,starts_at=x.starts_at,ends_at=x.ends_at,
                status=x.status,revision=x.revision) for x in rows]}

    @app.get(BASE+'/appointments')
    def clinic_booking_appointments():
        with SessionLocal() as db:
            admin=require_role(db,'clinic_admin')
            doctors=select(User.id).where(User.role=='doctor',User.organization_id==admin.organization_id)
            patients=select(User.id).where(User.role=='patient',User.organization_id==admin.organization_id)
            rows=db.execute(select(Appointment.id,Appointment.doctor_id,Appointment.proposed_at,Appointment.status,
                Appointment.format).where(Appointment.doctor_id.in_(doctors),Appointment.patient_user_id.in_(patients))
                .order_by(Appointment.proposed_at)).all()
            return {'items':[dict(id=x.id,doctor_id=x.doctor_id,proposed_at=x.proposed_at,status=x.status,
                format=x.format) for x in rows]}

    @app.post(BASE+'/appointments/<appointment_id>/reschedule')
    def clinic_booking_reschedule(appointment_id):
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or set(data)-{'reason','doctor_id'}:abort(422)
        with SessionLocal.begin() as db:
            row=request_admin_reschedule(db,require_role(db,'clinic_admin'),appointment_id,data.get('reason'),data.get('doctor_id'))
            return dict(id=row.id,appointment_id=row.appointment_id,status=row.status,
                booking_confirmed=False,requires_physician_proposal=True,requires_patient_acceptance=True),200

    @app.get(BASE+'/appointments/<appointment_id>/proposals')
    def clinic_booking_proposals(appointment_id):
        with SessionLocal() as db:
            metadata=admin_appointment(db,require_role(db,'clinic_admin'),appointment_id)
            items=[]
            for row in db.scalars(select(AppointmentProposal).where(AppointmentProposal.case_id==metadata.case_id)).all():
                payload=proposal_payload(db,row)
                # No patient identifier, case content, messages or reasons.
                items.append(dict(id=payload['id'],status=payload['status'],expires_at=payload['expires_at'],
                    candidates=payload['candidates']))
            return {'items':items,'confirmation_requires_patient_acceptance':True}
