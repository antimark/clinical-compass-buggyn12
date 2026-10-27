"""Projection boundary for optional administrative identity/contact data.

Fernet key comes only from CC_PII_ENCRYPTION_KEY, outside database/configuration.
Core User/Patient names, identity vaults, clinical text and login email are never
used as a fallback. Filtering and sorting operate on authorized projections.
"""
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select, update
from .models import User, DoctorPatientLink
from .onboarding_models import PatientConsent
from .extension_models import Appointment, Audit
from .admin_privacy_models import (AdminPrivacyFlag as Flag, AdminPrivacyTemplate as Template,
    AdminPrivacyPolicy as Policy, AdminPrivacyOverride as Override, AdminPrivacyValue as Value)

FIELDS = {'first_name': 'Имя', 'last_name': 'Фамилия', 'middle_name': 'Отчество',
          'phone': 'Телефон', 'email': 'Электронная почта'}


class PrivacyFailure(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def fail(status, code, message):
    raise PrivacyFailure(status, code, message)


def stamp():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def parse_time(value):
    if not isinstance(value, str) or len(value) > 40:
        fail(422, 'INVALID_EXPIRY', 'Укажите время с часовым поясом')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except ValueError:
        fail(422, 'INVALID_EXPIRY', 'Укажите время с часовым поясом')


def field(key):
    if key not in FIELDS:
        fail(422, 'INELIGIBLE_FIELD', 'Допустимы только перечисленные идентификационные и контактные поля')
    return key


def fresh_actor(db, actor, role):
    row = db.get(User, actor.id, populate_existing=True) if actor else None
    if row is None:
        fail(401, 'AUTHENTICATION_REQUIRED', 'Необходимо войти')
    if row.role != role:
        fail(403, 'ROLE_FORBIDDEN', 'Недостаточно прав')
    return row


def audit(db, actor, action, target):
    db.add(Audit(id='ap_' + uuid.uuid4().hex, actor=actor.id, action=action,
        object_type='admin_privacy', object_id=target[:60], created_at=stamp()))


def patient_ref(secret, organization_id, patient_id):
    return hmac.new(str(secret).encode(), (organization_id + ':' + patient_id).encode(), hashlib.sha256).hexdigest()[:22]


def relationship(db, patient, org):
    """Current clinical relationship metadata, never clinical contents.

    Mere patient organization membership is insufficient. Existing legacy doctor
    links without a consent ledger retain core compatibility; once a ledger
    exists, only its currently active intersection can authorize a relationship.
    """
    if patient.role != 'patient' or patient.organization_id != org or not patient.patient_id:
        return False
    rows = db.execute(select(DoctorPatientLink, User).join(User,
        User.id == DoctorPatientLink.doctor_id).where(DoctorPatientLink.patient_id == patient.patient_id,
        User.role == 'doctor', User.organization_id == org)).all()
    for link, doctor in rows:
        categories = set(filter(None, link.categories.split(',')))
        consents = db.scalars(select(PatientConsent).where(PatientConsent.patient_user_id == patient.id,
            PatientConsent.doctor_id == doctor.id).execution_options(populate_existing=True)).all()
        if consents:
            categories &= set().union(*(set(c.categories.split(',')) for c in consents if c.revoked_at is None))
        if categories:
            return True
    return False


def own_patient(db, actor, org=None, lock=False):
    actor = fresh_actor(db, actor, 'patient')
    if lock:
        # Serialize acceptance/overrides on the identity row, without changing data.
        db.execute(update(User).where(User.id == actor.id).values(role=User.role))
    if org is not None and not relationship(db, actor, org):
        fail(404, 'RELATIONSHIP_NOT_FOUND', 'Активная связь с клиникой не найдена')
    return actor


def clinic_actor(db, actor, org=None):
    actor = fresh_actor(db, actor, 'clinic_admin')
    if org is not None and actor.organization_id != org:
        fail(403, 'TENANT_FORBIDDEN', 'Другая организация недоступна')
    return actor


def flag_state(db, org):
    global_row = db.get(Flag, 'GLOBAL', populate_existing=True)
    local_row = db.get(Flag, 'org:' + org, populate_existing=True)
    return {'global_enabled': bool(global_row and global_row.enabled),
            'organization_enabled': bool(local_row and local_row.enabled),
            'enabled': bool(global_row and global_row.enabled and local_row and local_row.enabled)}


def set_flag(db, actor, org, enabled):
    actor = fresh_actor(db, actor, 'platform_admin')
    if type(enabled) is not bool or (org is not None and (not isinstance(org, str) or not org or len(org) > 64)):
        fail(422, 'INVALID_FLAG', 'Укажите организацию и логическое значение')
    if org is not None and not db.scalar(select(User.id).where(User.organization_id == org).limit(1)):
        fail(404, 'ORGANIZATION_NOT_FOUND', 'Организация не найдена')
    scope = 'GLOBAL' if org is None else 'org:' + org
    row = db.get(Flag, scope)
    if row is None:
        db.add(Flag(scope=scope, enabled=enabled))
    else:
        row.enabled = enabled
    audit(db, actor, 'admin_privacy_flag_changed', scope)
    db.flush()


def template_payload(row):
    return {'id': row.id, 'organization_id': row.organization_id, 'template_key': row.template_key,
            'version': row.version, 'read_fields': json.loads(row.read_fields_json), 'created_at': row.created_at}


def templates(db, org):
    return [template_payload(t) for t in db.scalars(select(Template).where(
        Template.organization_id == org).order_by(Template.template_key, Template.version)).all()]


def create_template(db, actor, org, key, version, read_fields):
    actor = fresh_actor(db, actor, 'platform_admin')
    if not isinstance(org, str) or len(org) > 64 or not db.scalar(select(User.id).where(User.organization_id == org).limit(1)):
        fail(422, 'INVALID_ORGANIZATION', 'Укажите существующую организацию')
    if not isinstance(key, str) or not key.isidentifier() or len(key) > 80 or type(version) is not int or version < 1:
        fail(422, 'INVALID_TEMPLATE', 'Укажите ключ и положительную версию шаблона')
    if not isinstance(read_fields, list) or not all(isinstance(k, str) for k in read_fields) or len(set(read_fields)) != len(read_fields):
        fail(422, 'INVALID_FIELDS', 'Укажите неповторяющийся список полей')
    for k in read_fields:
        field(k)
    if db.scalar(select(Template.id).where(Template.organization_id == org, Template.template_key == key, Template.version == version)):
        fail(409, 'TEMPLATE_EXISTS', 'Версия уже существует; создайте новую')
    row = Template(id='apt_' + uuid.uuid4().hex, organization_id=org, template_key=key,
        version=version, read_fields_json=json.dumps(sorted(read_fields)), created_at=stamp())
    db.add(row)
    audit(db, actor, 'admin_privacy_template_created', row.id)
    db.flush()
    return template_payload(row)


def policy_payload(db, patient, org):
    row = db.get(Policy, (patient.id, org), populate_existing=True)
    if row is None:
        return None
    return {'template_id': row.template_id, 'active': row.active, 'accepted_at': row.accepted_at,
        'revision': row.revision, 'overrides': [{'field_key': x.field_key, 'effect': x.effect, 'expires_at': x.expires_at}
            for x in db.scalars(select(Override).where(Override.patient_user_id == patient.id,
                Override.organization_id == org).order_by(Override.field_key)).all()]}


def accept_policy(db, actor, org, template_id, confirmed, revision):
    actor = own_patient(db, actor, org, lock=True)
    if confirmed is not True:
        fail(422, 'CONFIRMATION_REQUIRED', 'Подтвердите выбранную версию разрешения')
    template = db.get(Template, template_id) if isinstance(template_id, str) else None
    if template is None or template.organization_id != org:
        fail(422, 'INVALID_TEMPLATE', 'Шаблон другой организации или не найден')
    row = db.get(Policy, (actor.id, org), populate_existing=True)
    if type(revision) is not int or revision != (row.revision if row else 0):
        fail(409, 'REVISION_CONFLICT', 'Разрешение изменилось; обновите страницу')
    if row:
        row.template_id, row.active, row.accepted_at, row.revision = template.id, True, stamp(), row.revision + 1
    else:
        row = Policy(patient_user_id=actor.id, organization_id=org, template_id=template.id,
            active=True, accepted_at=stamp(), revision=1)
        db.add(row)
    db.execute(delete(Override).where(Override.patient_user_id == actor.id, Override.organization_id == org))
    audit(db, actor, 'admin_privacy_policy_accepted', template.id)
    db.flush()
    return policy_payload(db, actor, org)


def revoke_policy(db, actor, org):
    # Withdrawal remains possible even after underlying clinical link revocation.
    actor = own_patient(db, actor, lock=True)
    row = db.get(Policy, (actor.id, org), populate_existing=True)
    if row:
        row.active, row.revision = False, row.revision + 1
    audit(db, actor, 'admin_privacy_policy_revoked', org)
    db.flush()
    return {'revoked': True}


def update_override(db, actor, org, key, effect, expires_at, revision):
    actor = own_patient(db, actor, org, lock=True)
    field(key)
    policy = db.get(Policy, (actor.id, org), populate_existing=True)
    if not policy or not policy.active:
        fail(409, 'POLICY_REQUIRED', 'Сначала примите версию разрешения')
    if type(revision) is not int or revision != policy.revision:
        fail(409, 'REVISION_CONFLICT', 'Разрешение изменилось; обновите страницу')
    if effect not in ('ALLOW', 'DENY', 'REMOVE'):
        fail(422, 'INVALID_EFFECT', 'Выберите ALLOW, DENY или REMOVE')
    if expires_at is not None:
        expires = parse_time(expires_at)
        if expires <= datetime.now(timezone.utc):
            fail(422, 'INVALID_EXPIRY', 'Срок должен быть в будущем')
        expires_at = expires.isoformat().replace('+00:00', 'Z')
    row = db.get(Override, (actor.id, org, key))
    if effect == 'REMOVE':
        if row:
            db.delete(row)
    elif row:
        row.effect, row.expires_at = effect, expires_at
    else:
        db.add(Override(patient_user_id=actor.id, organization_id=org, field_key=key, effect=effect, expires_at=expires_at))
    policy.revision += 1
    audit(db, actor, 'admin_privacy_override_changed', org)
    db.flush()
    return policy_payload(db, actor, org)


def cipher():
    key = os.environ.get('CC_PII_ENCRYPTION_KEY', '')
    if not key:
        fail(503, 'PII_KEY_UNAVAILABLE', 'Хранилище контактных данных не настроено')
    try:
        return Fernet(key.encode('ascii'))
    except (ValueError, UnicodeError):
        fail(503, 'PII_KEY_UNAVAILABLE', 'Хранилище контактных данных не настроено')


def decrypt(value, crypt):
    try:
        return crypt.decrypt(value.encode('ascii')).decode('utf-8')
    except (InvalidToken, ValueError, UnicodeError):
        fail(503, 'PII_KEY_UNAVAILABLE', 'Контактные данные временно недоступны')


def write_values(db, actor, values):
    actor = own_patient(db, actor, lock=True)
    if not isinstance(values, dict) or len(values) > len(FIELDS):
        fail(422, 'INVALID_VALUES', 'Укажите разрешённые контактные поля')
    for key, value in values.items():
        field(key)
        if not isinstance(value, str) or len(value) > 500:
            fail(422, 'INVALID_VALUE', 'Значение должно быть строкой до 500 символов')
    crypt = cipher()
    for key, value in values.items():
        row = db.get(Value, (actor.id, key))
        encrypted = crypt.encrypt(value.encode('utf-8')).decode('ascii')
        if row:
            row.ciphertext, row.updated_at = encrypted, stamp()
        else:
            db.add(Value(patient_user_id=actor.id, field_key=key, ciphertext=encrypted, updated_at=stamp()))
    audit(db, actor, 'admin_privacy_own_values_updated', actor.id)
    db.flush()
    return {'saved_fields': sorted(values)}


def own_values(db, actor):
    actor = own_patient(db, actor)
    rows = db.scalars(select(Value).where(Value.patient_user_id == actor.id)).all()
    crypt = cipher() if rows else None
    return {x.field_key: decrypt(x.ciphertext, crypt) for x in rows if x.field_key in FIELDS}


def effective_fields(db, patient, org):
    if not relationship(db, patient, org) or not flag_state(db, org)['enabled']:
        return set()
    policy = db.get(Policy, (patient.id, org), populate_existing=True)
    template = db.get(Template, policy.template_id) if policy and policy.active else None
    if template is None or template.organization_id != org:
        return set()
    allowed = set(json.loads(template.read_fields_json)) & set(FIELDS)
    for item in db.scalars(select(Override).where(Override.patient_user_id == patient.id,
            Override.organization_id == org)).all():
        if item.expires_at and parse_time(item.expires_at) <= datetime.now(timezone.utc):
            continue
        if item.effect == 'ALLOW':
            allowed.add(item.field_key)
        elif item.effect == 'DENY':
            allowed.discard(item.field_key)
    return allowed & set(FIELDS)


def projected_patient(db, actor, patient, secret, requested_fields=None):
    actor = clinic_actor(db, actor)
    if not relationship(db, patient, actor.organization_id):
        fail(404, 'PATIENT_NOT_FOUND', 'Пациент не найден')
    granted = effective_fields(db, patient, actor.organization_id)
    if requested_fields is not None:
        granted &= set(requested_fields)
    result = {'patient_ref': patient_ref(secret, actor.organization_id, patient.patient_id),
              'fields': {}, 'contact_visible': False, 'clinical_record_access': False}
    if granted:
        rows = db.scalars(select(Value).where(Value.patient_user_id == patient.id, Value.field_key.in_(granted))).all()
        crypt = cipher() if rows else None
        result['fields'] = {x.field_key: decrypt(x.ciphertext, crypt) for x in rows}
        result['contact_visible'] = bool(result['fields'])
        audit(db, actor, 'admin_privacy_projected_read', result['patient_ref'])
    return result


def clinic_patients(db, actor):
    actor = clinic_actor(db, actor)
    return [p for p in db.scalars(select(User).where(User.role == 'patient',
        User.organization_id == actor.organization_id).order_by(User.id)).all() if relationship(db, p, actor.organization_id)]


def patient_by_ref(db, actor, ref, secret):
    for p in clinic_patients(db, actor):
        if hmac.compare_digest(patient_ref(secret, actor.organization_id, p.patient_id), ref):
            return p
    fail(404, 'PATIENT_NOT_FOUND', 'Пациент не найден')


def projected_patients(db, actor, secret, *, filter_field=None, filter_value=None,
        sort_field=None, requested_fields=None, offset=0, limit=50):
    clinic_actor(db, actor)
    if type(offset) is not int or type(limit) is not int or not 0 <= offset <= 100000 or not 1 <= limit <= 500:
        fail(422, 'INVALID_PAGINATION', 'Некорректная страница')
    if filter_field is not None:
        field(filter_field)
        if not isinstance(filter_value, str) or not filter_value or len(filter_value) > 200:
            fail(422, 'INVALID_FILTER', 'Укажите текст поиска')
    elif filter_value is not None:
        fail(422, 'INVALID_FILTER', 'Укажите поле поиска')
    if sort_field is not None:
        field(sort_field)
    if requested_fields is not None:
        for key in requested_fields:
            field(key)
    project_keys = None if requested_fields is None else set(requested_fields) | {k for k in (filter_field, sort_field) if k}
    views = [projected_patient(db, actor, p, secret, project_keys) for p in clinic_patients(db, actor)]
    if filter_field:
        views = [v for v in views if filter_value.casefold() in v['fields'].get(filter_field, '').casefold()]
    views.sort(key=lambda v: ((sort_field not in v['fields'], v['fields'].get(sort_field, '').casefold(), v['patient_ref'])
                             if sort_field else (v['patient_ref'],)))
    total = len(views)
    views = views[offset:offset + limit]
    if requested_fields is not None:
        for view in views:
            view['fields'] = {k: v for k, v in view['fields'].items() if k in requested_fields}
            view['contact_visible'] = bool(view['fields'])
    return {'items': views, 'total': total, 'offset': offset, 'limit': limit}


def projected_appointments(db, actor, secret):
    actor = clinic_actor(db, actor)
    patients = {p.id: p for p in db.scalars(select(User).where(User.role=='patient',User.organization_id==actor.organization_id)).all()}
    doctors = list(db.scalars(select(User.id).where(User.role == 'doctor', User.organization_id == actor.organization_id)).all())
    if not patients or not doctors:
        return {'items': []}
    # Select strictly administrative columns; case intake/clinical text excluded.
    rows = db.execute(select(Appointment.id, Appointment.patient_user_id, Appointment.doctor_id,
        Appointment.proposed_at, Appointment.format, Appointment.status).where(Appointment.doctor_id.in_(doctors),
        Appointment.patient_user_id.in_(patients)).order_by(Appointment.proposed_at, Appointment.id)).all()
    return {'items': [{'appointment_id': x.id, 'doctor_id': x.doctor_id, 'proposed_at': x.proposed_at,
        'format': x.format, 'status': x.status, 'patient': (projected_patient(db, actor, patients[x.patient_user_id], secret) if relationship(db,patients[x.patient_user_id],actor.organization_id) else {'patient_ref':patient_ref(secret,actor.organization_id,patients[x.patient_user_id].patient_id),'fields':{},'contact_visible':False,'clinical_record_access':False})}
        for x in rows]}


def projected_notices(db, actor, secret):
    # Notices derive only persisted administrative appointment transitions.
    return {'items': [{'id': 'appointment:' + x['appointment_id'] + ':' + x['status'],
        'kind': 'appointment_' + x['status'], 'appointment_id': x['appointment_id'],
        'proposed_at': x['proposed_at'], 'patient': x['patient']}
        for x in projected_appointments(db, actor, secret)['items']
        if x['status'] in ('offered', 'confirmed', 'cancelled', 'declined', 'expired')]}
