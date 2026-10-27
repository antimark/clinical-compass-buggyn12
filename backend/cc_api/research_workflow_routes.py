"""Research API: owned definitions, current grants and aggregate-only releases."""
from functools import wraps
from flask import abort, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .p0_models import DatasetDefinition
from .research_workflow_models import ResearchDefinitionRevision as Revision, ResearchStudyGrant as Grant
from . import research_workflow_service as s

BASE = '/api/v1/research-workflow'


def register_research_workflow_routes(app, SessionLocal, current_user, require_role, error, utc_now):
    @app.errorhandler(s.ResearchFailure)
    def research_workflow_failure(exc):
        return error(exc.status, exc.code, exc.message)

    @app.after_request
    def research_no_store(response):
        if request.path.startswith(BASE + '/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def conflict_guard(fn):
        @wraps(fn)
        def guarded(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except IntegrityError:
                return error(409, 'RESEARCH_CONFLICT', 'Определение изменилось; обновите страницу')
        return guarded

    def actor(db):
        user = current_user(db)
        if user is None:
            abort(401)
        return user

    def body(keys):
        value = request.get_json(silent=True)
        if not isinstance(value, dict) or set(value) - set(keys):
            abort(422)
        return value

    def selected_version():
        value = request.args.get('version')
        if value is None:
            return None
        try:
            version = int(value)
            if version < 1:
                raise ValueError()
            return version
        except ValueError:
            abort(422)

    @app.get(BASE + '/sources')
    def research_sources():
        with SessionLocal() as db:
            user = s.actor(db, actor(db))
            grant = db.get(Grant, (user.id, s.STUDY, user.organization_id), populate_existing=True)
            return {'items': ([{'id': s.STUDY, 'measures': [s.MEASURE], 'cohorts': ['A', 'B'],
                'criteria_tags': sorted(s.TAGS), 'minimum_cell': 5}] if grant and grant.active else []),
                'synthetic_only': True, 'limitation': s.LIMITATION}

    @app.post(BASE + '/grants')
    @conflict_guard
    def research_grant():
        data = body(('researcher_id', 'study_id', 'active'))
        with SessionLocal.begin() as db:
            return s.set_grant(db, actor(db), data.get('researcher_id'), data.get('study_id'), data.get('active'))

    @app.get(BASE + '/definitions')
    def research_definitions():
        with SessionLocal() as db:
            user = s.actor(db, actor(db))
            rows = db.scalars(select(DatasetDefinition).where(DatasetDefinition.researcher_id == user.id)
                .order_by(DatasetDefinition.created_at, DatasetDefinition.id)).all()
            allowed = []
            for row in rows:
                grant = db.get(Grant, (user.id, row.study_id, user.organization_id), populate_existing=True)
                if grant and grant.active and row.study_id == s.STUDY:
                    allowed.append(s.definition_payload(row))
            return {'items': allowed, 'synthetic_only': True}

    @app.post(BASE + '/definitions')
    @conflict_guard
    def research_create_definition():
        data = body(('study_id', 'measure', 'cohorts', 'start_date', 'end_date', 'criteria', 'min_cell'))
        with SessionLocal.begin() as db:
            result = s.create_definition(db, actor(db), data)
        return result, 201

    @app.get(BASE + '/definitions/<definition_id>')
    def research_definition(definition_id):
        with SessionLocal() as db:
            row, version, config = s.get_version(db, actor(db), definition_id, selected_version())
            return s.definition_payload(row, config, version)

    @app.put(BASE + '/definitions/<definition_id>')
    @conflict_guard
    def research_edit_definition(definition_id):
        data = body(('study_id', 'measure', 'cohorts', 'start_date', 'end_date', 'criteria', 'min_cell', 'revision'))
        revision = data.pop('revision', None)
        with SessionLocal.begin() as db:
            return s.update_definition(db, actor(db), definition_id, data, revision)

    @app.get(BASE + '/definitions/<definition_id>/versions')
    def research_definition_versions(definition_id):
        with SessionLocal() as db:
            row = s.own_definition(db, actor(db), definition_id)
            return {'id': row.id, 'items': [{'version': r.version, 'created_at': r.created_at}
                for r in db.scalars(select(Revision).where(Revision.definition_id == row.id).order_by(Revision.version)).all()]}

    @app.get(BASE + '/definitions/<definition_id>/compute')
    @app.get(BASE + '/definitions/<definition_id>/export')
    @conflict_guard
    def research_compute(definition_id):
        with SessionLocal.begin() as db:
            return s.compute(db, actor(db), definition_id, app.config['SECRET_KEY'], selected_version())
