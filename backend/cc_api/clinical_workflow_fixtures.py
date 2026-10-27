"""Opt-in, seed-once clinical personas; never modify an existing patient's grant."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from werkzeug.security import generate_password_hash
from .models import User, Patient, DoctorPatientLink, Checkin
from .extension_models import Audit, PrevisitCase, Message
from .onboarding_models import LocalIdentity, PatientOnboarding, PatientInvitation, PatientConsent
from .patient_experience_models import (SyntheticPersona, MetricObservation, DemoQuestionnaireAssignment,
    DemoQuestionnaireDraft, DemoQuestionnaireSubmission)
from .clinical_workflow_models import ClinicalDocument, MedicationAdherence
from .doctor_experience_models import PhysicianPriority
from .physician_history_models import PhysicianProfile
from .p0_models import AdverseEvent, PlanEvent, UserNotification
from .clinical_workflow_services import (validate_content, signature, synchronize_orders,
    append_revision, publish_plan, authorize_scopes)
from .medical_references import load_bundled_references, resolve_medication_reference
from .demo_questionnaires import DEFINITIONS, score_answers
from .icd10 import ICD_VERSION

PASSWORD = 'Synthetic-demo-pass-42'
SCOPES = 'symptoms,diagnosis,medications'
PERSONAS = (
    ('clinical_care', 'Вера Андреевна Крылова', [5, 4, 2], 10,
        'Синтетический пример текущего наблюдения: изменение самооценки, заполненный технический опросник, опубликованный план и разные самоотчёты.'),
    ('clinical_history', 'Артём Сергеевич Беляев', [2, 3, 3, 4, 3, 4, 4, 3], 15,
        'Синтетический пример расширенной истории: наблюдения, технический опросник из 15 вопросов, план, опубликованные и закрытые врачебные записи.'),
)


def seed_clinical_workflow_fixtures(SessionLocal, include_personas=False):
    if not include_personas:
        return
    bundled = {entry['id']: entry for entry in load_bundled_references()}
    ref = bundled['cipralex_escitalopram_10mg']
    metadata = resolve_medication_reference(ref['id'], ref['version'])
    origin = datetime(2026, 4, 5, 10, tzinfo=timezone.utc)
    def stamp(day=0):
        return (origin + timedelta(days=day)).isoformat().replace('+00:00', 'Z')
    with SessionLocal.begin() as db:
        doctor = db.get(User, 'doc_psy')
        if not doctor:
            return
        for physician_id, full_name in (('doc_psy', 'Сергей Игоревич Соколов (демо)'),
                ('doc_ther', 'Ольга Викторовна Крылова (демо)')):
            if db.get(User, physician_id) and not db.get(PhysicianProfile, physician_id):
                db.add(PhysicianProfile(user_id=physician_id, full_name=full_name, synthetic=1))
        for key, name, values, count, description in PERSONAS:
            marker = 'cw_fixture_' + key + '_v1'
            if db.get(Audit, marker):
                continue
            user_id, patient_id, email = 'pxu_' + key, 'pxp_' + key, key + '@demo.test'
            # A collision is not permission to repair or overwrite somebody's data.
            if (db.get(User, user_id) or db.get(Patient, patient_id)
                    or db.scalar(select(LocalIdentity).where(LocalIdentity.email == email))):
                raise ValueError('Clinical fixture identity collision: ' + key)
            display = name + ' (демо)'
            db.add(Patient(id=patient_id, display_name=display, diagnosis_label='', medication_label='',
                severity_label='', trend='insufficient_data', last_activity_at=stamp(20)))
            db.flush()
            person = User(id=user_id, display_name=display, role='patient', specialty=None,
                organization_id=doctor.organization_id, patient_id=patient_id, external_subject=None)
            db.add(person)
            db.flush()
            db.add(LocalIdentity(user_id=user_id, email=email, password_hash=generate_password_hash(PASSWORD),
                email_provider='synthetic_auto', email_status='verified_synthetic', created_at=stamp()))
            db.add(PatientOnboarding(user_id=user_id, status='completed', introduction_seen=1, updated_at=stamp(1)))
            db.add(SyntheticPersona(user_id=user_id, persona_key=key, description=description, state='history'))
            invitation_id = 'cwinv_' + key
            db.add(PatientInvitation(id=invitation_id,
                token_hash=hashlib.sha256(('used-clinical-fixture-' + key).encode()).hexdigest(),
                issuer_id=doctor.id, recipient_hash=hashlib.sha256(email.encode()).hexdigest(),
                organization_id=doctor.organization_id, categories=SCOPES, status='accepted',
                created_at=stamp(), expires_at=stamp(7), accepted_at=stamp(1), revoked_at=None, patient_user_id=user_id))
            db.flush()
            db.add(PatientConsent(id='cwcons_' + key, patient_user_id=user_id, doctor_id=doctor.id,
                invitation_id=invitation_id, categories=SCOPES, version='clinical-link-v1',
                accepted_at=stamp(1), revoked_at=None))
            db.add(DoctorPatientLink(doctor_id=doctor.id, patient_id=patient_id, categories=SCOPES))
            db.flush()
            authorize_scopes(db, doctor, patient_id, SCOPES)
            for index, value in enumerate(values):
                ident = f'cwobs_{key}_{index}'
                db.add(MetricObservation(id=ident, patient_id=patient_id, metric_key='wellbeing', unit='points',
                    scale_version='mood_1_5_v1', value=value, observed_at=stamp(2 + index * 2),
                    recorded_at=stamp(2 + index * 2), source='synthetic_fixture', event_key=ident))
            definition = next(d for d in DEFINITIONS if len(d['questions']) == count)
            aid = 'dq_fixture_' + key
            answers = {q['id']: 1 + index % 4 for index, q in enumerate(definition['questions'])}
            db.add(DemoQuestionnaireAssignment(id=aid, patient_id=patient_id, clinician_id=doctor.id,
                definition_id=definition['id'], definition_version=definition['version'], status='submitted', created_at=stamp(2)))
            db.flush()
            db.add(DemoQuestionnaireDraft(assignment_id=aid, answers_json=json.dumps(answers), last_page=0,
                revision=count, updated_at=stamp(18)))
            db.add(DemoQuestionnaireSubmission(id='ds_fixture_' + key, assignment_id=aid,
                definition_id=definition['id'], definition_version=definition['version'],
                definition_snapshot_json=json.dumps(definition, ensure_ascii=False), answers_json=json.dumps(answers),
                score=score_answers(definition, answers), submitted_at=stamp(18), idempotency_key='fixture_' + key))

            def document(suffix, kind, raw, final_state, day, mode='quick'):
                content, scopes = validate_content(kind, mode, raw)
                authorize_scopes(db, doctor, patient_id, scopes)
                row = ClinicalDocument(id='cdoc_fixture_' + key + '_' + suffix, patient_id=patient_id,
                    clinician_id=doctor.id, kind=kind, mode=mode, content_json=json.dumps(content, ensure_ascii=False),
                    required_scopes=scopes, status='draft', revision=1, parent_id=None, amendment_reason=None,
                    signed_hash=None, created_at=stamp(day), updated_at=stamp(day), signed_at=None, published_at=None)
                db.add(row)
                db.flush()
                synchronize_orders(db, row, stamp(day))
                append_revision(db, row, doctor, 'create', stamp(day))
                if final_state in ('signed', 'published'):
                    row.signed_hash = signature(row)
                    row.status, row.revision = 'signed', 2
                    row.signed_at = row.updated_at = stamp(day + 1)
                    append_revision(db, row, doctor, 'sign', stamp(day + 1))
                if final_state == 'published':
                    row.status, row.revision = 'published', 3
                    row.published_at = row.updated_at = stamp(day + 2)
                    append_revision(db, row, doctor, 'publish', stamp(day + 2))
                    publish_plan(db, row, stamp(day + 2))
                    db.add(UserNotification(id='cwn_' + key + '_' + suffix, recipient_id=user_id,
                        text='Демо: специалист явно опубликовал синтетическую запись', category='record', created_at=stamp(day + 2)))
                db.flush()
                return row

            diagnosis = dict(code='F32', version=ICD_VERSION,
                status='preliminary' if key == 'clinical_care' else 'confirmed')
            document('published', 'encounter', dict(narrative='Синтетическая запись: обсудили собственные наблюдения и работу с дневником. Это учебные данные, не медицинская оценка реального человека.',
                assessment='Синтетический пример врачебного текста. Технический опросник не интерпретируется как клиническая шкала.',
                follow_up='Обсудить новые записи на согласованной встрече.', diagnoses=[diagnosis]), 'published', 8, mode='extended')
            plan = document('plan', 'treatment', dict(items=[
                dict(item_type='medication', title=metadata['title'] + ' — синтетическая врачебная запись',
                    reference_id=metadata['id'], reference_version=metadata['version'],
                    notes='Технический пример, созданный от имени демонстрационного врача. Режим и дозировка не заданы; не является инструкцией к применению.'),
                dict(item_type='behavioral', title='Демо: вести личные заметки о дне', frequency='по желанию',
                    notes='Общая синтетическая активность для проверки самоотчётов.')]), 'published', 10)
            document('signed', 'encounter', dict(narrative='Синтетическая подписанная запись, пока не опубликованная пациенту.'), 'signed', 14)
            document('draft', 'encounter', dict(narrative='Приватный синтетический черновик врача; пациенту недоступен.'), 'draft', 16)
            oid = 'mord_' + plan.id.removeprefix('cdoc_') + '_0'
            for index, outcome in enumerate(('completed', 'missed', 'partial') if key == 'clinical_care' else ('completed', 'completed', 'completed', 'uncertain')):
                db.add(MedicationAdherence(id=f'cwrep_{key}_{index}', order_id=oid, patient_user_id=user_id,
                    outcome=outcome, note='Синтетический самоотчёт для проверки истории; не оценка эффективности.', recorded_at=stamp(15 + index)))
            activity_id = 'citem_' + plan.id.removeprefix('cdoc_') + '_1'
            db.add(PlanEvent(id='cwactivity_' + key, item_id=activity_id, patient_user_id=user_id,
                outcome='completed' if key == 'clinical_history' else 'missed', reported_at=stamp(19)))
            db.add(PhysicianPriority(doctor_id=doctor.id, patient_id=patient_id,
                priority=2 if key == 'clinical_care' else 1, note='Синтетический вручную заданный приоритет врача; не вычислен по сигналам.',
                revision=1, updated_at=stamp(19)))
            if key == 'clinical_care':
                db.add(Checkin(id='cwconcern_' + key, patient_id=patient_id, mood_score=2, comparison='worse',
                    note='Синтетическое сообщение пациента: хочу обсудить последние изменения отметок.', recorded_at=stamp(20)))
                db.add(AdverseEvent(id='cw_adverse_' + key, patient_id=patient_id, reporter_id=user_id,
                    description='Синтетическое сообщение о нежелательном событии для проверки интерфейса; причинная связь не установлена.',
                    status='reported', review_text=None, reviewer_id=None, created_at=stamp(20), reviewed_at=None))
            now = datetime.now(timezone.utc)
            db.add(PrevisitCase(id='cwcase_' + key, patient_user_id=user_id, doctor_id=doctor.id, status='submitted',
                intake_json=json.dumps({'subject':'Синтетическая встреча', 'message':'Учебное обращение по сохранённым наблюдениям.'}, ensure_ascii=False),
                created_at=(now - timedelta(hours=6)).isoformat().replace('+00:00', 'Z'),
                allowed_until=(now + timedelta(days=30)).isoformat().replace('+00:00', 'Z'),
                consent_version='case-1', first_patient_message=1, doctor_replied=1))
            db.flush()
            for role, sender, recipient, hours, message in (
                    ('patient', user_id, doctor.id, 6, 'Синтетическое обращение: хочу обсудить сохранённые наблюдения.'),
                    ('doctor', doctor.id, user_id, 5, 'Синтетический ответ специалиста: обсудим записи и согласуем время встречи.')):
                db.add(Message(id='cwmsg_' + key + '_' + role, thread_type='previsit', context_id='cwcase_' + key,
                    sender_id=sender, recipient_id=recipient, text=message,
                    created_at=(now - timedelta(hours=hours)).isoformat().replace('+00:00', 'Z')))
            db.add(Audit(id=marker, actor=doctor.id, action='synthetic_clinical_fixture_seeded',
                object_type='synthetic_fixture', object_id=patient_id, created_at=stamp(20)))
