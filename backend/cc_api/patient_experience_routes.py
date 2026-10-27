"""Synthetic-dev, authenticated and scoped patient experience APIs."""
import json
import math
import uuid
from datetime import datetime, timezone
from flask import abort, request
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .models import User, Patient, DoctorPatientLink, Checkin
from .extension_models import Appointment, PrevisitCase
from .p0_models import CarePlan, PlanItem
from .onboarding_models import PatientInvitation, PatientConsent, PreparedOnboardingDraft, LocalIdentity
from .patient_experience_models import (MetricObservation, DemoQuestionnaireDefinition,
    DemoQuestionnaireAssignment, DemoQuestionnaireDraft, DemoQuestionnaireSubmission, SyntheticPersona)
from .demo_questionnaires import METRICS, submission_payload, score_answers, validate_answers, EVALUATION_INSTRUMENTS, evaluation_definitions
from .verification import workspace_enabled

BASE = '/api/v1/patient-experience'


class SubmissionRace(Exception):
    pass


class ExperienceFailure(Exception):
    def __init__(self, status):
        self.status = status


def register_patient_experience_routes(app, SessionLocal, current_user, require_role, error, utc_now):
    @app.errorhandler(ExperienceFailure)
    def experience_error(exc):
        return error(exc.status, {409: 'CONFLICT', 422: 'INVALID_FIELDS'}[exc.status],
                     'Состояние изменилось; обновите страницу' if exc.status == 409 else 'Проверьте поля формы')

    @app.before_request
    def experience_guard():
        if request.path.startswith(BASE + '/') and request.path != BASE + '/capabilities' and not workspace_enabled(app.config):
            return error(403, 'SYNTHETIC_PROFILE_REQUIRED', 'Доступно только в synthetic_dev')

    def body(fields):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) - set(fields):
            raise ExperienceFailure(422)
        return data

    def auth(db):
        user = current_user(db)
        if not user:
            abort(401)
        return user

    def patient(db):
        user = require_role(db, 'patient')
        if not user.patient_id or not db.get(Patient, user.patient_id):
            abort(404)
        return user

    def doctor_access(db, doctor, patient_id):
        if doctor.role != 'doctor':
            abort(403)
        # Select grant metadata only before selecting any clinical record.
        person = db.scalar(select(User).where(User.patient_id == patient_id, User.role == 'patient', User.organization_id == doctor.organization_id))
        link = db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.patient_id == patient_id,
            DoctorPatientLink.doctor_id == doctor.id, (',' + DoctorPatientLink.categories + ',').contains(',symptoms,')))
        if not person or not link:
            abort(404)
        # New consent-ledger relationships must still have an active grant. Legacy links
        # without ledger rows retain their pre-existing consent representation.
        ledgers = db.scalars(select(PatientConsent).where(PatientConsent.patient_user_id == person.id, PatientConsent.doctor_id == doctor.id)).all()
        if ledgers and not any(c.revoked_at is None and 'symptoms' in c.categories.split(',') for c in ledgers):
            abort(404)
        return person

    def visible_assignment(db, aid, user, own_only=False):
        if user.role == 'patient':
            row = db.scalar(select(DemoQuestionnaireAssignment).where(DemoQuestionnaireAssignment.id == aid,
                DemoQuestionnaireAssignment.patient_id == user.patient_id))
        elif user.role == 'doctor' and not own_only:
            # Read patient reference metadata first; never select draft/result content before ACL.
            pid = db.scalar(select(DemoQuestionnaireAssignment.patient_id).where(DemoQuestionnaireAssignment.id == aid))
            if not pid:
                abort(404)
            doctor_access(db, user, pid)
            row = db.get(DemoQuestionnaireAssignment, aid)
        else:
            abort(403)
        if not row:
            abort(404)
        return row

    def assignment_payload(db, row):
        data = {k: getattr(row, k) for k in ('id', 'patient_id', 'definition_id', 'definition_version', 'status', 'created_at')}
        result = db.scalar(select(DemoQuestionnaireSubmission).where(DemoQuestionnaireSubmission.assignment_id == row.id))
        if result:
            data['total'] = result.score
        return data

    def assignments(db, user):
        if user.role == 'patient':
            rows = db.scalars(select(DemoQuestionnaireAssignment).where(DemoQuestionnaireAssignment.patient_id == user.patient_id).order_by(DemoQuestionnaireAssignment.created_at.desc())).all()
        elif user.role == 'doctor':
            allowed = []
            for pid in db.scalars(select(DoctorPatientLink.patient_id).where(DoctorPatientLink.doctor_id == user.id,
                    (',' + DoctorPatientLink.categories + ',').contains(',symptoms,'))).all():
                # Fail closed per row; no cross-tenant content selected.
                from werkzeug.exceptions import HTTPException
                try:
                    doctor_access(db, user, pid)
                    allowed.append(pid)
                except HTTPException:
                    continue
            rows = db.scalars(select(DemoQuestionnaireAssignment).where(DemoQuestionnaireAssignment.patient_id.in_(allowed)).order_by(DemoQuestionnaireAssignment.created_at.desc())).all()
        else:
            abort(403)
        return [assignment_payload(db, row) for row in rows]

    def timestamp(value):
        if not isinstance(value, str):
            raise ExperienceFailure(422)
        try:
            result = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if result.tzinfo is None or result.utcoffset() is None:
                raise ValueError()
            return result.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')
        except (ValueError, OverflowError):
            raise ExperienceFailure(422)

    def series(db, patient_id):
        grouped = {}
        def add(key, label, point, recorded_at):
            item = grouped.setdefault(key, {'metric_key': key[0], 'unit': key[1], 'scale_version': key[2], 'label': label, '_points': []})
            item['_points'].append((point, recorded_at))
        for row in db.scalars(select(MetricObservation).where(MetricObservation.patient_id == patient_id)).all():
            key = (row.metric_key, row.unit, row.scale_version)
            if key not in METRICS:
                continue
            add(key, METRICS[key][0], {'id': row.id, 'value': row.value, 'observed_at': timestamp(row.observed_at), 'source': row.source}, row.recorded_at)
        for row in db.scalars(select(Checkin).where(Checkin.patient_id == patient_id)).all():
            add(('wellbeing', 'points', 'mood_1_5_v1'), METRICS[('wellbeing', 'points', 'mood_1_5_v1')][0],
                {'id': row.id, 'value': row.mood_score, 'observed_at': timestamp(row.recorded_at), 'source': 'legacy_checkin'}, row.recorded_at)
        results = db.scalars(select(DemoQuestionnaireSubmission).join(DemoQuestionnaireAssignment,
            DemoQuestionnaireSubmission.assignment_id == DemoQuestionnaireAssignment.id).where(DemoQuestionnaireAssignment.patient_id == patient_id)).all()
        for row in results:
            definition = json.loads(row.definition_snapshot_json)
            add(('questionnaire_' + row.definition_id, 'points', row.definition_version), definition['title'],
                {'id': row.id, 'value': row.score, 'observed_at': timestamp(row.submitted_at), 'source': 'completed_questionnaire'}, row.submitted_at)
        output = []
        for key in sorted(grouped):
            item = grouped[key]
            raw = item.pop('_points')
            by_time = {}
            for point, recorded in sorted(raw, key=lambda x: (timestamp(x[1]), x[0]['id'])):
                by_time[point['observed_at']] = point
            item['points'] = sorted(by_time.values(), key=lambda p: p['observed_at'])
            item['point_count'] = len(item['points'])
            item['duplicate_count'] = len(raw) - len(item['points'])
            output.append(item)
        return output

    def published_notes(db, person, doctor=None):
        query = (select(PreparedOnboardingDraft, User.display_name)
            .join(PatientInvitation, PatientInvitation.id == PreparedOnboardingDraft.invitation_id)
            .join(PatientConsent, (PatientConsent.invitation_id == PatientInvitation.id) & (PatientConsent.doctor_id == PreparedOnboardingDraft.clinician_id))
            .join(User, User.id == PreparedOnboardingDraft.clinician_id)
            .join(DoctorPatientLink, (DoctorPatientLink.doctor_id == User.id) & (DoctorPatientLink.patient_id == person.patient_id))
            .where(PreparedOnboardingDraft.state == 'published', PreparedOnboardingDraft.signed_at.is_not(None),
                PreparedOnboardingDraft.published_at.is_not(None), PatientInvitation.status == 'accepted',
                PatientInvitation.patient_user_id == person.id, PatientInvitation.issuer_id == PreparedOnboardingDraft.clinician_id,
                PatientInvitation.organization_id == person.organization_id, PatientConsent.patient_user_id == person.id,
                PatientConsent.revoked_at.is_(None), (',' + PatientConsent.categories + ',').contains(',symptoms,'),
                (',' + DoctorPatientLink.categories + ',').contains(',symptoms,'), User.role == 'doctor',
                User.organization_id == person.organization_id))
        if doctor:
            query = query.where(PreparedOnboardingDraft.clinician_id == doctor.id)
        return [{'id': r.id, 'content': r.content, 'clinician_name': name, 'published_at': r.published_at,
            'signed_at': r.signed_at, 'version': r.version, 'source': 'published_clinician_note'}
            for r, name in db.execute(query.order_by(PreparedOnboardingDraft.published_at.desc())).all()]

    def chart(db, person, doctor=None):
        from .clinical_workflow_services import released_documents
        documents = released_documents(db, person, doctor)
        data_series = series(db, person.patient_id)
        submitted = db.scalars(select(DemoQuestionnaireSubmission).join(DemoQuestionnaireAssignment,
            DemoQuestionnaireAssignment.id == DemoQuestionnaireSubmission.assignment_id)
            .where(DemoQuestionnaireAssignment.patient_id == person.patient_id).order_by(DemoQuestionnaireSubmission.submitted_at.desc())).all()
        results = [submission_payload(r) for r in submitted]
        notes = published_notes(db, person, doctor)
        observations = [dict(p, metric_key=s['metric_key'], unit=s['unit'], scale_version=s['scale_version'], label=s['label'])
            for s in data_series for p in s['points'] if p['source'] != 'completed_questionnaire']
        timeline = [{'kind': 'observation', 'title': p['label'], 'occurred_at': p['observed_at'], 'source': p['source'], 'value': p['value'], 'unit': p['unit']} for p in observations]
        timeline += [{'kind': 'questionnaire', 'title': r['definition_id'], 'occurred_at': r['submitted_at'], 'source': 'completed_questionnaire', 'score': r['score'], 'assignment_id': r['assignment_id']} for r in results]
        timeline += [{'kind': 'published_note', 'title': 'Опубликованная запись специалиста', 'occurred_at': n['published_at'], 'source': n['source'], 'content': n['content']} for n in notes]
        timeline += [{'kind': 'clinical_document', 'title': 'Опубликованный план' if d['kind'] == 'treatment' else 'Опубликованная консультация',
                      'occurred_at': d['published_at'], 'source': 'signed_released_document', 'document_id': d['id']} for d in documents]
        return {'patient': {'display_name': person.display_name, 'synthetic': True}, 'series': data_series,
            'sections': [{'kind': 'observations', 'title': 'Собственные наблюдения', 'items': observations},
                         {'kind': 'questionnaires', 'title': 'Завершённые демонстрационные опросники', 'items': results},
                         {'kind': 'published_notes', 'title': 'Опубликованные записи', 'items': notes},
                         {'kind': 'clinical_documents', 'title': 'Консультации и планы', 'items': documents}],
            'timeline': sorted(timeline, key=lambda e: e['occurred_at'], reverse=True)}

    @app.get(BASE + '/capabilities')
    def px_capabilities():
        enabled = workspace_enabled(app.config)
        return {'enabled': enabled, 'personas_enabled': enabled and bool(app.config.get('SEED_PATIENT_PERSONAS'))}

    @app.get(BASE + '/personas')
    def px_personas():
        if not app.config.get('SEED_PATIENT_PERSONAS'):
            abort(403)
        with SessionLocal() as db:
            rows = db.execute(select(SyntheticPersona, User, LocalIdentity).join(User, User.id == SyntheticPersona.user_id).join(LocalIdentity, LocalIdentity.user_id == User.id).order_by(SyntheticPersona.persona_key)).all()
            return {'items': [{'persona_key': p.persona_key, 'email': i.email, 'display_name': u.display_name, 'description': p.description, 'state': p.state} for p, u, i in rows]}

    @app.get(BASE + '/observations')
    def px_observations():
        with SessionLocal() as db:
            user = patient(db)
            return {'series': series(db, user.patient_id)}

    @app.post(BASE + '/observations')
    def px_observation_create():
        data = body(('metric_key', 'unit', 'scale_version', 'value', 'observed_at', 'event_key'))
        key = tuple(data.get(k) for k in ('metric_key', 'unit', 'scale_version'))
        if any(not isinstance(v, str) for v in key) or key not in METRICS:
            raise ExperienceFailure(422)
        value = data.get('value')
        if type(value) not in (int, float) or not METRICS[key][1] <= value <= METRICS[key][2] or not math.isfinite(value):
            raise ExperienceFailure(422)
        event = data.get('event_key')
        if not isinstance(event, str) or not 1 <= len(event.strip()) <= 80:
            raise ExperienceFailure(422)
        observed = timestamp(data['observed_at']) if 'observed_at' in data else None
        if observed and datetime.fromisoformat(observed.replace('Z', '+00:00')) > datetime.now(timezone.utc):
            raise ExperienceFailure(422)
        def dto(row):
            return {k: getattr(row, k) for k in ('id', 'metric_key', 'unit', 'scale_version', 'value', 'observed_at', 'source', 'event_key')}
        def replay(row):
            if (row.metric_key, row.unit, row.scale_version) != key or row.value != value or (observed is not None and timestamp(row.observed_at) != observed):
                raise ExperienceFailure(409)
            return dto(row)
        try:
            with SessionLocal.begin() as db:
                user = patient(db)
                old = db.scalar(select(MetricObservation).where(MetricObservation.patient_id == user.patient_id, MetricObservation.event_key == event))
                if old:
                    return replay(old), 200
                row = MetricObservation(id='obs_' + uuid.uuid4().hex, patient_id=user.patient_id,
                    metric_key=key[0], unit=key[1], scale_version=key[2], value=value,
                    observed_at=observed or timestamp(utc_now()), recorded_at=timestamp(utc_now()), source='patient_report', event_key=event)
                db.add(row)
                db.flush()
                result = dto(row)
            return result, 201
        except IntegrityError:
            with SessionLocal() as db:
                user = patient(db)
                old = db.scalar(select(MetricObservation).where(MetricObservation.patient_id == user.patient_id, MetricObservation.event_key == event))
                if old:
                    return replay(old), 200
            raise ExperienceFailure(409)

    @app.get(BASE + '/dashboard')
    def px_dashboard():
        with SessionLocal() as db:
            user = patient(db)
            data_series = series(db, user.patient_id)
            links = db.execute(select(User, DoctorPatientLink).join(DoctorPatientLink, DoctorPatientLink.doctor_id == User.id)
                .where(DoctorPatientLink.patient_id == user.patient_id, User.organization_id == user.organization_id, User.role == 'doctor')).all()
            plans = db.scalars(select(CarePlan).where(CarePlan.patient_id == user.patient_id, CarePlan.status == 'active')).all()
            from .released_plan_access import plan_visible
            plans = [p for p in plans if plan_visible(db, user, p)]
            plan_items = [{'id': p.id, 'status': p.status, 'items': [{'id': i.id, 'title': i.title, 'item_type': i.item_type, 'frequency': i.frequency} for i in db.scalars(select(PlanItem).where(PlanItem.plan_id == p.id)).all()]} for p in plans]
            visits = db.scalars(select(Appointment).where(Appointment.patient_user_id == user.id, Appointment.proposed_at > utc_now(), Appointment.status.in_(['offered', 'confirmed']))).all()
            history = any(s['point_count'] for s in data_series) or bool(published_notes(db, user)) or bool(plans)
            return {'patient': {'display_name': user.display_name, 'synthetic': True}, 'state': 'history' if history else ('invited' if links else 'empty'),
                'series': data_series, 'assignments': assignments(db, user), 'links': [{'id': d.id, 'display_name': d.display_name, 'specialty': d.specialty} for d, _ in links],
                'plans': plan_items, 'appointments': [{k: getattr(v, k) for k in ('id', 'proposed_at', 'format', 'status')} for v in visits],
                'published_notes': published_notes(db, user), 'case_count': len(db.scalars(select(PrevisitCase.id).where(PrevisitCase.patient_user_id == user.id)).all())}

    @app.get(BASE + '/chart')
    def px_chart():
        with SessionLocal() as db:
            return chart(db, patient(db))

    @app.get(BASE + '/physician/patients/<patient_id>/chart')
    def px_physician_chart(patient_id):
        with SessionLocal() as db:
            doctor = require_role(db, 'doctor')
            return chart(db, doctor_access(db, doctor, patient_id), doctor)

    @app.get('/api/v1/evaluation/questionnaires/public-definitions')
    def px_public_evaluation_definitions():
        # Anonymous evaluation is intentionally read-only. No participant answers,
        # identifiers or scores are sent to the server until authenticated consent.
        if not app.config.get('DEMO_MODE') or app.config.get('APP_ENV') not in ('synthetic_dev', 'evaluation_sandbox'):
            abort(404)
        if app.config.get('APP_ENV') == 'evaluation_sandbox' and not app.config.get('EVALUATION_ACKNOWLEDGED'):
            abort(404)
        response = {'items': evaluation_definitions(), 'synthetic_only': True,
                    'clinical_release': False, 'storage': 'session_only_until_login'}
        from flask import make_response
        out = make_response(response)
        out.headers['Cache-Control'] = 'no-store'
        return out

    @app.get(BASE + '/questionnaires/definitions')
    def px_definitions():
        with SessionLocal() as db:
            user = auth(db)
            if user.role not in ('patient', 'doctor'):
                abort(403)
            return {'items': [json.loads(r.definition_json) for r in db.scalars(select(DemoQuestionnaireDefinition).order_by(DemoQuestionnaireDefinition.id)).all()]}

    @app.get(BASE + '/questionnaires/assignments')
    def px_assignments():
        with SessionLocal() as db:
            return {'items': assignments(db, auth(db))}

    @app.post(BASE + '/questionnaires/assignments')
    def px_assign():
        data = body(('patient_id', 'definition_id'))
        if not all(isinstance(data.get(k), str) for k in ('patient_id', 'definition_id')):
            raise ExperienceFailure(422)
        with SessionLocal.begin() as db:
            doctor = require_role(db, 'doctor')
            doctor_access(db, doctor, data['patient_id'])
            definition = db.get(DemoQuestionnaireDefinition, data['definition_id'])
            if not definition:
                raise ExperienceFailure(422)
            row = DemoQuestionnaireAssignment(id='dq_' + uuid.uuid4().hex, patient_id=data['patient_id'], clinician_id=doctor.id,
                definition_id=definition.id, definition_version=definition.version, status='assigned', created_at=utc_now())
            db.add(row)
            db.flush()
            db.add(DemoQuestionnaireDraft(assignment_id=row.id, answers_json='{}', last_page=0, revision=0, updated_at=utc_now()))
            result = assignment_payload(db, row)
        return result, 201

    def draft_payload(db, row):
        definition = db.get(DemoQuestionnaireDefinition, row.definition_id)
        draft = db.get(DemoQuestionnaireDraft, row.id)
        return {'assignment': assignment_payload(db, row), 'definition': json.loads(definition.definition_json),
            'draft': {'answers': json.loads(draft.answers_json), 'last_page': draft.last_page, 'revision': draft.revision, 'updated_at': draft.updated_at}}

    @app.post(BASE + '/questionnaires/self-assign')
    def px_self_assign():
        # Only this explicit allowlist is permitted for synthetic test accounts.
        data = body(('definition_id', 'idempotency_key'))
        key = data.get('idempotency_key')
        if key is not None and (not isinstance(key, str) or not 1 <= len(key.strip()) <= 80):
            raise ExperienceFailure(422)
        allowed = {'eval_' + code + '_v1' for code in EVALUATION_INSTRUMENTS}
        if data.get('definition_id') not in allowed:
            raise ExperienceFailure(422)
        with SessionLocal.begin() as db:
            user = patient(db)
            definition = db.get(DemoQuestionnaireDefinition, data['definition_id'])
            if definition is None or definition.status != 'evaluation_draft_unapproved':
                raise ExperienceFailure(422)
            # A guest's submit may have committed before its response was lost.
            # Recover only that patient's exact completed transfer; never use
            # matching scores/answers as identity or disclose another account.
            if key is not None:
                completed = db.scalar(select(DemoQuestionnaireAssignment).join(
                    DemoQuestionnaireSubmission,
                    DemoQuestionnaireSubmission.assignment_id == DemoQuestionnaireAssignment.id).where(
                    DemoQuestionnaireAssignment.patient_id == user.patient_id,
                    DemoQuestionnaireAssignment.definition_id == definition.id,
                    DemoQuestionnaireSubmission.idempotency_key == key))
                if completed:
                    return assignment_payload(db, completed), 200
            # Return the pending assignment when clicked again; submitted ones
            # remain immutable and a new assessment is a new explicit action.
            existing = db.scalar(select(DemoQuestionnaireAssignment).where(
                DemoQuestionnaireAssignment.patient_id == user.patient_id,
                DemoQuestionnaireAssignment.definition_id == definition.id,
                DemoQuestionnaireAssignment.status == 'assigned').order_by(DemoQuestionnaireAssignment.created_at.desc()))
            if existing:
                return assignment_payload(db, existing), 200
            row = DemoQuestionnaireAssignment(id='dq_' + uuid.uuid4().hex, patient_id=user.patient_id,
                clinician_id=user.id, definition_id=definition.id, definition_version=definition.version,
                status='assigned', created_at=utc_now())
            db.add(row)
            db.flush()
            db.add(DemoQuestionnaireDraft(assignment_id=row.id, answers_json='{}', last_page=0, revision=0, updated_at=utc_now()))
            result = assignment_payload(db, row)
        return result, 201

    @app.get(BASE + '/questionnaires/assignments/<assignment_id>')
    def px_assignment(assignment_id):
        with SessionLocal() as db:
            user = patient(db)
            return draft_payload(db, visible_assignment(db, assignment_id, user, True))

    @app.put(BASE + '/questionnaires/assignments/<assignment_id>/draft')
    def px_draft(assignment_id):
        data = body(('definition_version', 'revision', 'answers', 'last_page'))
        if type(data.get('revision')) is not int or data['revision'] < 0 or type(data.get('last_page')) is not int:
            raise ExperienceFailure(422)
        answers = data.get('answers', {})
        if not isinstance(answers, dict):
            raise ExperienceFailure(422)
        with SessionLocal.begin() as db:
            user = patient(db)
            row = visible_assignment(db, assignment_id, user, True)
            definition = db.get(DemoQuestionnaireDefinition, row.definition_id)
            payload = json.loads(definition.definition_json)
            if data.get('definition_version') != row.definition_version or not 0 <= data['last_page'] < len(payload['pages']):
                raise ExperienceFailure(422)
            try:
                validate_answers(payload, answers)
            except ValueError:
                raise ExperienceFailure(422)
            if row.status != 'assigned':
                raise ExperienceFailure(409)
            draft = db.get(DemoQuestionnaireDraft, row.id)
            if draft.revision != data['revision']:
                raise ExperienceFailure(409)
            merged = dict(json.loads(draft.answers_json), **answers)
            # Assignment write serializes draft versus submit even when their read snapshots race.
            locked = db.execute(update(DemoQuestionnaireAssignment).where(DemoQuestionnaireAssignment.id == row.id,
                DemoQuestionnaireAssignment.status == 'assigned').values(status='assigned')).rowcount
            updated = db.execute(update(DemoQuestionnaireDraft).where(DemoQuestionnaireDraft.assignment_id == row.id,
                DemoQuestionnaireDraft.revision == data['revision']).values(answers_json=json.dumps(merged, ensure_ascii=False),
                    last_page=data['last_page'], revision=data['revision'] + 1, updated_at=utc_now())).rowcount
            if not locked or not updated:
                raise ExperienceFailure(409)
            db.expire_all()
            result = draft_payload(db, db.get(DemoQuestionnaireAssignment, row.id))
        return result

    @app.post(BASE + '/questionnaires/assignments/<assignment_id>/submit')
    def px_submit(assignment_id):
        data = body(('definition_version', 'revision', 'idempotency_key'))
        key = data.get('idempotency_key')
        if type(data.get('revision')) is not int or data['revision'] < 0 or not isinstance(key, str) or not 1 <= len(key.strip()) <= 80:
            raise ExperienceFailure(422)
        try:
            with SessionLocal.begin() as db:
                user = patient(db)
                row = visible_assignment(db, assignment_id, user, True)
                if data.get('definition_version') != row.definition_version:
                    raise ExperienceFailure(422)
                old = db.scalar(select(DemoQuestionnaireSubmission).where(DemoQuestionnaireSubmission.assignment_id == row.id))
                if old:
                    if old.idempotency_key != key:
                        raise ExperienceFailure(409)
                    return submission_payload(old), 200
                if row.status != 'assigned':
                    raise SubmissionRace()
                draft = db.get(DemoQuestionnaireDraft, row.id)
                if draft.revision != data['revision']:
                    raise SubmissionRace()
                definition = db.get(DemoQuestionnaireDefinition, row.definition_id)
                snapshot = json.loads(definition.definition_json)
                answers = json.loads(draft.answers_json)
                try:
                    score = score_answers(snapshot, answers)
                except ValueError:
                    raise ExperienceFailure(422)
                locked = db.execute(update(DemoQuestionnaireAssignment).where(DemoQuestionnaireAssignment.id == row.id,
                    DemoQuestionnaireAssignment.status == 'assigned').values(status='submitted')).rowcount
                updated = db.execute(update(DemoQuestionnaireDraft).where(DemoQuestionnaireDraft.assignment_id == row.id,
                    DemoQuestionnaireDraft.revision == data['revision']).values(revision=data['revision'] + 1)).rowcount
                if not locked or not updated:
                    raise SubmissionRace()
                result = DemoQuestionnaireSubmission(id='ds_' + uuid.uuid4().hex, assignment_id=row.id, definition_id=row.definition_id,
                    definition_version=row.definition_version, definition_snapshot_json=definition.definition_json, answers_json=draft.answers_json,
                    score=score, submitted_at=utc_now(), idempotency_key=key)
                db.add(result)
                db.flush()
                from .clinical_review_services import event_notice
                event_notice(db,user.id,'questionnaire','Сохранён результат демонстрационного опросника','questionnaire',row.id)
                output = submission_payload(result)
            return output, 201
        except (IntegrityError, SubmissionRace):
            # Unique assignment result makes concurrent exact retries deterministic.
            with SessionLocal() as db:
                user = patient(db)
                row = visible_assignment(db, assignment_id, user, True)
                old = db.scalar(select(DemoQuestionnaireSubmission).where(DemoQuestionnaireSubmission.assignment_id == row.id))
                if old and old.idempotency_key == key:
                    return submission_payload(old), 200
            raise ExperienceFailure(409)

    @app.get(BASE + '/questionnaires/assignments/<assignment_id>/result')
    def px_result(assignment_id):
        with SessionLocal() as db:
            row = visible_assignment(db, assignment_id, auth(db))
            result = db.scalar(select(DemoQuestionnaireSubmission).where(DemoQuestionnaireSubmission.assignment_id == row.id))
            if not result:
                abort(404)
            return submission_payload(result)
