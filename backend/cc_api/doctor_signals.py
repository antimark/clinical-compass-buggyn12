"""Explainable demonstration events, never a clinical risk classifier."""
import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .models import Checkin
from .p0_models import AdverseEvent
from .patient_experience_models import MetricObservation
from .doctor_experience_models import DoctorSignal

LIMITATION = 'Синтетическое демонстрационное правило; изменение субъективной оценки не является прогнозом клинического риска.'
RULE_VERSION = 'wellbeing-decrease-2-v1'


def normalized_time(value):
    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('Timezone required')
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def canonical_observations(db, patient_id):
    """Only one explicitly compatible triple; duplicate instants keep latest write."""
    points = []
    for row in db.scalars(select(MetricObservation).where(MetricObservation.patient_id == patient_id,
            MetricObservation.metric_key == 'wellbeing', MetricObservation.unit == 'points',
            MetricObservation.scale_version == 'mood_1_5_v1')).all():
        points.append((row.recorded_at, dict(id=row.id, value=row.value, observed_at=row.observed_at,
            unit=row.unit, scale_version=row.scale_version, source=row.source)))
    for row in db.scalars(select(Checkin).where(Checkin.patient_id == patient_id)).all():
        points.append((row.recorded_at, dict(id=row.id, value=row.mood_score, observed_at=row.recorded_at,
            unit='points', scale_version='mood_1_5_v1', source='legacy_checkin')))
    by_time = {}
    for recorded, point in sorted(points, key=lambda pair: (normalized_time(pair[0]), pair[1]['id'])):
        if not 1 <= point['value'] <= 5:
            continue
        point['observed_at'] = normalized_time(point['observed_at'])
        by_time[point['observed_at']] = point
    return sorted(by_time.values(), key=lambda point: point['observed_at'])


def persist_signal(db, doctor_id, patient_id, *, kind, source, event_key, rule_version,
                   reason, evidence, occurred_at, created_at):
    existing = db.scalar(select(DoctorSignal.id).where(DoctorSignal.doctor_id == doctor_id,
        DoctorSignal.event_key == event_key))
    if existing:
        return
    digest = hashlib.sha256((doctor_id + ':' + event_key).encode()).hexdigest()[:48]
    # Savepoint makes concurrent dashboard reads idempotent without rolling back
    # independent events in this request. A unique DB constraint is authoritative.
    try:
        with db.begin_nested():
            db.add(DoctorSignal(id='dx_' + digest, doctor_id=doctor_id, patient_id=patient_id,
                kind=kind, source=source, event_key=event_key, rule_version=rule_version,
                reason=reason, evidence_json=json.dumps(evidence, ensure_ascii=False),
                occurred_at=normalized_time(occurred_at), status='open', created_at=created_at))
            db.flush()
    except IntegrityError:
        if not db.scalar(select(DoctorSignal.id).where(DoctorSignal.doctor_id == doctor_id,
                DoctorSignal.event_key == event_key)):
            raise


def discover_signals(db, doctor_id, patient_id, scopes, now):
    """Caller must authorize exact scopes before any source read."""
    if 'symptoms' in scopes:
        points = canonical_observations(db, patient_id)
        for before, after in zip(points, points[1:]):
            if before['value'] - after['value'] >= 2:
                persist_signal(db, doctor_id, patient_id, kind='system_signal', source='wellbeing_observation',
                    event_key=RULE_VERSION + ':' + hashlib.sha256((patient_id + ':' + before['id'] + ':' + after['id']).encode()).hexdigest(),
                    rule_version=RULE_VERSION,
                    reason=f"Снижение собственной оценки самочувствия с {before['value']:g} до {after['value']:g} по шкале 1–5.",
                    evidence={'required_scope': 'symptoms', 'observations': [before, after],
                        'rule': 'Разность двух последовательных сопоставимых оценок ≥ 2; медицинские пороги не применяются.'},
                    occurred_at=after['observed_at'], created_at=now)
        for row in db.scalars(select(Checkin).where(Checkin.patient_id == patient_id)).all():
            if not row.note.strip():
                continue
            persist_signal(db, doctor_id, patient_id, kind='patient_report', source='patient_checkin_note',
                event_key='patient-note-v1:' + row.id, rule_version='patient-note-v1',
                reason='Пациент оставил текстовое сообщение при отметке самочувствия. Содержание не классифицировалось автоматически.',
                evidence={'required_scope': 'symptoms', 'event_id': row.id, 'text': row.note,
                    'observations': [{'id': row.id, 'value': row.mood_score, 'observed_at': normalized_time(row.recorded_at),
                        'unit': 'points', 'scale_version': 'mood_1_5_v1'}]}, occurred_at=row.recorded_at, created_at=now)
    if 'medications' in scopes:
        for row in db.scalars(select(AdverseEvent).where(AdverseEvent.patient_id == patient_id)).all():
            persist_signal(db, doctor_id, patient_id, kind='patient_report', source='reported_adverse_event',
                event_key='reported-event-v1:' + row.id, rule_version='reported-event-v1',
                reason='Зарегистрировано сообщение о нежелательном событии; причинная связь не устанавливается автоматически.',
                evidence={'required_scope': 'medications', 'event_id': row.id, 'text': row.description},
                occurred_at=row.created_at, created_at=now)


def signal_payload(row, patient_name):
    evidence = json.loads(row.evidence_json)
    return dict(id=row.id, patient_id=row.patient_id, patient_name=patient_name, kind=row.kind,
        source=row.source, event_key=row.event_key, rule_version=row.rule_version, reason=row.reason,
        evidence=evidence, occurred_at=row.occurred_at, status=row.status,
        limitation=LIMITATION, required_scope=evidence['required_scope'])
