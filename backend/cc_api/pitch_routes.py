"""Authorized guided pitch: derive progress from actual writes; never perform them."""
import json
import uuid
from datetime import datetime
from flask import abort, request
from sqlalchemy import select, update
from werkzeug.exceptions import HTTPException
from .models import User, DoctorPatientLink
from .extension_models import Audit
from .doctor_access import authorized_patient
from .doctor_experience_models import DoctorSignal
from .patient_experience_models import MetricObservation
from .clinical_workflow_models import ClinicalDocument
from .clinical_workflow_services import released_documents
from .p0_models import ClinicalDecision
from .pitch_models import PitchRun, PitchEscalationConfig, PitchEscalationSimulation
from .verification import synthetic_enabled

BASE = '/api/v1/pitch'
LIMITATION = 'Пошаговая работа с синтетическими данными. Симуляция эскалации не отправляет уведомления и не задаёт клинический регламент, получателей или круглосуточную поддержку.'


def after(value, start):
    return bool(value) and datetime.fromisoformat(value.replace('Z', '+00:00')) >= datetime.fromisoformat(start.replace('Z', '+00:00'))


def register_pitch_routes(app, SessionLocal, current_user, require_role, error, utc_now):
    def actor(db):
        if not synthetic_enabled(app.config):
            abort(404)
        user = current_user(db)
        if not user:
            abort(401)
        if user.role not in ('doctor', 'patient'):
            abort(403)
        return user

    def participant(db, doctor, pid, lock=False):
        person = None
        for scope in ('diagnosis', 'medications', 'symptoms'):
            person = authorized_patient(db, doctor, pid, scope, lock=lock)
        return person

    def run_access(db, user, rid, lock=False):
        # Select participant metadata before selecting any clinical content.
        row = db.get(PitchRun, rid)
        if not row or user.id not in (row.doctor_id, row.patient_user_id):
            abort(404)
        doctor, patient = db.get(User, row.doctor_id), db.get(User, row.patient_user_id)
        if not doctor or not patient or doctor.organization_id != patient.organization_id:
            abort(404)
        participant(db, doctor, patient.patient_id, lock)
        return row, doctor, patient

    def run_dto(row, doctor, patient):
        return dict(id=row.id, patient_id=patient.patient_id, patient_name=patient.display_name,
                    doctor_name=doctor.display_name, started_at=row.started_at)

    def signal_access(db, user, sid, lock=False):
        if user.role != 'doctor':
            abort(403)
        meta = db.execute(select(DoctorSignal.doctor_id, DoctorSignal.patient_id).where(DoctorSignal.id == sid, DoctorSignal.source != 'consented_intake_safety')).first()
        if not meta or meta.doctor_id != user.id:
            abort(404)
        # The full pitch requires all three independently granted scopes.
        participant(db, user, meta.patient_id, lock)
        return db.get(DoctorSignal, sid)

    def config_dto(row):
        return dict(signal_id=row.signal_id, delay_seconds=row.delay_seconds, target_label=row.target_label, revision=row.revision)

    @app.get(BASE + '/capabilities')
    def pitch_capabilities():
        return {'enabled': synthetic_enabled(app.config)}

    @app.get(BASE + '/runs')
    def pitch_runs():
        with SessionLocal() as db:
            user = actor(db)
            query = select(PitchRun.id).where((PitchRun.doctor_id == user.id) | (PitchRun.patient_user_id == user.id))
            runs = []
            for rid in db.scalars(query.order_by(PitchRun.started_at.desc()).limit(50)):
                try:
                    row, doctor, patient = run_access(db, user, rid)
                    runs.append(run_dto(row, doctor, patient))
                except HTTPException as exc:
                    if exc.code != 404:
                        raise
            patients = []
            if user.role == 'doctor':
                ids = set(db.scalars(select(DoctorPatientLink.patient_id).where(DoctorPatientLink.doctor_id == user.id)))
                for pid in sorted(ids):
                    try:
                        patient = participant(db, user, pid)
                        patients.append(dict(id=pid, name=patient.display_name))
                    except HTTPException as exc:
                        if exc.code != 404:
                            raise
            return dict(items=runs, patients=patients, limitation=LIMITATION)

    @app.post(BASE + '/runs')
    def pitch_start():
        body = request.get_json(silent=True) or {}
        with SessionLocal.begin() as db:
            user = actor(db)
            if user.role != 'doctor':
                abort(403)
            pid = body.get('patient_id')
            if not isinstance(pid, str):
                abort(422)
            patient = participant(db, user, pid, True)
            row = PitchRun(id='pitch_' + uuid.uuid4().hex, doctor_id=user.id,
                           patient_user_id=patient.id, started_at=utc_now())
            db.add(row)
            db.add(Audit(id=uuid.uuid4().hex, actor=user.id, action='pitch_started', object_type='pitch', object_id=row.id, created_at=row.started_at))
            return run_dto(row, user, patient), 201

    @app.get(BASE + '/runs/<run_id>/progress')
    def pitch_progress(run_id):
        with SessionLocal() as db:
            user = actor(db)
            run, doctor, patient = run_access(db, user, run_id)
            observations = db.scalars(select(MetricObservation).where(MetricObservation.patient_id == patient.patient_id,
                MetricObservation.metric_key == 'wellbeing', MetricObservation.unit == 'points', MetricObservation.scale_version == 'mood_1_5_v1')).all()
            published = released_documents(db, patient, doctor if user.role == 'doctor' else None)
            new_ids = {row.id for row in observations if after(row.recorded_at, run.started_at)}
            observation = bool(new_ids)
            publication = any(item['kind'] == 'treatment' and item['clinician_id'] == doctor.id
                              and after(item['published_at'], run.started_at) for item in published)
            signals, configs = [], []
            alert = review = decision = treatment = None
            if user.role == 'doctor':
                rows = db.scalars(select(DoctorSignal).where(DoctorSignal.doctor_id == doctor.id,
                    DoctorSignal.patient_id == patient.patient_id, DoctorSignal.source != 'consented_intake_safety')).all()
                rows = [row for row in rows if after(row.created_at, run.started_at)
                    and row.source == 'wellbeing_observation' and new_ids.intersection(
                        point['id'] for point in json.loads(row.evidence_json).get('observations', []))]
                signals = [dict(id=row.id, reason=row.reason, occurred_at=row.occurred_at) for row in rows]
                alert = bool(rows)
                review = bool(db.scalar(select(Audit.id).where(Audit.actor == doctor.id,
                    Audit.action == 'pitch_chart_reviewed', Audit.object_id == run.id)))
                decision = any(after(value, run.started_at) for value in db.scalars(select(ClinicalDecision.confirmed_at)
                    .where(ClinicalDecision.patient_id == patient.patient_id, ClinicalDecision.clinician_id == doctor.id)))
                treatment = any(after(value, run.started_at) for value in db.scalars(select(ClinicalDocument.created_at)
                    .where(ClinicalDocument.patient_id == patient.patient_id, ClinicalDocument.clinician_id == doctor.id,
                           ClinicalDocument.kind == 'treatment')))
                for signal in rows:
                    config = db.get(PitchEscalationConfig, (doctor.id, signal.id))
                    configs.append(config_dto(config) if config else dict(signal_id=signal.id, delay_seconds=None, target_label=None, revision=0))
            steps = [dict(key=k, label=label, role=role, href=href if role == user.role else None, done=done)
                for k, label, role, href, done in (
                    ('observation', 'Пациент сохраняет новое наблюдение', 'patient', '/patient', observation),
                    ('alert', 'Врач рассматривает объяснимый сигнал', 'doctor', '/doctor', alert),
                    ('chart_review', 'Врач изучает карту пациента', 'doctor', '/doctor/patients/' + patient.patient_id, review),
                    ('decision', 'Врач явно сохраняет своё решение', 'doctor', '/doctor/patients/' + patient.patient_id + '/decisions', decision),
                    ('treatment', 'Врач создаёт план лечения', 'doctor', '/doctor/patients/' + patient.patient_id + '/treatment', treatment),
                    ('publication', 'Подписанный план явно опубликован пациенту', 'patient', '/patient/treatment', publication))]
            return dict(run=run_dto(run, doctor, patient), steps=steps, signals=signals, escalations=configs, limitation=LIMITATION)

    @app.post(BASE + '/runs/<run_id>/chart-review')
    def pitch_review(run_id):
        with SessionLocal.begin() as db:
            user = actor(db)
            if user.role != 'doctor':
                abort(403)
            run, _, _ = run_access(db, user, run_id, True)
            db.add(Audit(id=uuid.uuid4().hex, actor=user.id, action='pitch_chart_reviewed', object_type='pitch', object_id=run.id, created_at=utc_now()))
            return {'reviewed': True}

    @app.put(BASE + '/signals/<signal_id>/escalation')
    def pitch_escalation(signal_id):
        body = request.get_json(silent=True) or {}
        delay, target, revision = body.get('delay_seconds'), body.get('target_label'), body.get('revision')
        if (type(revision) is not int or revision < 0 or (delay is not None and (type(delay) is not int or not 0 <= delay <= 604800))
                or (target is not None and (not isinstance(target, str) or not 1 <= len(target.strip()) <= 120))):
            abort(422)
        with SessionLocal.begin() as db:
            user = actor(db)
            signal_access(db, user, signal_id, True)
            row = db.get(PitchEscalationConfig, (user.id, signal_id), populate_existing=True)
            if (row.revision if row else 0) != revision:
                abort(409)
            values = dict(delay_seconds=delay, target_label=target.strip() if target else None, revision=revision + 1, updated_at=utc_now())
            if row:
                result = db.execute(update(PitchEscalationConfig).where(PitchEscalationConfig.doctor_id == user.id,
                    PitchEscalationConfig.signal_id == signal_id, PitchEscalationConfig.revision == revision).values(**values))
                if result.rowcount != 1:
                    abort(409)
                db.refresh(row)
            else:
                row = PitchEscalationConfig(doctor_id=user.id, signal_id=signal_id, **values)
                db.add(row)
            return config_dto(row)

    @app.post(BASE + '/signals/<signal_id>/simulate')
    def pitch_simulate(signal_id):
        body = request.get_json(silent=True) or {}
        with SessionLocal.begin() as db:
            user = actor(db)
            signal_access(db, user, signal_id, True)
            row = db.get(PitchEscalationConfig, (user.id, signal_id), populate_existing=True)
            if not row or body.get('explicit_demo') is not True or type(body.get('revision')) is not int or row.revision != body['revision']:
                abort(409)
            if row.delay_seconds is None or not row.target_label:
                return error(422, 'DEMO_CONFIG_REQUIRED', 'Явно задайте условный интервал и получателя; это не клинический регламент')
            now = utc_now()
            db.add(PitchEscalationSimulation(id=uuid.uuid4().hex, doctor_id=user.id, signal_id=signal_id,
                config_revision=row.revision, config_json=json.dumps(config_dto(row), ensure_ascii=False), created_at=now))
            return {'simulated': True, 'delivered': False, 'created_at': now}
