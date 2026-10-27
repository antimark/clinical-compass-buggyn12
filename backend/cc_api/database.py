"""SQLAlchemy connection, schema migration and session factory setup.

This module deliberately preserves automatic Alembic upgrades and the refusal
of legacy unversioned databases; it never drops or recreates existing tables.
"""
from __future__ import annotations
import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def initialize_database(app, project_root):
    # Shared SQLAlchemy model/API code for SQLite demo and an opt-in PostgreSQL
    # integration profile. PostgreSQL has NOT been tested in this environment.
    database_url=os.environ.get('CC_DATABASE_URL')
    if database_url:
        if not (database_url.startswith('postgresql+psycopg://') or database_url.startswith('sqlite:///')):
            raise RuntimeError('CC_DATABASE_URL must use postgresql+psycopg or sqlite for this prototype')
        if database_url.startswith('sqlite:///'):
            Path(database_url[len('sqlite:///'):]).parent.mkdir(parents=True,exist_ok=True)
    else:
        database_file = Path(app.config['DB_PATH'])
        database_file.parent.mkdir(parents=True, exist_ok=True)
        database_url = f'sqlite:///{database_file}'
    is_sqlite=database_url.startswith('sqlite:///')
    engine = create_engine(database_url,pool_pre_ping=True,hide_parameters=True,
                           **({'connect_args':{'timeout':20}} if is_sqlite else {}))

    if is_sqlite:
        @event.listens_for(engine, 'connect')
        def configure_sqlite(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute('PRAGMA foreign_keys=ON')
            cursor.execute('PRAGMA busy_timeout=20000')
            cursor.execute('PRAGMA journal_mode=WAL')
            cursor.close()

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect
    db_has_tables = inspect(engine).has_table('users')
    db_has_version = inspect(engine).has_table('alembic_version')
    if db_has_tables and not db_has_version:
        raise RuntimeError('Unversioned legacy database detected. Back it up and migrate manually; do not silently overwrite patient data.')
    config = Config(str(project_root / 'alembic.ini'))
    config.set_main_option('script_location', str(project_root / 'migrations'))
    config.set_main_option('sqlalchemy.url', database_url.replace('%', '%%'))
    command.upgrade(config, 'head')
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    app.extensions['cc_session_factory'] = SessionLocal
    return SessionLocal
