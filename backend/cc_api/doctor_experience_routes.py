"""Physician dashboard: scoped evidence, append-only review and independent priority."""
import json
import uuid
from flask import abort, request
from sqlalchemy import select, update
from werkzeug.exceptions import HTTPException
from .models import User, DoctorPatientLink
from .extension_models import Audit, Appointment, PrevisitCase
from .patient_experience_models import DemoQuestionnaireAssignment, DemoQuestionnaireSubmission
from .doctor_experience_models import DoctorSignal, DoctorSignalReview, PhysicianPriority
from .doctor_access import authorized_patient
from .doctor_signals import (LIMITATION, canonical_observations, discover_signals,
                            normalized_time, signal_payload)
from .verification import workspace_enabled

BASE = '/api/v1/doctor-experience'


def register_doctor_experience_routes(app, SessionLocal, current_user, require_role, error, utc_now):
    @app.before_request
    def doctor_experience_guard():
        if request.path.startswith(BASE + '/') and request.path != BASE + '/capabilities' and not workspace_enabled(app.config):
            return error(403, 'SYNTHETIC_PROFILE_REQUIRED', 'Доступно только в synthetic_dev')

    def stamp():
        value = utc_now()
        return value if isinstance(value, str) else value.isoformat().replace('+00:00', 'Z')

    def body(fields):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) - set(fields):
            abort(422)
        return data

    def audit(db, user, action, kind, object_id):
        db.add(Audit(id='dxa_' + uuid.uuid4().hex, actor=user.id, action=action,
            object_type=kind, object_id=object_id, created_at=stamp()))

    def permitted(db, doctor, pid, scope):
        try:
            return authorized_patient(db, doctor, pid, scope=scope)
        except HTTPException as exc:
            if exc.code != 404:
                raise
            return None

    def allowed_patients(db, doctor):
        result = {}
        for pid in db.scalars(select(DoctorPatientLink.patient_id).where(DoctorPatientLink.doctor_id == doctor.id)).all():
            person = permitted(db, doctor, pid, None)
            if not person:
                continue
            scopes = [s for s in ('symptoms', 'medications') if permitted(db, doctor, pid, s)]
            result[pid] = (person, scopes)
        return result

    def scoped_signal(db, doctor, signal_id, lock=False):
        # Metadata first; no stored text/evidence selected until current authorization.
        metadata = db.execute(select(DoctorSignal.patient_id, DoctorSignal.source).where(
            DoctorSignal.id == signal_id, DoctorSignal.doctor_id == doctor.id)).first()
        if not metadata or metadata.source == 'consented_intake_safety':
            abort(404)
        scope = 'medications' if metadata.source == 'reported_adverse_event' else 'symptoms'
        person = authorized_patient(db, doctor, metadata.patient_id, scope=scope, lock=lock)
        return db.get(DoctorSignal, signal_id), person

    def signals(db, doctor, allowed, now):
        output = []
        for pid, (person, scopes) in allowed.items():
            discover_signals(db, doctor.id, pid, scopes, now)
            # Restrict by source before loading evidence; absent grants never read content.
            sources = []
            if 'symptoms' in scopes:
                sources.extend(('wellbeing_observation', 'patient_checkin_note'))
            if 'medications' in scopes:
                sources.append('reported_adverse_event')
            rows = db.scalars(select(DoctorSignal).where(DoctorSignal.doctor_id == doctor.id,
                DoctorSignal.patient_id == pid, DoctorSignal.source.in_(sources))).all()
            output.extend(signal_payload(row, person.display_name) for row in rows)
        return sorted(output, key=lambda s: (s['status'] == 'open', s['occurred_at'], s['id']), reverse=True)

    def case_appointments(db, doctor, now):
        cases = []
        appointments = []
        for row in db.scalars(select(PrevisitCase).where(PrevisitCase.doctor_id == doctor.id)).all():
            person = db.scalar(select(User).where(User.id == row.patient_user_id,
                User.role == 'patient', User.organization_id == doctor.organization_id))
            if not person or row.status in ('declined', 'withdrawn', 'expired'):
                continue
            if normalized_time(row.allowed_until) <= normalized_time(now):
                continue
            cases.append(dict(id=row.id, patient_user_id=person.id, patient_id=person.patient_id,
                patient_name=person.display_name, status=row.status, created_at=row.created_at,
                allowed_until=row.allowed_until))
            for appointment in db.scalars(select(Appointment).where(Appointment.case_id == row.id,
                    Appointment.doctor_id == doctor.id, Appointment.patient_user_id == person.id,
                    Appointment.status.in_(('offered', 'confirmed', 'accepted')))).all():
                if not appointment.proposed_at or normalized_time(appointment.proposed_at) <= normalized_time(now):
                    continue
                appointments.append(dict(id=appointment.id, case_id=row.id, patient_id=person.patient_id,
                    patient_name=person.display_name, proposed_at=appointment.proposed_at,
                    format=appointment.format, status=appointment.status))
        return sorted(cases, key=lambda c: c['created_at'], reverse=True), sorted(appointments, key=lambda a: a['proposed_at'])

    def dashboard(db, doctor):
        sort = request.args.get('sort', 'attention')
        selected_filter = request.args.get('filter', 'all')
        query = request.args.get('q', '')
        if sort not in ('attention', 'appointment', 'name', 'priority') or selected_filter not in ('all', 'attention', 'priority') or len(query) > 100:
            abort(422)
        now = stamp()
        allowed = allowed_patients(db, doctor)
        all_signals = signals(db, doctor, allowed, now)
        cases, appointments = case_appointments(db, doctor, now)
        rows = []
        for pid, (person, scopes) in allowed.items():
            priority = db.get(PhysicianPriority, (doctor.id, pid)) if 'symptoms' in scopes else None
            points = canonical_observations(db, pid) if 'symptoms' in scopes else []
            completed = len(db.scalars(select(DemoQuestionnaireSubmission.id).join(DemoQuestionnaireAssignment,
                DemoQuestionnaireAssignment.id == DemoQuestionnaireSubmission.assignment_id)
                .where(DemoQuestionnaireAssignment.patient_id == pid)).all()) if 'symptoms' in scopes else 0
            upcoming = [a['proposed_at'] for a in appointments if a['patient_id'] == pid]
            rows.append(dict(id=pid, display_name=person.display_name, physician_priority=priority.priority if priority else 0,
                priority_revision=priority.revision if priority else 0, priority_note=priority.note if priority else '',
                open_signal_count=sum(s['patient_id'] == pid and s['status'] == 'open' for s in all_signals),
                latest_observed_at=points[-1]['observed_at'] if points else None,
                nearest_appointment_at=min(upcoming) if upcoming else None,
                completed_questionnaire_count=completed, scope=scopes))
        counters = dict(patients=len(rows), attention=sum(r['open_signal_count'] > 0 for r in rows),
            cases=len(cases), appointments=len(appointments))
        if query:
            rows = [r for r in rows if query.casefold() in r['display_name'].casefold()]
        if selected_filter == 'attention':
            rows = [r for r in rows if r['open_signal_count']]
        elif selected_filter == 'priority':
            rows = [r for r in rows if r['physician_priority']]
        sorters = dict(attention=lambda r: (-r['open_signal_count'], -r['physician_priority'], r['display_name'].casefold()),
            appointment=lambda r: (r['nearest_appointment_at'] is None, r['nearest_appointment_at'] or '', r['display_name'].casefold()),
            name=lambda r: r['display_name'].casefold(), priority=lambda r: (-r['physician_priority'], r['display_name'].casefold()))
        rows.sort(key=sorters[sort])
        db.commit()
        from .physician_history_models import PhysicianProfile
        profile = db.get(PhysicianProfile, doctor.id)
        return dict(doctor=dict(display_name=doctor.display_name, full_name=profile.full_name if profile else doctor.display_name), warnings=[s for s in all_signals if s['status'] == 'open'], patients=rows,
            counters=counters, cases=cases, appointments=appointments, sort=sort, filter=selected_filter, limitation=LIMITATION)

    @app.get(BASE + '/capabilities')
    def dx_capabilities():
        return {'enabled': workspace_enabled(app.config)}

    @app.get(BASE + '/dashboard')
    @app.get(BASE + '/patients')
    def dx_dashboard():
        with SessionLocal() as db:
            return dashboard(db, require_role(db, 'doctor'))

    @app.get(BASE + '/signals')
    def dx_signals():
        with SessionLocal() as db:
            doctor = require_role(db, 'doctor')
            output = signals(db, doctor, allowed_patients(db, doctor), stamp())
            db.commit()
            return {'items': output}

    @app.get(BASE + '/signals/<signal_id>')
    def dx_signal_detail(signal_id):
        with SessionLocal() as db:
            doctor = require_role(db, 'doctor')
            row, person = scoped_signal(db, doctor, signal_id)
            output = signal_payload(row, person.display_name)
            output['reviews'] = [dict(id=r.id, status=r.status, assessment=r.assessment, created_at=r.created_at)
                for r in db.scalars(select(DoctorSignalReview).where(DoctorSignalReview.signal_id == row.id,
                    DoctorSignalReview.doctor_id == doctor.id).order_by(DoctorSignalReview.created_at, DoctorSignalReview.id)).all()]
            return output

    @app.put(BASE + '/patients/<patient_id>/priority')
    def dx_priority(patient_id):
        data = body(('priority', 'note', 'revision'))
        if type(data.get('priority')) is not int or data['priority'] not in range(4) or type(data.get('revision')) is not int or data['revision'] < 0 or not isinstance(data.get('note', ''), str) or len(data.get('note', '')) > 500:
            abort(422)
        with SessionLocal() as db:
            doctor = require_role(db, 'doctor')
            authorized_patient(db, doctor, patient_id, lock=True)
            old = db.get(PhysicianPriority, (doctor.id, patient_id))
            if not old:
                if data['revision'] != 0:
                    return error(409, 'CONFLICT', 'Приоритет изменился; обновите страницу')
                from sqlalchemy.exc import IntegrityError
                try:
                    with db.begin_nested():
                        db.add(PhysicianPriority(doctor_id=doctor.id, patient_id=patient_id, priority=data['priority'],
                            note=data.get('note', '').strip(), revision=1, updated_at=stamp()))
                        db.flush()
                except IntegrityError:
                    return error(409, 'CONFLICT', 'Приоритет изменился; обновите страницу')
                revision = 1
            else:
                changed = db.execute(update(PhysicianPriority).where(PhysicianPriority.doctor_id == doctor.id,
                    PhysicianPriority.patient_id == patient_id, PhysicianPriority.revision == data['revision'])
                    .values(priority=data['priority'], note=data.get('note', '').strip(), revision=data['revision'] + 1, updated_at=stamp()))
                if changed.rowcount != 1:
                    return error(409, 'CONFLICT', 'Приоритет изменился; обновите страницу')
                revision = data['revision'] + 1
            audit(db, doctor, 'physician_priority_changed', 'physician_priority', patient_id)
            db.commit()
            return dict(patient_id=patient_id, physician_priority=data['priority'], priority_note=data.get('note', '').strip(), priority_revision=revision)

    @app.post(BASE + '/signals/<signal_id>/review')
    def dx_review(signal_id):
        data = body(('status', 'assessment'))
        if data.get('status') not in ('acknowledged', 'closed') or not isinstance(data.get('assessment'), str) or not 1 <= len(data['assessment'].strip()) <= 2000:
            abort(422)
        with SessionLocal() as db:
            doctor = require_role(db, 'doctor')
            row, person = scoped_signal(db, doctor, signal_id, lock=True)
            review = DoctorSignalReview(id='dxr_' + uuid.uuid4().hex, signal_id=row.id, doctor_id=doctor.id,
                status=data['status'], assessment=data['assessment'].strip(), created_at=stamp())
            db.add(review)
            row.status = data['status']
            audit(db, doctor, 'doctor_signal_reviewed', 'doctor_signal', row.id)
            db.commit()
            return dict(signal_payload(row, person.display_name), review_id=review.id)
