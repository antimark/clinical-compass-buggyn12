"""Additive, opt-in physician day fixtures; no mutation of Phase 3 fixture records."""
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from .models import User, DoctorPatientLink, Checkin
from .extension_models import Audit, PrevisitCase, Appointment
from .patient_experience_models import MetricObservation, SyntheticPersona


def seed_doctor_experience(SessionLocal, include_personas=False):
    if not include_personas:
        return
    with SessionLocal.begin() as db:
        marker = 'dx_fixture_day_v1'
        if db.get(Audit, marker):
            return
        doctor = db.get(User, 'doc_psy')
        person = db.get(User, 'pxu_history_02')
        if not doctor or not person or not db.get(SyntheticPersona, person.id):
            return
        if not db.scalar(select(DoctorPatientLink.id).where(DoctorPatientLink.doctor_id == doctor.id,
                DoctorPatientLink.patient_id == person.patient_id)):
            return
        now = datetime.now(timezone.utc).replace(microsecond=0)
        def stamp(hours=0):
            return (now + timedelta(hours=hours)).isoformat().replace('+00:00', 'Z')
        # These are additional clearly identified source records, not a reset of old
        # observations, identities, questionnaire submissions or treatment histories.
        for i, (value, hours) in enumerate(((5, -48), (2, -24))):
            ident = f'dx_fixture_obs_{i}'
            if not db.get(MetricObservation, ident):
                db.add(MetricObservation(id=ident, patient_id=person.patient_id, metric_key='wellbeing',
                    unit='points', scale_version='mood_1_5_v1', value=value, observed_at=stamp(hours),
                    recorded_at=stamp(hours), source='synthetic_fixture', event_key=ident))
        if not db.get(Checkin, 'dx_fixture_concern'):
            db.add(Checkin(id='dx_fixture_concern', patient_id=person.patient_id, mood_score=2,
                comparison='same', note='Синтетическое сообщение: хочу обсудить последние отметки на ближайшей встрече.',
                recorded_at=stamp(-12)))
        cid = 'dx_fixture_incoming_case'
        if not db.get(PrevisitCase, cid):
            db.add(PrevisitCase(id=cid, patient_user_id=person.id, doctor_id=doctor.id, status='submitted',
                intake_json=json.dumps({'subject': 'Демонстрационная встреча', 'message': 'Синтетический входящий кейс.'}, ensure_ascii=False),
                created_at=stamp(-6), allowed_until=stamp(24 * 30), consent_version='case-1',
                first_patient_message=1, doctor_replied=1))
            db.flush()
            db.add(Appointment(id='dx_fixture_offer', case_id=cid, doctor_id=doctor.id, patient_user_id=person.id,
                proposed_at=stamp(24 * 7), format='video', status='offered'))
        db.add(Audit(id=marker, actor=doctor.id, action='synthetic_physician_fixture_seeded',
            object_type='synthetic_fixture', object_id=person.patient_id, created_at=stamp()))
