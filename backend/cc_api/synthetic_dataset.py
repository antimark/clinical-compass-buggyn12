"""Managed disposable Phase01A SQLite datasets. No arbitrary DB path interface.

The private filesystem ledger is an operator boundary, not an HTTP capability.
Reset fails closed if ANY recorded row changed or any foreign row appeared.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from sqlalchemy import and_, select
from .models import Base

ROOT = Path('/private/tmp')
PREFIX = 'cc-phase01a-'
DB_NAME = 'synthetic.sqlite'


def guard():
    if os.environ.get('CC_APP_ENV') != 'synthetic_dev' or os.environ.get('CC_DEMO_MODE') != '1':
        raise ValueError('Explicit CC_APP_ENV=synthetic_dev and CC_DEMO_MODE=1 required')
    if os.environ.get('CC_DATABASE_URL') or os.environ.get('CC_DB_PATH'):
        raise ValueError('Database environment overrides forbidden for managed datasets')


def folder(dataset):
    guard()
    if not re.fullmatch(r'[a-z0-9_]{8}', dataset):
        raise ValueError('Expected managed dataset identifier, never a database path')
    path = ROOT / (PREFIX + dataset)
    if path.is_symlink() or not path.is_dir() or path.stat().st_uid != os.getuid():
        raise ValueError('Unowned or missing managed dataset')
    for name in (DB_NAME, 'ownership.json'):
        if (path / name).is_symlink():
            raise ValueError('Symlink forbidden')
    return path


def open_app(path):
    from . import create_app
    return create_app({'DEMO_MODE': True, 'APP_ENV': 'synthetic_dev',
        'SEED_PATIENT_PERSONAS': True, 'AUTO_SEED_DEMO': False,
        'DB_PATH': str(path / DB_NAME), 'SECRET_KEY': os.urandom(32).hex()})


def snapshot(db):
    result = {}
    for table in Base.metadata.sorted_tables:
        records = []
        for row in db.execute(select(table)).mappings():
            key = {col.name: row[col.name] for col in table.primary_key}
            digest = hashlib.sha256(json.dumps(dict(row), sort_keys=True, default=str).encode()).hexdigest()
            records.append({'key': key, 'sha256': digest})
        result[table.name] = sorted(records, key=lambda item: json.dumps(item['key'], sort_keys=True))
    return result


def create_dataset():
    guard()
    path = Path(tempfile.mkdtemp(prefix=PREFIX, dir=ROOT))
    dataset = path.name.removeprefix(PREFIX)
    app = open_app(path)
    session = app.extensions['cc_session_factory']
    # Reuse the authoritative seed graph, including its consent model and IDs.
    from .demo_fixtures import initialize_demo_fixtures
    app.config['AUTO_SEED_DEMO'] = True
    initialize_demo_fixtures(app, session)
    from .phase01a_fixtures import seed_phase01a
    seed_phase01a(session)
    with session() as db:
        rows = snapshot(db)
    ledger = {'version': 1, 'dataset': dataset, 'inode': (path / DB_NAME).stat().st_ino, 'rows': rows}
    (path / 'ownership.json').write_text(json.dumps(ledger, ensure_ascii=False, indent=2))
    session.kw['bind'].dispose()
    return dataset


def operate(dataset, reset=False):
    path = folder(dataset)
    ledger = json.loads((path / 'ownership.json').read_text())
    if ledger['dataset'] != dataset or ledger['version'] != 1 or (path / DB_NAME).stat().st_ino != ledger['inode']:
        raise ValueError('Dataset ownership mismatch')
    app = open_app(path)
    session = app.extensions['cc_session_factory']
    try:
        with session.begin() as db:
            # SQLite reserved writer lock: no concurrent write between verification and deletion.
            from sqlalchemy import text
            db.execute(text('BEGIN IMMEDIATE'))
            if snapshot(db) != ledger['rows']:
                raise ValueError('Dataset changed or contains non-owned rows; reset/seed refused')
            if reset:
                for table in reversed(Base.metadata.sorted_tables):
                    for record in ledger['rows'][table.name]:
                        db.execute(table.delete().where(and_(*(table.c[k] == v for k, v in record['key'].items()))))
        if reset:
            # Reuse this managed database, retaining ownership proof only for newly seeded rows.
            from .demo_fixtures import initialize_demo_fixtures
            app.config['AUTO_SEED_DEMO'] = True
            initialize_demo_fixtures(app, session)
            from .phase01a_fixtures import seed_phase01a
            seed_phase01a(session)
            with session() as db:
                ledger['rows'] = snapshot(db)
            (path / 'ownership.json').write_text(json.dumps(ledger, ensure_ascii=False, indent=2))
        return {'dataset': dataset, 'operation': 'reset' if reset else 'seed',
                'rows': sum(len(v) for v in ledger['rows'].values())}
    finally:
        session.kw['bind'].dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('create', 'seed', 'reset'))
    parser.add_argument('dataset', nargs='?')
    args = parser.parse_args()
    try:
        if args.action == 'create':
            if args.dataset:
                raise ValueError('create chooses a new private directory itself')
            dataset = create_dataset()
            print(json.dumps({'dataset': dataset, 'database': str(folder(dataset) / DB_NAME)}))
        else:
            print(json.dumps(operate(args.dataset or '', reset=args.action == 'reset')))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
