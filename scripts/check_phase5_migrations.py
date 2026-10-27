"""Disposable SQLite migration roundtrip; never touches the review database."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from cc_api import create_app
from cc_api.models import User
from cc_api.onboarding_models import LocalIdentity
from cc_api.patient_experience_models import MetricObservation


def main():
    if os.environ.get('CC_DATABASE_URL'):
        raise RuntimeError('Unset CC_DATABASE_URL: this check may target only its own temporary SQLite database')
    with TemporaryDirectory(prefix='cc_phase5_migration_') as folder:
        path = Path(folder) / 'roundtrip.sqlite'
        app = create_app({'TESTING': True, 'DEMO_MODE': True, 'APP_ENV': 'synthetic_dev',
            'SEED_PATIENT_PERSONAS': True, 'DB_PATH': str(path)})
        factory = app.extensions['cc_session_factory']
        queries = [
            select(User.id, User.display_name, User.organization_id, User.patient_id).order_by(User.id),
            select(LocalIdentity.user_id, LocalIdentity.email, LocalIdentity.password_hash).order_by(LocalIdentity.user_id),
            select(MetricObservation.id, MetricObservation.value, MetricObservation.observed_at).order_by(MetricObservation.id),
        ]
        with factory() as db:
            before = [db.execute(query).all() for query in queries]
        config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
        config.set_main_option('sqlalchemy.url', 'sqlite:///' + str(path))
        command.downgrade(config, '0004_patient_experience')
        command.upgrade(config, 'head')
        with factory() as db:
            assert before == [db.execute(query).all() for query in queries]
            assert db.execute(text('PRAGMA foreign_key_check')).all() == []
            assert db.execute(text('select version_num from alembic_version')).scalar() == '0014_staff_enrollment'
        print('PASS SQLite0014→0004→0014: users, local identities and Phase3 observations preserved; foreign_key_check empty.')
        print('Disposable DB only. Legacy plan projections retained; real rollback requires backup restoration. PostgreSQL NOT_RUN.')


if __name__ == '__main__':
    main()
