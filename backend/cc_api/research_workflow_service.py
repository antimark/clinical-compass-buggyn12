"""Vetted synthetic aggregates with versioning and serialized disclosure control.

No patient/core queries, raw rows or subject IDs are exposed. Subject membership
is retained only as study-scoped HMAC tokens in the internal disclosure ledger.
This is a demonstration privacy guard, not a formal differential privacy claim.
"""
import hashlib
import hmac
import json
import statistics
import uuid
from datetime import date, datetime, timezone
from sqlalchemy import select, update
from .models import User
from .p0_models import DatasetDefinition
from .extension_models import ResearchObservation, Audit
from .research_workflow_models import (ResearchDefinitionRevision as Revision,
    ResearchStudyGrant as Grant, ResearchDisclosure as Disclosure, ResearchStudyLock as Lock)

STUDY = 'study_demo_v1'
MEASURE = 'synthetic_mood'
TAGS = {'synthetic_quality', 'observed_value', 'missing_value'}
SYNTHETIC_SOURCES = {'synthetic', 'synthetic_fixture', 'reproducible_synthetic_fixture_v1'}
LIMITATION = 'Синтетические описательные агрегаты. Сравнение не доказывает эффективность или причинность.'


class ResearchFailure(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def fail(status, code, message):
    raise ResearchFailure(status, code, message)


def stamp():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def uid():
    return 'rw_' + uuid.uuid4().hex


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(secret, value):
    return hmac.new(str(secret).encode(), canonical(value).encode(), hashlib.sha256).hexdigest()


def actor(db, user):
    current = db.get(User, user.id, populate_existing=True) if user else None
    if current is None:
        fail(401, 'AUTHENTICATION_REQUIRED', 'Необходимо войти')
    if current.role != 'researcher':
        fail(403, 'ROLE_FORBIDDEN', 'Требуется роль исследователя')
    return current


def require_grant(db, user, study):
    user = actor(db, user)
    row = db.get(Grant, (user.id, study, user.organization_id), populate_existing=True)
    if study != STUDY or row is None or not row.active:
        fail(404, 'STUDY_NOT_FOUND', 'Разрешённый набор не найден')
    return user


def provision_grant(db, researcher, study=STUDY):
    """Server provisioning only; never called by list/read, never restores revoke."""
    if researcher.role != 'researcher' or study != STUDY:
        raise ValueError('Only a vetted synthetic study can be provisioned')
    key = (researcher.id, study, researcher.organization_id)
    if db.get(Grant, key) is None:
        db.add(Grant(researcher_id=researcher.id, study_id=study,
            organization_id=researcher.organization_id, active=True))
    if db.get(Lock, study) is None:
        db.add(Lock(study_id=study, revision=0))
    db.flush()


def validate(data):
    if not isinstance(data, dict) or set(data) - {'study_id', 'measure', 'cohorts', 'start_date', 'end_date', 'criteria', 'min_cell'}:
        fail(422, 'INVALID_DEFINITION', 'Неизвестные поля определения')
    if data.get('study_id') != STUDY or data.get('measure') != MEASURE:
        fail(422, 'INVALID_SOURCE', 'Доступен только разрешённый синтетический источник')
    groups = data.get('cohorts')
    if not isinstance(groups, list) or not groups or not all(isinstance(x, str) for x in groups) or len(set(groups)) != len(groups) or not set(groups) <= {'A', 'B'}:
        fail(422, 'INVALID_COHORTS', 'Выберите разные когорты A и B')
    window = {}
    for key in ('start_date', 'end_date'):
        value = data.get(key)
        if value is not None:
            try:
                if not isinstance(value, str) or len(value) != 10 or date.fromisoformat(value).isoformat() != value:
                    raise ValueError()
            except ValueError:
                fail(422, 'INVALID_WINDOW', 'Период задаётся датами ГГГГ-ММ-ДД')
        window[key] = value
    if window['start_date'] and window['end_date'] and window['start_date'] > window['end_date']:
        fail(422, 'INVALID_WINDOW', 'Начало периода позже окончания')
    criteria = data.get('criteria', {})
    if not isinstance(criteria, dict) or set(criteria) - {'include', 'exclude'}:
        fail(422, 'INVALID_CRITERIA', 'Неизвестные критерии')
    criteria_out = {}
    for key in ('include', 'exclude'):
        values = criteria.get(key, [])
        if not isinstance(values, list) or not all(isinstance(x, str) for x in values) or len(set(values)) != len(values) or not set(values) <= TAGS:
            fail(422, 'INVALID_CRITERIA', 'Недопустимый критерий отбора')
        criteria_out[key] = sorted(values)
    if set(criteria_out['include']) & set(criteria_out['exclude']):
        fail(422, 'INVALID_CRITERIA', 'Критерий одновременно включён и исключён')
    threshold = data.get('min_cell', 5)
    if type(threshold) is not int or not 5 <= threshold <= 1000:
        fail(422, 'INVALID_THRESHOLD', 'Минимальная ячейка от 5 до 1000')
    return {'study_id': STUDY, 'measure': MEASURE, 'cohorts': sorted(groups), **window,
            'criteria': criteria_out, 'min_cell': threshold}


def definition_payload(row, config=None, version=None):
    return {'id': row.id, 'study_id': row.study_id, 'version': version or row.version,
        'definition': config if config is not None else json.loads(row.definition_json), 'created_at': row.created_at}


def own_definition(db, user, definition_id, lock=False):
    user = actor(db, user)
    if lock:
        db.execute(update(DatasetDefinition).where(DatasetDefinition.id == definition_id,
            DatasetDefinition.researcher_id == user.id).values(version=DatasetDefinition.version))
    row = db.get(DatasetDefinition, definition_id, populate_existing=True)
    if not row or row.researcher_id != user.id:
        fail(404, 'DEFINITION_NOT_FOUND', 'Определение не найдено')
    require_grant(db, user, row.study_id)
    return row


def create_definition(db, user, data):
    config = validate(data)
    user = require_grant(db, user, config['study_id'])
    row = DatasetDefinition(id=uid(), researcher_id=user.id, study_id=config['study_id'],
        definition_json=canonical(config), version=1, created_at=stamp())
    db.add(row)
    db.flush()
    db.add(Revision(id=uid(), definition_id=row.id, version=1, snapshot_json=canonical(config),
        actor_id=user.id, created_at=stamp()))
    db.add(Audit(id=uid(), actor=user.id, action='research_definition_created', object_type='dataset', object_id=row.id, created_at=stamp()))
    db.flush()
    return definition_payload(row)


def update_definition(db, user, definition_id, data, revision):
    config = validate(data)
    row = own_definition(db, user, definition_id, lock=True)
    if type(revision) is not int or revision != row.version:
        fail(409, 'REVISION_CONFLICT', 'Определение изменилось; обновите страницу')
    if config['study_id'] != row.study_id:
        fail(422, 'INVALID_SOURCE', 'Источник определения неизменяем')
    previous = json.loads(row.definition_json)
    if config['min_cell'] < previous.get('min_cell', 5):
        fail(422, 'THRESHOLD_DECREASE_FORBIDDEN', 'Порог можно только увеличивать')
    row.version += 1
    row.definition_json = canonical(config)
    db.add(Revision(id=uid(), definition_id=row.id, version=row.version, snapshot_json=canonical(config),
        actor_id=user.id, created_at=stamp()))
    db.add(Audit(id=uid(), actor=user.id, action='research_definition_revised', object_type='dataset', object_id=row.id, created_at=stamp()))
    db.flush()
    return definition_payload(row)


def get_version(db, user, definition_id, version=None):
    row = own_definition(db, user, definition_id)
    version = row.version if version is None else version
    if type(version) is not int or version < 1:
        fail(422, 'INVALID_VERSION', 'Укажите версию определения')
    snapshot = db.scalar(select(Revision).where(Revision.definition_id == row.id, Revision.version == version))
    if snapshot:
        config = validate(json.loads(snapshot.snapshot_json))
    elif version == row.version:
        # Compatibility read for legacy definitions, revision backfill owned by coordinator.
        legacy = json.loads(row.definition_json)
        config = validate({'study_id': row.study_id, **legacy})
    else:
        fail(404, 'VERSION_NOT_FOUND', 'Версия не найдена')
    return row, version, config


def source_tags(row):
    tags = {'synthetic_quality'} if row.source in SYNTHETIC_SOURCES else set()
    tags.add('missing_value' if row.value is None else 'observed_value')
    return tags


def selected_latest(db, config):
    query = select(ResearchObservation).where(ResearchObservation.study_id == config['study_id'],
        ResearchObservation.measure == config['measure'], ResearchObservation.cohort.in_(config['cohorts']),
        ResearchObservation.source.in_(SYNTHETIC_SOURCES))
    dated = []
    for row in db.scalars(query).all():
        try:
            timestamp = datetime.fromisoformat(row.recorded_at.replace('Z', '+00:00'))
            if timestamp.tzinfo is None:
                continue
            timestamp = timestamp.astimezone(timezone.utc)
        except (ValueError, AttributeError):
            continue
        day = timestamp.date().isoformat()
        if config['start_date'] and day < config['start_date']:
            continue
        if config['end_date'] and day > config['end_date']:
            continue
        dated.append((timestamp, row.id, row))
    # Actual timestamps, deterministic ID tie break, before criteria application.
    latest = {}
    for _timestamp, _id, row in sorted(dated, key=lambda x: (x[0], x[1]), reverse=True):
        latest.setdefault((row.cohort, row.study_subject), row)
    include, exclude = set(config['criteria']['include']), set(config['criteria']['exclude'])
    return [r for r in latest.values() if include <= source_tags(r) and not exclude & source_tags(r)]


def set_grant(db, administrator, researcher_id, study, active):
    current = db.get(User, administrator.id, populate_existing=True) if administrator else None
    if current is None or current.role != 'platform_admin':
        fail(403, 'ROLE_FORBIDDEN', 'Требуется администратор платформы')
    researcher = db.get(User, researcher_id) if isinstance(researcher_id, str) else None
    if researcher is None or researcher.role != 'researcher' or study != STUDY or type(active) is not bool:
        fail(422, 'INVALID_GRANT', 'Укажите исследователя, разрешённый набор и логическое значение')
    locked = db.execute(update(Lock).where(Lock.study_id == study).values(revision=Lock.revision + 1))
    if locked.rowcount != 1:
        fail(503, 'STUDY_NOT_PROVISIONED', 'Набор ещё не подготовлен')
    key = (researcher.id, study, researcher.organization_id)
    row = db.get(Grant, key, populate_existing=True)
    if row:
        row.active = active
    else:
        db.add(Grant(researcher_id=researcher.id, study_id=study,
            organization_id=researcher.organization_id, active=active))
    db.add(Audit(id=uid(), actor=current.id, action='research_study_grant_changed',
        object_type='study', object_id=study, created_at=stamp()))
    db.flush()
    return {'researcher_id': researcher.id, 'study_id': study, 'active': active}


def compute(db, user, definition_id, secret, version=None):
    row, version, config = get_version(db, user, definition_id, version)
    # One shared row across every researcher/cohort; serializes first disclosure.
    result = db.execute(update(Lock).where(Lock.study_id == row.study_id).values(revision=Lock.revision + 1))
    if result.rowcount != 1:
        fail(503, 'STUDY_NOT_PROVISIONED', 'Набор ещё не подготовлен')
    require_grant(db, user, row.study_id)
    previous = db.scalars(select(Disclosure).where(Disclosure.study_id == row.study_id)
        .order_by(Disclosure.created_at, Disclosure.id)).all()
    observations = selected_latest(db, config)
    items = []
    for cohort in config['cohorts']:
        cache = next((d for d in previous if d.definition_id == row.id and d.definition_version == version and d.cohort == cohort), None)
        if cache:
            items.append(json.loads(cache.result_json))
            continue
        members = sorted((digest(secret, [row.study_id, r.study_subject]), r.value, r.recorded_at)
            for r in observations if r.cohort == cohort)
        tokens = {x[0] for x in members}
        value_hash = digest(secret, members)
        valid = [x[1] for x in members if x[1] is not None]
        threshold = config['min_cell']
        reason = None
        if len(tokens) < threshold or len(valid) < threshold:
            reason = 'small_cell'
        else:
            for disclosure in previous:
                published = json.loads(disclosure.result_json)
                if published['suppressed']:
                    continue
                old_tokens = set(json.loads(disclosure.membership_json))
                difference = len(tokens ^ old_tokens)
                if difference and difference < max(threshold, disclosure.min_cell):
                    reason = 'differencing_guard'
                    break
                if not difference and value_hash != disclosure.values_fingerprint:
                    reason = 'changed_population_values_requires_review'
                    break
        hidden = reason is not None
        payload = {'cohort': cohort, 'n': None if hidden else len(tokens),
            'observed_n': None if hidden else len(valid), 'missing_n': None if hidden else len(tokens) - len(valid),
            'mean': None if hidden else round(statistics.mean(valid), 2), 'suppressed': hidden,
            'suppression_reason': reason, 'source': 'vetted_synthetic_observations'}
        disclosure = Disclosure(id=uid(), study_id=row.study_id, cohort=cohort, definition_id=row.id,
            definition_version=version, query_fingerprint=digest(secret, [row.id, version, config, cohort]),
            membership_json=canonical(sorted(tokens)), values_fingerprint=value_hash, result_json=canonical(payload),
            min_cell=threshold, created_at=stamp())
        db.add(disclosure)
        previous.append(disclosure)
        items.append(payload)
    db.add(Audit(id=uid(), actor=user.id, action='research_aggregate_disclosed', object_type='dataset', object_id=row.id, created_at=stamp()))
    db.flush()
    return {'id': row.id, 'version': version, 'items': items, 'min_cell': config['min_cell'],
        'synthetic_only': True, 'provenance': 'server-persisted versioned synthetic aggregate', 'limitation': LIMITATION}
