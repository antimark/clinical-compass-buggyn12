"""Role-gated, generic reference reading and clinician-only exact source matches."""
import hashlib
import json
from flask import abort, request, Response
from sqlalchemy import select
from .reference_models import DrugReference, ReferenceMatchRule, TherapyReference
from .medical_references import (compact_reference, detailed_reference, MATCH_LIMITATION,
    REFERENCE_LIMITATION, THERAPY_LIMITATION)
from .icd10 import resolve_icd10, ICD_VERSION, ARCHIVE
from .verification import workspace_enabled

BASE = '/api/v1/references'


def register_reference_routes(app, SessionLocal, current_user, require_role, error, utc_now):
    @app.before_request
    def reference_guard():
        if request.path.startswith(BASE + '/') and request.path != BASE + '/capabilities' and not workspace_enabled(app.config):
            return error(403, 'SYNTHETIC_PROFILE_REQUIRED', 'Доступно только в synthetic_dev')

    def reader(db):
        user = current_user(db)
        if not user:
            abort(401)
        if user.role not in ('patient', 'doctor'):
            abort(403)
        return user

    def reference(db, reference_id):
        version = request.args.get('version')
        if version is not None and (len(version) > 80 or not version):
            abort(422)
        query = select(DrugReference).where(DrugReference.id == reference_id)
        if version:
            query = query.where(DrugReference.version == version)
        else:
            query = query.order_by(DrugReference.imported_at.desc(), DrugReference.version.desc())
        row = db.scalar(query.limit(1))
        if not row:
            abort(404)
        return row

    @app.get(BASE + '/capabilities')
    def ref_capabilities():
        return {'enabled': workspace_enabled(app.config)}

    @app.get(BASE + '/medications')
    def ref_medications():
        query = request.args.get('q', '')
        if len(query) > 100:
            abort(422)
        with SessionLocal() as db:
            reader(db)
            rows = db.scalars(select(DrugReference).order_by(DrugReference.id, DrugReference.imported_at.desc(), DrugReference.version.desc())).all()
            latest = {}
            for row in rows:
                latest.setdefault(row.id, row)
            return {'items': [compact_reference(row) for row in sorted(latest.values(), key=lambda item: item.title.casefold())
                if query.casefold() in (row.title + ' ' + row.inn).casefold()], 'limitation': REFERENCE_LIMITATION}

    @app.get(BASE + '/medications/<reference_id>')
    def ref_medication(reference_id):
        with SessionLocal() as db:
            reader(db)
            return detailed_reference(reference(db, reference_id))

    @app.get(BASE + '/medications/<reference_id>/raw')
    def ref_medication_raw(reference_id):
        with SessionLocal() as db:
            reader(db)
            row = reference(db, reference_id)
            raw = row.raw_original_json.encode('utf-8')
            if hashlib.sha256(raw).hexdigest() != row.import_fingerprint:
                abort(409)
            return Response(raw, mimetype='application/json', headers={
                'Content-Disposition': 'attachment; filename="' + row.source_filename + '"',
                'X-Content-SHA256': row.import_fingerprint, 'X-Reference-SHA256': row.import_fingerprint})

    @app.get(BASE + '/matches')
    def ref_matches():
        code, version = request.args.get('code', ''), request.args.get('version', '')
        if len(code) > 32 or len(version) > 100:
            abort(422)
        with SessionLocal() as db:
            require_role(db, 'doctor')
            output = []
            if version not in (ICD_VERSION, ARCHIVE['version']):
                abort(422)
            if resolve_icd10(code, version):
                for rule in db.scalars(select(ReferenceMatchRule).where(ReferenceMatchRule.icd10_code == code,
                        ReferenceMatchRule.curation_status == 'synthetic_demo',
                        ReferenceMatchRule.environment_scope == 'synthetic_dev').order_by(ReferenceMatchRule.id)).all():
                    row = db.get(DrugReference, (rule.drug_reference_id, rule.drug_reference_version))
                    if not row:
                        continue
                    paths = json.loads(rule.source_field_paths_json)
                    source = json.loads(row.raw_original_json)
                    values = []
                    for pointer in paths:
                        value = source
                        for part in pointer.strip('/').split('/'):
                            value = value[int(part)] if isinstance(value, list) else value[part]
                        values.append(value)
                    if len(values) != 2 or values[0] != code or values[1] != rule.match_basis:
                        abort(409)
                    output.append(dict(reference=compact_reference(row), rule=dict(id=rule.id, version=rule.version,
                        code=rule.icd10_code, match_basis=rule.match_basis, source_field_paths=paths,
                        curation_status=rule.curation_status, display_limitation=rule.display_limitation,
                        source_excerpt=dict(icd10_code=values[0], diagnosis_or_condition=values[1]))))
            return dict(items=output, label='Справочное совпадение (демо)', limitation=MATCH_LIMITATION)

    @app.get(BASE + '/therapies')
    def ref_therapies():
        with SessionLocal() as db:
            require_role(db, 'doctor')
            return dict(items=[dict(json.loads(r.content_json), id=r.id, version=r.version, title=r.title, review_status=r.review_status) for r in db.scalars(select(TherapyReference).order_by(TherapyReference.title)).all()],
                limitation=THERAPY_LIMITATION)

    @app.get(BASE + '/therapies/<therapy_id>')
    def ref_therapy(therapy_id):
        with SessionLocal() as db:
            require_role(db, 'doctor')
            row = db.scalar(select(TherapyReference).where(TherapyReference.id == therapy_id)
                .order_by(TherapyReference.version.desc()).limit(1))
            if not row:
                abort(404)
            return dict(json.loads(row.content_json), id=row.id, title=row.title, limitation=THERAPY_LIMITATION)
