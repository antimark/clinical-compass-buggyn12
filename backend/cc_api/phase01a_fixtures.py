"""Small additive graph; reuse existing personas, never seed a second D01 user."""
import json
from sqlalchemy import select
from werkzeug.security import generate_password_hash
from .models import User, Checkin
from .extension_models import Audit, Message, PrevisitCase
from .onboarding_models import LocalIdentity


def seed_phase01a(session):
    with session.begin() as db:
        if db.get(Audit, 'phase01a_graph_v1'):
            return
        for model, key in ((User, 'doc_gp'), (Checkin, 'phase01a_critical_source'),
                           (Message, 'msg_demo_01'), (Message, 'msg_demo_02')):
            if db.get(model, key):
                raise ValueError('Unowned Phase01A ID collision: ' + key)
        db.add(User(id='doc_gp', display_name='Демо терапевт', role='doctor',
                    specialty='general_practice', organization_id='org_demo'))
        db.flush()
        db.add(LocalIdentity(user_id='doc_gp', email='doc_gp@demo.test',
            password_hash=generate_password_hash('Synthetic-demo-pass-42'),
            email_provider='synthetic_seed', email_status='verified_synthetic', created_at='2026-10-26T09:00:00Z'))
        db.add(Checkin(id='phase01a_critical_source', patient_id='pat_a', mood_score=2,
            comparison='worse', note='Изолированный синтетический тест сигнала SYNTHETIC_TEST_TRIGGER; не клиническое правило.',
            recorded_at='2026-10-17T11:00:00Z'))
        case = db.get(PrevisitCase, 'dx_fixture_incoming_case')
        if not case or case.patient_user_id != 'pxu_history_02' or case.doctor_id != 'doc_psy':
            raise ValueError('Authoritative case graph missing or inconsistent')
        for ident, sender, recipient, text in (
            ('msg_demo_01', 'pxu_history_02', 'doc_psy', 'Синтетический пример: хочу обсудить сон и справочную карточку Авиандра. Это не запрос назначения.'),
            ('msg_demo_02', 'doc_psy', 'pxu_history_02', 'Синтетический ответ: обсудим вопросы на встрече; назначения не создавались.')):
            db.add(Message(id=ident, thread_type='previsit', context_id=case.id, sender_id=sender,
                           recipient_id=recipient, text=text, created_at='2026-10-26T09:00:00Z'))
        db.add(Audit(id='phase01a_graph_v1', actor='doc_psy', action='synthetic_dataset_seeded',
                     object_type='synthetic_fixture', object_id='phase01a', created_at='2026-10-26T09:00:00Z'))
