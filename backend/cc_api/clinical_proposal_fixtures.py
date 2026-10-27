"""Explicit disposable synthetic demonstrations; never seed on application GET/startup."""
import json
from datetime import datetime, timedelta, timezone
from .extension_models import PrevisitCase
from .models import User
from .verification import synthetic_enabled

ROUTINE_TEXT = 'Синтетический учебный визит: длительная тревога и трудности сна. Хочу обсудить с психиатром справочную карточку Авиандра; препарат не принимаю.'
CRITICAL_TEXT = 'Изолированная альтернативная учебная ветвь SYNTHETIC_TEST_TRIGGER_03A. Это тест представления критического сигнала, не клиническая оценка.'
FIXTURES = (
    ('phase03a_aviandr_visit', 'pxu_history_02', 'pxp_history_02', ROUTINE_TEXT, 'routine'),
    ('phase03a_alternate_visit', 'pat_01', 'pat_a', CRITICAL_TEXT, 'alternate_critical'),
)


def install(app):
    """Only explicit fixture setup; respects collisions and never rewrites an intake."""
    if not synthetic_enabled(app.config):
        raise ValueError('Synthetic fixture requires synthetic_dev')
    now = datetime.now(timezone.utc)
    with app.extensions['cc_session_factory'].begin() as db:
        for cid, uid, pid, text, _ in FIXTURES:
            person = db.get(User, uid)
            doctor = db.get(User, 'doc_psy')
            if not person or person.patient_id != pid or not doctor or person.organization_id != doctor.organization_id:
                raise ValueError('Canonical synthetic graph missing')
            existing = db.get(PrevisitCase, cid)
            if existing:
                if (existing.patient_user_id, existing.doctor_id, existing.intake_json) != (uid, doctor.id, json.dumps({'text': text}, ensure_ascii=False)):
                    raise ValueError('Unowned fixture collision')
                continue
            db.add(PrevisitCase(id=cid, patient_user_id=uid, doctor_id=doctor.id,
                status='submitted', intake_json=json.dumps({'text': text}, ensure_ascii=False),
                created_at=now.isoformat(), allowed_until=(now+timedelta(days=30)).isoformat(),
                consent_version='case-1', first_patient_message=1, doctor_replied=0))
