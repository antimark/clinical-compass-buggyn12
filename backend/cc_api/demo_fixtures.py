"""Synthetic-only initial data, with original fixture IDs and authorization rules."""
from __future__ import annotations
import os
import hmac
import hashlib
from .models import Alert, DoctorPatientLink, Patient, User
from .utilities import utc_now


def initialize_demo_fixtures(app, SessionLocal):
    if not app.config.get('AUTO_SEED_DEMO', True):
        # Evaluation sandboxes deliberately do not seed accounts or patients;
        # questionnaire *definitions* must still exist on a fresh workspace.
        from .verification import workspace_enabled
        if workspace_enabled(app.config):
            from .patient_experience_fixtures import seed_patient_experience
            seed_patient_experience(SessionLocal, include_personas=False)
            # Immutable bundled references/rules contain no patients or accounts.
            # Keep exact ICD assistance available in fresh evaluation workspaces.
            from .medical_references import seed_medical_references
            seed_medical_references(SessionLocal)
        return
    if app.config['DEMO_MODE']:
        seed_demo(SessionLocal)
        # Preserve the original fixed synthetic researcher's existing study
        # permission once; never restore an explicitly withdrawn grant.
        from .research_workflow_service import provision_grant
        from .extension_models import Audit
        with SessionLocal.begin() as db:
            researcher = db.get(User, 'researcher_01')
            if researcher and not db.get(Audit, 'phase5_research_fixture_access_v1'):
                provision_grant(db, researcher)
                db.add(Audit(id='phase5_research_fixture_access_v1', actor=researcher.id,
                    action='legacy_study_permission_migrated', object_type='study',
                    object_id='study_demo_v1', created_at=utc_now()))
    if app.config['DEMO_MODE'] and app.config['APP_ENV'] == 'synthetic_dev':
        from .demo_accounts import seed_demo_accounts
        seed_demo_accounts(SessionLocal)
        from .patient_experience_fixtures import seed_patient_experience
        seed_patient_experience(SessionLocal, include_personas=app.config['SEED_PATIENT_PERSONAS'])
        from .doctor_experience_fixtures import seed_doctor_experience
        seed_doctor_experience(SessionLocal, include_personas=app.config['SEED_PATIENT_PERSONAS'])
        from .medical_references import seed_medical_references
        seed_medical_references(SessionLocal)
        from .clinical_workflow_fixtures import seed_clinical_workflow_fixtures
        seed_clinical_workflow_fixtures(SessionLocal, include_personas=app.config['SEED_PATIENT_PERSONAS'])


def seed_demo(SessionLocal):
    with SessionLocal.begin() as db:
        if db.get(User, 'doc_psy'):
            return
        db.add_all([
            User(id='doc_psy', display_name='Демо психиатр', role='doctor', specialty='psychiatry', organization_id='org_demo'),
            User(id='doc_ther', display_name='Демо психотерапевт', role='doctor', specialty='psychotherapy', organization_id='org_demo'),
            User(id='doc_other', display_name='Доктор другой клиники (демо)', role='doctor', specialty='psychiatry', organization_id='org_other'),
            User(id='pat_01', display_name='Демо пациент', role='patient', specialty=None, organization_id='org_demo', patient_id='pat_a'),
            User(id='pat_02', display_name='Демо пациент Б', role='patient', specialty=None, organization_id='org_other', patient_id='pat_b'),
            User(id='pat_03', display_name='Новый пациент (без связи)', role='patient', specialty=None, organization_id='org_demo', patient_id='pat_c'),
            User(id='clinic_01', display_name='Демо администратор', role='clinic_admin', specialty=None, organization_id='org_demo'),
            User(id='researcher_01', display_name='Демо исследователь', role='researcher', specialty=None, organization_id='org_demo'),
            User(id='platform_01', display_name='Администратор платформы (синтетический)', role='platform_admin', specialty=None, organization_id='platform'),
            Patient(id='pat_a', display_name='Алексей Демонстрационный', diagnosis_label='Синтетический случай A', medication_label='Учебный препарат X', severity_label='умеренная', trend='worse', last_activity_at='2026-10-17T10:00:00Z'),
            Patient(id='pat_b', display_name='Мария Демонстрационная', diagnosis_label='Синтетический случай B', medication_label='Учебный препарат Y', severity_label='лёгкая', trend='stable', last_activity_at='2026-10-16T10:00:00Z'),
            Patient(id='pat_c', display_name='Только по приглашению', diagnosis_label='Без диагноза', medication_label='Нет данных', severity_label='не оценено', trend='insufficient_data', last_activity_at=None),
        ])
        # SQLAlchemy may insert Alert before its referenced User/Patient when
        # only scalar foreign-key IDs (not ORM relationships) are supplied.
        # Persist parents first, but keep all fixture creation atomic.
        db.flush()
        db.add_all([
            DoctorPatientLink(doctor_id='doc_psy', patient_id='pat_a', categories='symptoms,diagnosis,medications,severity'),
            DoctorPatientLink(doctor_id='doc_ther', patient_id='pat_a', categories='symptoms,diagnosis'),
            Alert(id='al_001', assigned_doctor_id='doc_psy', patient_id='pat_a', severity='critical', status='open', reason_code='SYNTHETIC_TEST_TRIGGER', created_at='2026-10-17T12:00:00Z'),
        ])
        from .extension_models import ResearchObservation, IdentityVault
        import hashlib
        for uid_, org in [('pat_01','org_demo'), ('pat_02','org_other'), ('pat_03','org_demo')]:
            db.add(IdentityVault(user_id=uid_, verified_subject='synthetic:' + uid_,
                                 synthetic_contact=uid_ + '@example.invalid', organization_id=org))
        key = os.environ.get('CC_STUDY_DEMO_KEY', 'SYNTHETIC_ONLY_NOT_A_RESEARCH_KEY').encode()
        for cohort in ('A', 'B'):
            for n in range(12):
                source_identity = f'{cohort}-{n:03}'
                pseudonym = hmac.new(key, f'study_demo_v1:{source_identity}'.encode(), hashlib.sha256).hexdigest()[:20]
                db.add(ResearchObservation(id='obs_' + cohort + str(n), study_id='study_demo_v1',
                     study_subject=pseudonym, cohort=cohort, measure='synthetic_mood',
                     value=None if n in (4, 9) else (2 + (n % 3) + (1 if cohort == 'A' else 0)),
                     source='reproducible_synthetic_fixture_v1', recorded_at='2026-10-17T12:00:00Z'))
