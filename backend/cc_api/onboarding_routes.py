"""Persisted synthetic patient enrollment with explicit, recipient-bound consent."""
import base64
import hashlib
import hmac
import io
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from flask import abort, request, session
from sqlalchemy import select, update, exists
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .models import User, Patient, DoctorPatientLink
from .extension_models import Audit, Invitation
from .p0_models import UserNotification
from .onboarding_models import (LocalIdentity, OnboardingJourney, PatientOnboarding,
    PatientInvitation, PatientConsent, PreparedOnboardingDraft, StaffVerification, LocalAuthSession)
from .verification import (workspace_enabled, normalize_synthetic_email,
    SyntheticEmailVerifier, SyntheticProfessionalVerifier)

CATEGORIES = {'symptoms', 'diagnosis', 'medications', 'severity'}
CONSENT_VERSION = 'clinical-link-v1'


class OnboardingFailure(Exception):
    def __init__(self, status):
        self.status = status



def register_onboarding_routes(app, SessionLocal, current_user, require_role, error, utc_now):
    @app.errorhandler(OnboardingFailure)
    def onboarding_error(exc):
        codes = {409: ('CONFLICT', 'Состояние изменилось; обновите страницу'),
                 410: ('INVITATION_EXPIRED', 'Срок приглашения истёк'),
                 422: ('INVALID_FIELDS', 'Проверьте поля формы')}
        code, message = codes[exc.status]
        return error(exc.status, code, message)

    def uid():
        return uuid.uuid4().hex

    def digest(value):
        return hashlib.sha256(value.encode('utf-8')).hexdigest()

    def body(fields):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) - set(fields):
            raise OnboardingFailure(422)
        return data

    def text(data, key, low, high):
        value = data.get(key)
        if not isinstance(value, str) or not low <= len(value.strip()) <= high:
            raise OnboardingFailure(422)
        return value.strip()

    def version(data, field='version'):
        value = data.get(field)
        if type(value) is not int or value < 0:
            raise OnboardingFailure(422)
        return value

    def audit(db, user, action, object_id):
        db.add(Audit(id=uid(), actor=user.id, action=action, object_type='onboarding',
                     object_id=object_id, created_at=utc_now()))

    @app.before_request
    def onboarding_profile_guard():
        if request.path.startswith('/api/v1/onboarding/') and request.path != '/api/v1/onboarding/bootstrap':
            if not workspace_enabled(app.config):
                return error(403, 'SYNTHETIC_PROFILE_REQUIRED', 'Доступно только в synthetic_dev')

    def journey_payload(row):
        return {key: getattr(row, key) for key in
                ('id', 'doctor_id', 'subject', 'message', 'step', 'revision', 'updated_at')}

    def journey_for(db, user=None, create=True):
        jid = session.get('journey_id')
        row = db.get(OnboardingJourney, jid) if isinstance(jid, str) else None
        if row and row.owner_id != (user.id if user else None):
            row = None
        if row is None and user:
            row = db.scalar(select(OnboardingJourney).where(OnboardingJourney.owner_id == user.id)
                            .order_by(OnboardingJourney.updated_at.desc(), OnboardingJourney.id).limit(1))
        if row is None and create:
            row = OnboardingJourney(id=uid(), owner_id=user.id if user else None,
                doctor_id=None, subject='', message='', step='draft', revision=0, updated_at=utc_now())
            db.add(row)
            db.flush()
        if row:
            session['journey_id'] = row.id
        return row

    def adopt_journey(db, user):
        row = db.get(OnboardingJourney, session.get('journey_id')) if session.get('journey_id') else None
        if row and row.owner_id is None:
            if not (row.doctor_id or row.subject or row.message):
                existing = db.scalar(select(OnboardingJourney).where(OnboardingJourney.owner_id == user.id)
                    .order_by(OnboardingJourney.updated_at.desc(), OnboardingJourney.id).limit(1))
                if existing:
                    return existing
            # Prevent a selected doctor from silently crossing the registered tenant.
            doctor = db.get(User, row.doctor_id) if row.doctor_id else None
            if doctor and doctor.organization_id != user.organization_id:
                abort(403)
            claimed = db.execute(update(OnboardingJourney).where(OnboardingJourney.id == row.id,
                OnboardingJourney.owner_id.is_(None)).values(owner_id=user.id, updated_at=utc_now()))
            if claimed.rowcount != 1:
                raise OnboardingFailure(409)
            db.refresh(row)
            return row
        return journey_for(db, user)

    def state_for(db, user):
        row = db.get(PatientOnboarding, user.id)
        if row is None:
            row = PatientOnboarding(user_id=user.id, status='pending', introduction_seen=0,
                                    updated_at=utc_now())
            db.add(row)
            db.flush()
        return row

    def state_payload(db, user):
        row = state_for(db, user)
        return {'status': row.status, 'introduction_seen': bool(row.introduction_seen),
                'journey': journey_payload(journey_for(db, user))}

    def revoke_session(db):
        token = session.get('auth_session')
        if isinstance(token, str):
            db.execute(update(LocalAuthSession).where(LocalAuthSession.token_hash == digest(token),
                LocalAuthSession.revoked_at.is_(None)).values(revoked_at=utc_now()))

    def rotate(user, journey):
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat().replace('+00:00', 'Z')
        with SessionLocal.begin() as db:
            revoke_session(db)
            db.add(LocalAuthSession(token_hash=digest(token), user_id=user.id,
                expires_at=expires, revoked_at=None))
        session.clear()
        session['auth_session'] = token
        session['uid'] = user.id
        session['csrf_token'] = secrets.token_urlsafe(24)
        if journey is not None:
            session['journey_id'] = journey.id
        session['synthetic_identity'] = app.config.get('APP_ENV')=='synthetic_dev'

    def auth_context(db, user):
        return {'user': {'id': user.id, 'display_name': user.display_name, 'patient_id': user.patient_id},
            'context': {'role': user.role, 'specialty': user.specialty, 'organization_id': user.organization_id},
            'csrf_token': session['csrf_token'], 'synthetic_identity': app.config.get('APP_ENV'),
            'features': {'ai_chat_enabled': False, 'ai_summary_enabled': False, 'research_enabled': True,
                'synthetic_registration_enabled': workspace_enabled(app.config)},
            'onboarding': state_payload(db, user) if user.role == 'patient' else None}

    def invitation_for_token(db, token, pending=True):
        if not isinstance(token, str) or not 20 <= len(token) <= 200:
            abort(404)
        row = db.scalar(select(PatientInvitation).where(PatientInvitation.token_hash == digest(token)))
        if not row:
            abort(404)
        if row.status == 'revoked' or row.expires_at <= utc_now():
            abort(404)
        if pending and row.status != 'pending':
            raise OnboardingFailure(409)
        doctor = db.get(User, row.issuer_id)
        if not doctor or doctor.role != 'doctor' or doctor.organization_id != row.organization_id:
            abort(403)
        return row, doctor

    @app.get('/api/v1/onboarding/bootstrap')
    def onboarding_bootstrap():
        enabled = workspace_enabled(app.config)
        if enabled and 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_urlsafe(24)
        with SessionLocal() as db:
            authenticated = current_user(db) is not None
        return {'enabled': enabled, 'csrf_token': session.get('csrf_token') if enabled else None,
            'authenticated': authenticated, 'environment': app.config.get('APP_ENV', 'development'),
            'email_verification': ('evaluation_not_verified' if app.config.get('APP_ENV')=='evaluation_sandbox' else 'synthetic_auto') if enabled else 'disabled',
            'professional_verification': ('not_verified' if app.config.get('APP_ENV')=='evaluation_sandbox' else 'synthetic_auto') if enabled else 'disabled',
            'production_verification': 'DEFERRED_BY_PRODUCT_DECISION'}

    @app.get('/api/v1/onboarding/journey')
    def onboarding_journey():
        if not session.get('csrf_token'):
            return error(403, 'BOOTSTRAP_REQUIRED', 'Сначала откройте форму регистрации')
        with SessionLocal.begin() as db:
            user = current_user(db)
            if user and user.role != 'patient':
                abort(403)
            return journey_payload(journey_for(db, user))

    @app.put('/api/v1/onboarding/journey')
    def onboarding_journey_save():
        data = body(('doctor_id', 'subject', 'message', 'revision'))
        rev = version(data, 'revision')
        with SessionLocal.begin() as db:
            user = current_user(db)
            if user and user.role != 'patient':
                abort(403)
            row = journey_for(db, user)
            values = {'updated_at': utc_now(), 'revision': rev + 1}
            if 'doctor_id' in data:
                if not isinstance(data['doctor_id'], str):
                    raise OnboardingFailure(422)
                doctor = db.get(User, data['doctor_id'])
                if not doctor or doctor.role != 'doctor':
                    raise OnboardingFailure(422)
                if user and doctor.organization_id != user.organization_id:
                    abort(403)
                values['doctor_id'] = doctor.id
            for key, limit in (('subject', 160), ('message', 4000)):
                if key in data:
                    if not isinstance(data[key], str) or len(data[key]) > limit:
                        raise OnboardingFailure(422)
                    values[key] = data[key]
            merged = values.get('subject', row.subject) + '\n\n' + values.get('message', row.message)
            if len(merged) > 2000:
                return error(422, 'INVALID_INTAKE', 'Тема и сообщение вместе не должны превышать 2000 символов')
            result = db.execute(update(OnboardingJourney).where(OnboardingJourney.id == row.id,
                OnboardingJourney.revision == rev).values(**values))
            if result.rowcount != 1:
                return error(409, 'STALE_REVISION', 'Черновик изменён; обновите страницу')
            db.refresh(row)
            return journey_payload(row)

    @app.post('/api/v1/onboarding/register')
    def onboarding_register():
        data = body(('display_name', 'email', 'password', 'terms_consent', 'invitation_token'))
        name = text(data, 'display_name', 2, 100)
        password = data.get('password')
        if not isinstance(password, str) or not 12 <= len(password) <= 128 or data.get('terms_consent') is not True:
            raise OnboardingFailure(422)
        try:
            email = normalize_synthetic_email(data.get('email'))
        except ValueError:
            return error(422, 'INVALID_SYNTHETIC_EMAIL', 'Используйте адрес .test или .example')
        verification = SyntheticEmailVerifier().verify(email, app.config)
        try:
            with SessionLocal.begin() as db:
                if current_user(db):
                    raise OnboardingFailure(409)
                if db.scalar(select(LocalIdentity).where(LocalIdentity.email == email)):
                    return error(409, 'REGISTRATION_CONFLICT', 'Регистрация недоступна для этих данных')
                journey = journey_for(db)
                org = app.config.get('EVALUATION_TENANT') if app.config.get('APP_ENV')=='evaluation_sandbox' else 'org_demo'
                if 'invitation_token' in data:
                    invite, _ = invitation_for_token(db, data['invitation_token'])
                    if not hmac.compare_digest(invite.recipient_hash, digest(email)):
                        abort(403)
                    org = invite.organization_id
                    # Invitation context overrides no draft; foreign selected doctor is rejected.
                    selected = db.get(User, journey.doctor_id) if journey.doctor_id else None
                    if selected and selected.organization_id != org:
                        abort(403)
                elif journey.doctor_id:
                    selected = db.get(User, journey.doctor_id)
                    if not selected or selected.role != 'doctor':
                        raise OnboardingFailure(422)
                    org = selected.organization_id
                patient = Patient(id=uid(), display_name=name, diagnosis_label='', medication_label='',
                    severity_label='', trend='insufficient_data', last_activity_at=None)
                db.add(patient)
                db.flush()
                user = User(id=uid(), display_name=name, role='patient', specialty=None,
                    organization_id=org, patient_id=patient.id, external_subject=None)
                db.add(user)
                db.flush()
                db.add(LocalIdentity(user_id=user.id, email=email, password_hash=generate_password_hash(password),
                    email_provider=verification['provider'], email_status=verification['status'], created_at=utc_now()))
                claimed = db.execute(update(OnboardingJourney).where(OnboardingJourney.id == journey.id,
                    OnboardingJourney.owner_id.is_(None)).values(owner_id=user.id, updated_at=utc_now()))
                if claimed.rowcount != 1:
                    raise OnboardingFailure(409)
                db.refresh(journey)
                state_for(db, user)
                audit(db, user, 'synthetic_patient_registered', user.id)
                db.flush()
                # Session rotation only follows a successful commit.
            rotate(user, journey)
            with SessionLocal.begin() as db:
                return auth_context(db, user), 201
        except IntegrityError:
            return error(409, 'REGISTRATION_CONFLICT', 'Регистрация недоступна для этих данных')

    @app.post('/api/v1/onboarding/login')
    def onboarding_login():
        data = body(('email', 'password'))
        try:
            email = normalize_synthetic_email(data.get('email'))
        except ValueError:
            email = ''
        password = data.get('password')
        with SessionLocal.begin() as db:
            identity = db.scalar(select(LocalIdentity).where(LocalIdentity.email == email))
            user = db.get(User, identity.user_id) if identity else None
            if not user or not isinstance(password, str) or len(password) > 128 or not check_password_hash(identity.password_hash, password):
                return error(401, 'INVALID_CREDENTIALS', 'Неверные данные входа')
            journey = adopt_journey(db, user) if user.role == 'patient' else None
            if user.role == 'patient':
                state_for(db, user)
        rotate(user, journey)
        with SessionLocal.begin() as db:
            return auth_context(db, user)

    @app.post('/api/v1/onboarding/logout')
    def onboarding_logout():
        body(())
        with SessionLocal.begin() as db:
            revoke_session(db)
        session.clear()
        session['csrf_token'] = secrets.token_urlsafe(24)
        return {'status': 'logged_out', 'csrf_token': session['csrf_token']}

    @app.route('/api/v1/onboarding/state', methods=['GET', 'PUT'])
    def onboarding_state():
        data = body(('introduction_seen', 'status')) if request.method == 'PUT' else None
        with SessionLocal.begin() as db:
            user = require_role(db, 'patient')
            row = state_for(db, user)
            if data is not None:
                if 'introduction_seen' in data:
                    if type(data['introduction_seen']) is not bool:
                        raise OnboardingFailure(422)
                    row.introduction_seen = int(data['introduction_seen'])
                if 'status' in data:
                    if data['status'] not in ('completed', 'pending'):
                        raise OnboardingFailure(422)
                    row.status = data['status']
                row.updated_at = utc_now()
            return state_payload(db, user)

    @app.post('/api/v1/onboarding/invitations')
    def onboarding_invitation_create():
        data = body(('recipient_email', 'categories', 'ttl_hours'))
        try:
            email = normalize_synthetic_email(data.get('recipient_email'))
        except ValueError:
            raise OnboardingFailure(422)
        categories = data.get('categories')
        ttl = data.get('ttl_hours', 24)
        if not isinstance(categories, list) or not categories or any(not isinstance(c, str) for c in categories) or not set(categories) <= CATEGORIES or len(set(categories)) != len(categories) or type(ttl) is not int or not 1 <= ttl <= 168:
            raise OnboardingFailure(422)
        token = secrets.token_urlsafe(32)
        stamp = utc_now()
        expires = (datetime.now(timezone.utc) + timedelta(hours=ttl)).isoformat().replace('+00:00', 'Z')
        with SessionLocal.begin() as db:
            doctor = require_role(db, 'doctor')
            row = PatientInvitation(id=uid(), token_hash=digest(token), issuer_id=doctor.id,
                recipient_hash=digest(email), organization_id=doctor.organization_id,
                categories=','.join(categories), status='pending', created_at=stamp, expires_at=expires)
            db.add(row)
            audit(db, doctor, 'patient_invitation_created', row.id)
            path = '/invite/' + token
            base = app.config.get('PUBLIC_BASE_URL', 'http://127.0.0.1:8765').rstrip('/')
            parsed = urlsplit(base)
            if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.query or parsed.fragment or parsed.path not in ('', '/') or parsed.username or parsed.password:
                raise RuntimeError('PUBLIC_BASE_URL must be a trusted origin')
            absolute = base + '/#' + path
            import qrcode
            import qrcode.image.svg
            stream = io.BytesIO()
            qrcode.make(absolute, image_factory=qrcode.image.svg.SvgPathImage).save(stream)
            qr = 'data:image/svg+xml;base64,' + base64.b64encode(stream.getvalue()).decode('ascii')
            return {'id': row.id, 'token': token, 'url': path, 'absolute_url': absolute,
                'qr_data_uri': qr, 'qr_svg': qr, 'expires_at': expires, 'categories': categories}, 201

    @app.get('/api/v1/onboarding/invitations')
    def onboarding_invitation_list():
        with SessionLocal() as db:
            doctor = require_role(db, 'doctor')
            rows = db.scalars(select(PatientInvitation).where(PatientInvitation.issuer_id == doctor.id)
                              .order_by(PatientInvitation.created_at.desc()))
            return {'items': [{k: getattr(row, k) for k in ('id', 'status', 'expires_at', 'patient_user_id')} |
                {'categories': row.categories.split(',')} for row in rows]}

    @app.post('/api/v1/onboarding/invitations/preview')
    def onboarding_invitation_preview():
        data = body(('token',))
        with SessionLocal() as db:
            token = data.get('token')
            if not isinstance(token, str) or not 20 <= len(token) <= 200:
                abort(404)
            token_hash = digest(token)
            new_invite = db.scalar(select(PatientInvitation.id).where(PatientInvitation.token_hash == token_hash))
            if new_invite is None:
                legacy = db.scalar(select(Invitation).where(Invitation.code_hash == token_hash))
                if not legacy or legacy.status != 'pending':
                    abort(404)
                try:
                    expires = datetime.fromisoformat(legacy.expires_at.replace('Z', '+00:00'))
                    if expires <= datetime.now(timezone.utc):
                        abort(404)
                except (ValueError, TypeError):
                    abort(404)
                user = current_user(db)
                if not user or legacy.recipient_id != user.id or legacy.target_role != user.role or legacy.organization_id != user.organization_id:
                    abort(403)
                issuer = db.get(User, legacy.issuer_id)
                if not issuer or (issuer.role != 'platform_admin' and issuer.organization_id != legacy.organization_id):
                    abort(403)
                if legacy.target_role == 'patient' and (user.patient_id != legacy.patient_id or issuer.role != 'doctor'):
                    abort(403)
                return {'legacy': True, 'doctor': {'id': issuer.id, 'name': issuer.display_name},
                    'categories': legacy.categories.split(',') if legacy.categories else [],
                    'organization_id': legacy.organization_id, 'expires_at': legacy.expires_at,
                    'consent_version': CONSENT_VERSION}
            row, doctor = invitation_for_token(db, token)
            return {'id': row.id, 'doctor': {'id': doctor.id, 'name': doctor.display_name},
                'organization_id': row.organization_id, 'categories': row.categories.split(','),
                'expires_at': row.expires_at, 'status': row.status, 'consent_version': CONSENT_VERSION}

    @app.post('/api/v1/onboarding/invitations/accept')
    def onboarding_invitation_accept():
        data = body(('token', 'consent', 'consent_version'))
        if data.get('consent') is not True or data.get('consent_version') != CONSENT_VERSION:
            return error(422, 'CONSENT_REQUIRED', 'Подтвердите согласие указанной версии')
        with SessionLocal.begin() as db:
            user = require_role(db, 'patient')
            row, doctor = invitation_for_token(db, data.get('token'))
            identity = db.get(LocalIdentity, user.id)
            if not identity or not user.patient_id or user.organization_id != row.organization_id or not hmac.compare_digest(row.recipient_hash, digest(identity.email)):
                abort(403)
            accepted = utc_now()
            result = db.execute(update(PatientInvitation).where(PatientInvitation.id == row.id,
                PatientInvitation.status == 'pending', PatientInvitation.expires_at > accepted)
                .values(status='accepted', accepted_at=accepted, patient_user_id=user.id))
            if result.rowcount != 1:
                raise OnboardingFailure(409)
            link = db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.doctor_id == doctor.id,
                DoctorPatientLink.patient_id == user.patient_id))
            if link:
                # Explicit acceptance replaces the grant with exactly reviewed categories.
                link.categories = row.categories
            else:
                db.add(DoctorPatientLink(doctor_id=doctor.id, patient_id=user.patient_id, categories=row.categories))
            db.add(PatientConsent(id=uid(), patient_user_id=user.id, doctor_id=doctor.id,
                invitation_id=row.id, categories=row.categories, version=CONSENT_VERSION, accepted_at=accepted))
            audit(db, user, 'patient_invitation_accepted', row.id)
            return {'status': 'accepted', 'clinical_link_created': True,
                'scope': row.categories.split(','), 'invitation_id': row.id}

    @app.post('/api/v1/onboarding/invitations/<iid>/revoke')
    def onboarding_invitation_revoke(iid):
        body(())
        with SessionLocal.begin() as db:
            doctor = require_role(db, 'doctor')
            result = db.execute(update(PatientInvitation).where(PatientInvitation.id == iid,
                PatientInvitation.issuer_id == doctor.id, PatientInvitation.status == 'pending')
                .values(status='revoked', revoked_at=utc_now()))
            if result.rowcount != 1:
                row = db.get(PatientInvitation, iid)
                if not row or row.issuer_id != doctor.id:
                    abort(404)
                raise OnboardingFailure(409)
            audit(db, doctor, 'patient_invitation_revoked', iid)
            return {'status': 'revoked'}

    def draft_payload(row):
        return {key: getattr(row, key) for key in ('id', 'invitation_id', 'content', 'state',
                'version', 'created_at', 'signed_at', 'published_at')}

    @app.post('/api/v1/onboarding/invitations/<iid>/drafts')
    def onboarding_draft_create(iid):
        data = body(('content',))
        content = text(data, 'content', 2, 4000)
        with SessionLocal.begin() as db:
            doctor = require_role(db, 'doctor')
            invite = db.get(PatientInvitation, iid)
            if not invite or invite.issuer_id != doctor.id:
                abort(404)
            if invite.status == 'revoked' or invite.organization_id != doctor.organization_id or invite.expires_at <= utc_now() and invite.status != 'accepted':
                raise OnboardingFailure(409)
            row = PreparedOnboardingDraft(id=uid(), invitation_id=iid, clinician_id=doctor.id,
                content=content, state='draft', version=1, created_at=utc_now())
            db.add(row)
            db.flush()
            audit(db, doctor, 'onboarding_draft_created', row.id)
            return draft_payload(row), 201

    @app.get('/api/v1/onboarding/drafts')
    def onboarding_drafts():
        with SessionLocal() as db:
            doctor = require_role(db, 'doctor')
            return {'items': [draft_payload(row) for row in db.scalars(select(PreparedOnboardingDraft)
                .where(PreparedOnboardingDraft.clinician_id == doctor.id)
                .order_by(PreparedOnboardingDraft.created_at.desc()))]}

    def active_consent(db, invite, doctor):
        user = db.get(User, invite.patient_user_id) if invite.patient_user_id else None
        if not user or user.role != 'patient' or user.organization_id != doctor.organization_id:
            return None
        # Lock consent in PostgreSQL; SQLite write CAS below serializes mutations.
        consent = db.scalar(select(PatientConsent).where(PatientConsent.invitation_id == invite.id,
            PatientConsent.patient_user_id == user.id, PatientConsent.doctor_id == doctor.id,
            PatientConsent.revoked_at.is_(None)).with_for_update())
        link = db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.patient_id == user.patient_id,
            DoctorPatientLink.doctor_id == doctor.id))
        if not consent or not link or 'symptoms' not in consent.categories.split(',') or 'symptoms' not in link.categories.split(','):
            return None
        return user

    def advance_draft(draftid, state, previous):
        data = body(('confirmation', 'version'))
        rev = version(data)
        if data.get('confirmation') is not True:
            raise OnboardingFailure(422)
        with SessionLocal.begin() as db:
            doctor = require_role(db, 'doctor')
            row = db.get(PreparedOnboardingDraft, draftid)
            if not row or row.clinician_id != doctor.id:
                abort(404)
            invite = db.get(PatientInvitation, row.invitation_id)
            if not invite or invite.status != 'accepted' or invite.organization_id != doctor.organization_id:
                abort(403)
            patient = active_consent(db, invite, doctor)
            if not patient:
                abort(403)
            values = {'state': state, 'version': rev + 1,
                'signed_at' if state == 'signed' else 'published_at': utc_now()}
            # Recheck grant in the same atomic UPDATE, guarding stale consent/link reads.
            grant = exists(select(PatientConsent.id).where(PatientConsent.invitation_id == invite.id,
                PatientConsent.revoked_at.is_(None),
                (',' + PatientConsent.categories + ',').contains(',symptoms,')))
            linked = exists(select(DoctorPatientLink.id).where(DoctorPatientLink.patient_id == patient.patient_id,
                DoctorPatientLink.doctor_id == doctor.id,
                (',' + DoctorPatientLink.categories + ',').contains(',symptoms,')))
            result = db.execute(update(PreparedOnboardingDraft).where(PreparedOnboardingDraft.id == row.id,
                PreparedOnboardingDraft.state == previous, PreparedOnboardingDraft.version == rev,
                grant, linked).values(**values))
            if result.rowcount != 1:
                raise OnboardingFailure(409)
            audit(db, doctor, 'onboarding_draft_' + state, row.id)
            if state == 'published':
                db.add(UserNotification(id=uid(), recipient_id=patient.id, category='record',
                    text='Врач опубликовал запись', created_at=utc_now()))
            db.refresh(row)
            return draft_payload(row)

    @app.post('/api/v1/onboarding/drafts/<draftid>/sign')
    def onboarding_draft_sign(draftid):
        return advance_draft(draftid, 'signed', 'draft')

    @app.post('/api/v1/onboarding/drafts/<draftid>/publish')
    def onboarding_draft_publish(draftid):
        return advance_draft(draftid, 'published', 'signed')

    @app.get('/api/v1/onboarding/records')
    def onboarding_records():
        with SessionLocal() as db:
            user = require_role(db, 'patient')
            # Every visibility predicate applies before clinical content is selected.
            rows = db.execute(select(PreparedOnboardingDraft, User.display_name)
                .join(PatientInvitation, PatientInvitation.id == PreparedOnboardingDraft.invitation_id)
                .join(PatientConsent, (PatientConsent.invitation_id == PatientInvitation.id) &
                      (PatientConsent.doctor_id == PreparedOnboardingDraft.clinician_id))
                .join(User, User.id == PreparedOnboardingDraft.clinician_id)
                .join(DoctorPatientLink, (DoctorPatientLink.doctor_id == User.id) &
                      (DoctorPatientLink.patient_id == user.patient_id))
                .where(PreparedOnboardingDraft.state == 'published',
                    PreparedOnboardingDraft.signed_at.is_not(None),
                    PreparedOnboardingDraft.published_at.is_not(None),
                    PatientInvitation.status == 'accepted', PatientInvitation.patient_user_id == user.id,
                    PatientConsent.patient_user_id == user.id, PatientConsent.revoked_at.is_(None),
                    (',' + PatientConsent.categories + ',').contains(',symptoms,'),
                    (',' + DoctorPatientLink.categories + ',').contains(',symptoms,'),
                    User.role == 'doctor', User.organization_id == user.organization_id)
                .order_by(PreparedOnboardingDraft.published_at.desc()))
            return {'items': [{'id': row.id, 'content': row.content, 'published_at': row.published_at,
                               'clinician_name': name} for row, name in rows]}

    @app.post('/api/v1/onboarding/professional-verification')
    def onboarding_professional_verification():
        body(())
        with SessionLocal.begin() as db:
            doctor = require_role(db, 'doctor')
            result = SyntheticProfessionalVerifier().verify(doctor, app.config)
            row = db.get(StaffVerification, doctor.id)
            if row is None:
                row = StaffVerification(user_id=doctor.id, provider=result['provider'],
                    status=result['status'], verified_at=utc_now())
                db.add(row)
            else:
                row.provider, row.status, row.verified_at = result['provider'], result['status'], utc_now()
            audit(db, doctor, 'synthetic_professional_verified', doctor.id)
            return result
