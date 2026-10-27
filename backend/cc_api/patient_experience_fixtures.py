"""Opt-in synthetic accounts; each marker is seeded once and never reset."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from werkzeug.security import generate_password_hash
from .models import User, Patient, DoctorPatientLink
from .onboarding_models import LocalIdentity, PatientOnboarding, PatientInvitation, PatientConsent, PreparedOnboardingDraft
from .extension_models import PrevisitCase, Appointment
from .p0_models import CarePlan, PlanItem, PlanEvent
from .patient_experience_models import (MetricObservation, DemoQuestionnaireDefinition,
    DemoQuestionnaireAssignment, DemoQuestionnaireDraft, DemoQuestionnaireSubmission, SyntheticPersona)
from .demo_questionnaires import DEFINITIONS, evaluation_definitions, score_answers

FIXTURE_PASSWORD = 'Synthetic-demo-pass-42'


def seed_patient_experience(SessionLocal, include_personas=False):
    with SessionLocal.begin() as db:
        for definition in DEFINITIONS + evaluation_definitions():
            if not db.get(DemoQuestionnaireDefinition, definition['id']):
                db.add(DemoQuestionnaireDefinition(id=definition['id'], version=definition['version'],
                    language=definition['language'], status=definition['status'], title=definition['title'],
                    definition_json=json.dumps(definition, ensure_ascii=False)))
        db.flush()
        if not include_personas:
            return
        doctor = db.get(User, 'doc_psy')
        if not doctor or doctor.role != 'doctor':
            return
        # Fixed dates ensure reproducible synthetic historical trajectories, never invented future availability.
        origin = datetime(2026, 1, 5, 10, tzinfo=timezone.utc)
        def stamp(day=0):
            return (origin + timedelta(days=day)).isoformat().replace('+00:00', 'Z')
        names = ['Анна Соколова', 'Михаил Волков', 'Елена Морозова', 'Дмитрий Орлов', 'Мария Лебедева',
            'Алексей Соколов', 'Ольга Козлова', 'Иван Новиков', 'Наталья Попова', 'Сергей Васильев',
            'Татьяна Смирнова', 'Павел Михайлов', 'Ирина Фёдорова', 'Андрей Зайцев', 'Светлана Павлова']
        keys = ['trend_one', 'trend_two', 'invited_empty'] + [f'history_{i:02}' for i in range(1, 13)]
        password_hash = None
        for index, key in enumerate(keys):
            uid, pid = 'pxu_' + key, 'pxp_' + key
            if db.get(SyntheticPersona, uid):
                continue
            # Refuse collisions rather than overwrite an account lacking the marker.
            email = key + '@demo.test'
            if db.get(User, uid) or db.get(Patient, pid) or db.scalar(select(LocalIdentity).where(LocalIdentity.email == email)):
                continue
            display = names[index] + ' (демо)'
            description = ('Одно сохранённое наблюдение; график появится после второго.' if key == 'trend_one' else
                'Два сопоставимых наблюдения и черновик опросника из 15 вопросов.' if key == 'trend_two' else
                'Приглашение принято; собственных наблюдений пока нет.' if key == 'invited_empty' else
                f'Синтетическая история {index - 2}: наблюдения, технический опросник и общий план активности.')
            db.add(Patient(id=pid, display_name=display, diagnosis_label='', medication_label='', severity_label='',
                trend='insufficient_data', last_activity_at=stamp(10 + index) if key != 'invited_empty' else None))
            db.flush()
            db.add(User(id=uid, display_name=display, role='patient', specialty=None,
                organization_id=doctor.organization_id, patient_id=pid, external_subject=None))
            db.flush()
            if password_hash is None:
                password_hash = generate_password_hash(FIXTURE_PASSWORD)
            db.add(LocalIdentity(user_id=uid, email=email, password_hash=password_hash,
                email_provider='synthetic_auto', email_status='verified_synthetic', created_at=stamp()))
            db.add(PatientOnboarding(user_id=uid, status='completed', introduction_seen=1, updated_at=stamp()))
            clinician_id = 'doc_ther' if index >= 3 and index % 2 and db.get(User, 'doc_ther') else doctor.id
            db.add(DoctorPatientLink(doctor_id=clinician_id, patient_id=pid, categories='symptoms'))
            invitation_id = 'pxinv_' + key
            db.add(PatientInvitation(id=invitation_id, token_hash=hashlib.sha256(('fixture-used-' + key).encode()).hexdigest(),
                issuer_id=clinician_id, recipient_hash=hashlib.sha256(email.encode()).hexdigest(), organization_id=doctor.organization_id,
                categories='symptoms', status='accepted', created_at=stamp(), expires_at=stamp(7), accepted_at=stamp(1),
                revoked_at=None, patient_user_id=uid))
            db.flush()
            db.add(PatientConsent(id='pxcons_' + key, patient_user_id=uid, doctor_id=clinician_id,
                invitation_id=invitation_id, categories='symptoms', version='clinical-link-v1', accepted_at=stamp(1), revoked_at=None))
            state = 'invited' if key == 'invited_empty' else 'history'
            db.add(SyntheticPersona(user_id=uid, persona_key=key, description=description, state=state))
            count = 1 if key == 'trend_one' else 2 if key == 'trend_two' else 0 if key == 'invited_empty' else 3 + index % 6
            for j in range(count):
                db.add(MetricObservation(id=f'obs_fixture_{key}_{j}', patient_id=pid, metric_key='wellbeing', unit='points',
                    scale_version='mood_1_5_v1', value=1 + (index + j * 2) % 5, observed_at=stamp(2 + j * 3),
                    recorded_at=stamp(2 + j * 3), source='synthetic_fixture', event_key=f'fixture_{key}_{j}'))
            if key != 'invited_empty':
                definition = DEFINITIONS[1 if key == 'trend_two' or index % 2 else 0]
                aid = 'dq_fixture_' + key
                completed = key.startswith('history_')
                answers = ({q['id']: 1 + (index + i) % 4 for i, q in enumerate(definition['questions'])}
                    if completed else {'q1': 2, 'q2': 3} if key == 'trend_two' else {})
                db.add(DemoQuestionnaireAssignment(id=aid, patient_id=pid, clinician_id=clinician_id,
                    definition_id=definition['id'], definition_version='1', status='submitted' if completed else 'assigned', created_at=stamp(2)))
                db.flush()
                db.add(DemoQuestionnaireDraft(assignment_id=aid, answers_json=json.dumps(answers), last_page=0,
                    revision=3 if completed else 2 if key == 'trend_two' else 0, updated_at=stamp(10)))
                if completed:
                    db.add(DemoQuestionnaireSubmission(id='ds_fixture_' + key, assignment_id=aid, definition_id=definition['id'],
                        definition_version='1', definition_snapshot_json=json.dumps(definition, ensure_ascii=False), answers_json=json.dumps(answers),
                        score=score_answers(definition, answers), submitted_at=stamp(10 + index), idempotency_key='fixture_' + key))
                    plan_id = 'pxplan_' + key
                    db.add(CarePlan(id=plan_id, patient_id=pid, clinician_id=clinician_id, status='active', version=1, created_at=stamp(1)))
                    db.flush()
                    item_id = 'pxitem_' + key
                    db.add(PlanItem(id=item_id, plan_id=plan_id, item_type='activity', title='Демо: заполнить личную заметку о дне',
                        scheduled_at=None, frequency='по желанию', completion_criteria='Отметка пользователя', created_at=stamp(1)))
                    db.flush()
                    if index % 3:
                        db.add(PlanEvent(id='pxevent_' + key, item_id=item_id, patient_user_id=uid,
                            outcome='completed', reported_at=stamp(10 + index)))
                    db.add(PreparedOnboardingDraft(id='pxnote_' + key, invitation_id=invitation_id, clinician_id=clinician_id,
                        content='Синтетический пример опубликованной записи: обсудили использование личного дневника. Медицинские заключения отсутствуют.',
                        state='published', version=1, created_at=stamp(3), signed_at=stamp(4), published_at=stamp(5)))
                    case_id = 'pxcase_' + key
                    db.add(PrevisitCase(id=case_id, patient_user_id=uid, doctor_id=clinician_id, status='submitted',
                        intake_json=json.dumps({'subject': 'Синтетическая встреча', 'message': 'Демонстрация истории активности'}),
                        created_at=stamp(1), allowed_until=stamp(30), consent_version='case-1', first_patient_message=1, doctor_replied=1))
                    db.add(Appointment(id='pxappt_' + key, case_id=case_id, doctor_id=clinician_id, patient_user_id=uid,
                        proposed_at=stamp(7 + index), format='video', status='completed' if index % 3 else 'cancelled'))
