"""Original core API routes and request-scoped identity authorization.

The helper callbacks are returned for compatibility with existing additive
route registrars. This module intentionally retains the original endpoint
implementation, names, authorization behavior and registration order.
"""
from __future__ import annotations
import hashlib
import secrets
import uuid
from flask import abort, jsonify, request, session
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from .models import Alert, Checkin, DoctorPatientLink, Patient, User
from . import onboarding_models
from .identity import verified_subject, decode_identity_token, has_staff_assurance
from .utilities import utc_now, alert_dict
from .http_hooks import register_http_hooks


def register_core_routes(app, SessionLocal):
    def api_error(status: int, code: str, message: str):
        return jsonify({'error': {'code': code, 'message': message}, 'request_id': request.environ.get('cc.request_id', 'unknown')}), status

    def current_user(db: Session):
        if not app.config['DEMO_MODE'] or session.get('oidc_session'):
            try:
                # Explicit bearer authentication never falls back to a cookie,
                # including when an invalid bearer is supplied with a valid cookie.
                if request.headers.get('Authorization'):
                    header = request.headers['Authorization']
                    if not header.startswith('Bearer '):
                        return None
                    claims = decode_identity_token(header[7:])
                    user = db.scalar(select(User).where(User.external_subject == claims['sub']))
                    return user if user and (user.role == 'patient' or has_staff_assurance(claims)) else None
                from .oidc_browser import browser_user
                return browser_user(db)
            except Exception:
                return None
        if app.config['DEMO_MODE']:
            uid = session.get('uid')
            user = db.get(User, uid) if uid else None
            # Every synthetic-dev identity, including fixture clinicians, must
            # present a password-authenticated, unrevoked local session.
            from .verification import workspace_enabled
            if not workspace_enabled(app.config) or not user or (app.config.get('APP_ENV')=='evaluation_sandbox' and user.organization_id!=app.config.get('EVALUATION_TENANT')) or not db.get(onboarding_models.LocalIdentity, user.id):
                return None
            token = session.get('auth_session')
            auth_session = db.get(onboarding_models.LocalAuthSession, hashlib.sha256(token.encode()).hexdigest()) if isinstance(token, str) else None
            if (not auth_session or auth_session.user_id != user.id or auth_session.revoked_at
                    or auth_session.expires_at <= utc_now()):
                return None
            return user
        try:
            subject = verified_subject()
        except Exception:
            return None
        return db.scalar(select(User).where(User.external_subject == subject)) if subject else None

    def require_role(db, role):
        user = current_user(db)
        if not user:
            abort(401)
        if user.role != role:
            abort(403)
        return user

    def safe_row(patient, categories, alert_level):
        item = {
            'id': patient.id,
            'display_name': patient.display_name,
            'attention_level': alert_level,
            'attention_reason': None,  # Do not leak alarm reason to unauthorized roles.
            'trend': patient.trend if 'symptoms' in categories else 'insufficient_data',
            'last_activity_at': patient.last_activity_at if 'symptoms' in categories else None,
            'allowed_actions': ['view_overview']
        }
        if 'diagnosis' in categories:
            item['diagnosis_label'] = patient.diagnosis_label
        if 'medications' in categories:
            item['medication_label'] = patient.medication_label
        if 'severity' in categories:
            item['severity_label'] = patient.severity_label
        return item

    def doctor_links(db, doctor_id):
        output=[]
        from werkzeug.exceptions import HTTPException
        for pid in db.scalars(select(DoctorPatientLink.patient_id).where(DoctorPatientLink.doctor_id == doctor_id)).all():
            try:output.append(get_link(db,doctor_id,pid))
            except HTTPException:continue
        return output

    def get_link(db, doctor_id, patient_id):
        from types import SimpleNamespace
        from .doctor_access import authorized_scopes
        doctor=db.get(User,doctor_id)
        scopes=authorized_scopes(db,doctor,patient_id)
        return SimpleNamespace(patient_id=patient_id,categories=','.join(sorted(scopes)))
    register_http_hooks(app, api_error)

    @app.get('/api/v1/health')
    def health():
        return {'status': 'ok', 'service': 'clinical-compass-api'}

    @app.get('/api/v1/auth/me')
    def me():
        with SessionLocal() as db:
            user = current_user(db)
            if not user:
                abort(401)
            if (app.config['DEMO_MODE'] or session.get('oidc_session')) and 'csrf_token' not in session:
                session['csrf_token'] = secrets.token_urlsafe(24)
            return {
                'user': {'id': user.id, 'display_name': user.display_name, 'patient_id': user.patient_id},
                'context': {'role': user.role, 'specialty': user.specialty, 'organization_id': user.organization_id},
                'csrf_token': session.get('csrf_token') if app.config['DEMO_MODE'] or session.get('oidc_session') else None,
                'features': {'ai_chat_enabled': False, 'ai_summary_enabled': False, 'research_enabled': True,
                             'oidc_session': bool(session.get('oidc_session')),
                             'synthetic_onboarding_enabled': bool(app.config['DEMO_MODE'] and app.config['APP_ENV']=='synthetic_dev')},
                'synthetic_identity': 'synthetic_dev' if db.get(onboarding_models.LocalIdentity,user.id) else None,
            }

    @app.get('/api/v1/doctors/me/patients')
    def doctor_patients():
        with SessionLocal() as db:
            user = require_role(db, 'doctor')
            sort = request.args.get('sort', 'attention_desc')
            if sort not in ('attention_desc', 'name_asc', 'last_activity_desc'):
                return api_error(422, 'INVALID_SORT', 'Unsupported sort')
            q = request.args.get('q', '').strip().casefold()
            if len(q) > 100:
                return api_error(422, 'INVALID_SEARCH', 'Search too long')
            try:
                page = int(request.args.get('page', 1))
                per_page = int(request.args.get('per_page', 20))
            except ValueError:
                return api_error(422, 'INVALID_PAGINATION', 'Page must be integer')
            if page < 1 or not 1 <= per_page <= 100:
                return api_error(422, 'INVALID_PAGINATION', 'Out of range')
            rows = []
            for link in doctor_links(db, user.id):
                patient = db.get(Patient, link.patient_id)
                person = db.scalar(select(User).where(User.role == 'patient', User.patient_id == link.patient_id))
                if (not patient or not person or person.organization_id != user.organization_id
                        or q not in patient.display_name.casefold()):
                    continue
                categories = set(link.categories.split(','))
                # Only alerts explicitly assigned to this clinician affect attention ordering.
                level = 'unknown'
                if 'symptoms' in categories:
                    critical = db.scalar(select(Alert).where(Alert.assigned_doctor_id == user.id, Alert.patient_id == patient.id, Alert.severity == 'critical', Alert.status == 'open'))
                    high = db.scalar(select(Alert).where(Alert.assigned_doctor_id == user.id, Alert.patient_id == patient.id, Alert.severity == 'high', Alert.status == 'open'))
                    level = 'critical' if critical else ('high' if high else 'routine')
                rows.append(safe_row(patient, categories, level))
            priority = {'critical': 0, 'high': 1, 'routine': 2, 'unknown': 3}
            if sort == 'attention_desc':
                rows.sort(key=lambda item: (priority[item['attention_level']], item['display_name']))
            elif sort == 'name_asc':
                rows.sort(key=lambda item: item['display_name'])
            else:
                rows.sort(key=lambda item: item.get('last_activity_at') or '', reverse=True)
            total = len(rows)
            start = (page - 1) * per_page
            return {'items': rows[start:start + per_page], 'page': page, 'per_page': per_page,
                    'total': total, 'sort': sort, 'generated_at': utc_now()}

    @app.get('/api/v1/doctors/me/patients/<patient_id>/overview')
    def doctor_overview(patient_id):
        with SessionLocal() as db:
            user = require_role(db, 'doctor')
            link = get_link(db, user.id, patient_id)
            if not link:
                abort(404)
            person = db.scalar(select(User).where(User.role == 'patient', User.patient_id == patient_id))
            if not person or person.organization_id != user.organization_id:
                abort(404)
            patient = db.get(Patient, patient_id)
            if not patient:
                abort(404)
            categories = set(link.categories.split(','))
            sections = []
            if 'symptoms' in categories:
                observations = list(db.scalars(select(Checkin).where(Checkin.patient_id == patient_id).order_by(Checkin.recorded_at.desc()).limit(30)))
                sections.append({'key': 'trends', 'label': 'Динамика',
                                 'data': {'moods': [{'score': c.mood_score, 'recorded_at': c.recorded_at} for c in observations]}})
            if 'medications' in categories:
                sections.append({'key': 'medications', 'label': 'Медикаменты',
                                 'data': {'current': patient.medication_label}})
            if 'diagnosis' in categories:
                sections.append({'key': 'history', 'label': 'Анамнез', 'data': {'diagnosis_label': patient.diagnosis_label}})
            row = safe_row(patient, categories, 'routine')
            return {'patient': row, 'sections': sections, 'capabilities': ['read_overview'], 'generated_at': utc_now()}

    @app.get('/api/v1/doctors/me/alerts')
    def doctor_alerts():
        with SessionLocal() as db:
            user = require_role(db, 'doctor')
            q = (select(Alert).join(DoctorPatientLink,
                (DoctorPatientLink.patient_id == Alert.patient_id) & (DoctorPatientLink.doctor_id == user.id))
                .join(User, (User.patient_id == Alert.patient_id) & (User.role == 'patient') &
                      (User.organization_id == user.organization_id))
                .where(Alert.assigned_doctor_id == user.id, DoctorPatientLink.categories.contains('symptoms')))
            if request.args.get('status'):
                q = q.where(Alert.status == request.args['status'])
            alerts = list(db.scalars(q.order_by(Alert.created_at.desc())))
            return {'items': [alert_dict(a) for a in alerts]}

    @app.post('/api/v1/alerts/<alert_id>/acknowledge')
    def acknowledge(alert_id):
        with SessionLocal.begin() as db:
            user = require_role(db, 'doctor')
            alert = db.get(Alert, alert_id)
            if not alert or alert.assigned_doctor_id != user.id:
                abort(404)
            link = get_link(db, user.id, alert.patient_id)
            patient_account = db.scalar(select(User).where(User.patient_id == alert.patient_id,
                User.role == 'patient', User.organization_id == user.organization_id))
            if not link or not patient_account or 'symptoms' not in link.categories.split(','):
                abort(404)
            if alert.status != 'open':
                return api_error(409, 'ALREADY_HANDLED', 'Alert is not open')
            alert.status = 'acknowledged'
            alert.acknowledged_at = utc_now()
            # Production: write immutable audit_event in the same transaction.
            return alert_dict(alert)

    @app.post('/api/v1/patients/me/check-ins')
    def patient_checkin():
        payload = request.get_json(silent=True) or {}
        if set(payload) - {'mood_score', 'comparison', 'note', 'observed_at'}:
            return api_error(422, 'INVALID_FIELD', 'Unexpected field')
        score = payload.get('mood_score')
        comparison = payload.get('comparison')
        if type(score) is not int or not 1 <= score <= 5 or comparison not in ('better', 'same', 'worse', 'unsure'):
            return api_error(422, 'INVALID_CHECKIN', 'Mood must be 1..5; comparison invalid')
        note = payload.get('note', '')
        if not isinstance(note, str) or len(note) > 2000:
            return api_error(422, 'INVALID_NOTE', 'Invalid note')
        with SessionLocal.begin() as db:
            user = require_role(db, 'patient')
            if not user.patient_id:
                abort(403)
            new = Checkin(id='ck_' + uuid.uuid4().hex[:10], patient_id=user.patient_id,
                          mood_score=score, comparison=comparison, note=note, recorded_at=utc_now())
            db.add(new)
            # Production: add clinical rule evaluation + scoped notifications via outbox.
            return ({'id': new.id, 'mood_score': new.mood_score, 'comparison': new.comparison,
                     'recorded_at': new.recorded_at, 'source_type': 'patient_self_report'}, 201)

    return current_user, require_role, api_error
