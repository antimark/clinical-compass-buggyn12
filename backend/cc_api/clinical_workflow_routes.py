"""Explicit save, sign, release and amendment APIs; no automatic prescribing."""
import json
from flask import abort, request
from sqlalchemy import select, update
from .models import User
from .p0_models import UserNotification
from .clinical_workflow_models import ClinicalDocument, MedicationOrder, MedicationAdherence
from .clinical_workflow_services import (uid, text, validate_content, authorize_scopes,
    document_access, document_payload, order_payload, append_revision, signature,
    synchronize_orders, publish_plan, new_document)
from .icd10 import ICD_VERSION, search_icd10
from .verification import workspace_enabled

from .clinical_intelligence_review_services import safe_storage_errors

BASE = '/api/v1/clinical-workflow'


def register_clinical_workflow_routes(app, SessionLocal, current_user, require_role, error, utc_now):
    @app.before_request
    def clinical_workflow_guard():
        if request.path.startswith(BASE + '/') and request.path != BASE + '/capabilities' and not workspace_enabled(app.config):
            return error(403, 'SYNTHETIC_PROFILE_REQUIRED', 'Доступно только в synthetic_dev')

    def stamp():
        value = utc_now()
        return value if isinstance(value, str) else value.isoformat().replace('+00:00', 'Z')

    def body(fields, required=None):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) - set(fields) or set(required or ()) - set(data):
            abort(422)
        return data

    def auth(db):
        user = current_user(db)
        if not user:
            abort(401)
        if user.role not in ('doctor', 'patient'):
            abort(403)
        return user

    def revision(data):
        if type(data.get('revision')) is not int or data['revision'] < 1:
            abort(422)
        return data['revision']

    def conflict():
        return error(409, 'CONFLICT', 'Документ изменился или подписан; обновите страницу')

    @app.get(BASE + '/capabilities')
    def cw_capabilities():
        return {'enabled': workspace_enabled(app.config)}

    @app.get(BASE + '/icd10')
    def cw_icd10():
        query = request.args.get('q', '')
        if len(query) > 100:
            abort(422)
        with SessionLocal() as db:
            require_role(db, 'doctor')
            return dict(items=search_icd10(query), version=ICD_VERSION,
                coverage='limited_verified_subset', limitation='Ограниченный проверенный набор кодов МКБ-10; не полный национальный справочник.')

    @app.get(BASE + '/patients/<patient_id>/documents')
    def cw_documents(patient_id):
        with SessionLocal() as db:
            user = auth(db)
            if user.role == 'doctor':
                authorize_scopes(db, user, patient_id, 'symptoms')
                query = select(ClinicalDocument.id).where(ClinicalDocument.patient_id == patient_id,
                    ClinicalDocument.clinician_id == user.id)
            else:
                if user.patient_id != patient_id:
                    abort(404)
                query = select(ClinicalDocument.id).where(ClinicalDocument.patient_id == patient_id,
                    ClinicalDocument.status == 'published')
            from werkzeug.exceptions import HTTPException
            items = []
            for document_id in db.scalars(query).all():
                try:
                    row = document_access(db, user, document_id)
                except HTTPException as exc:
                    if exc.code == 404:
                        continue
                    raise
                items.append(document_payload(db, row, patient=user.role == 'patient'))
            return {'items': sorted(items, key=lambda r: (r['created_at'], r['id']), reverse=True)}

    @app.get(BASE + '/documents/<document_id>')
    def cw_document(document_id):
        with SessionLocal() as db:
            user = auth(db)
            return document_payload(db, document_access(db, user, document_id), patient=user.role == 'patient')

    @app.post(BASE + '/patients/<patient_id>/documents')
    def cw_create(patient_id):
        data = body(('kind', 'mode', 'content'), ('kind', 'mode', 'content'))
        content, scopes = validate_content(data['kind'], data['mode'], data['content'])
        with SessionLocal() as db:
            doctor = require_role(db, 'doctor')
            authorize_scopes(db, doctor, patient_id, scopes, lock=True)
            row = new_document(db, doctor, patient_id, data['kind'], data['mode'], content, scopes, stamp())
            db.commit()
            return document_payload(db, row), 201

    @app.put(BASE + '/documents/<document_id>')
    @safe_storage_errors
    def cw_save(document_id):
        request.max_content_length=2097153
        if request.content_length and request.content_length>2097152: abort(413)
        if len(request.get_data(cache=True))>2097152: abort(413)
        data = body(('revision', 'mode', 'content', 'ci_transfer'), ('revision', 'mode', 'content'))
        rev = revision(data)
        transfer = 'ci_transfer' in data
        if transfer:
            from .clinical_intelligence_review_services import enabled
            if not enabled(app): abort(404)
            request.max_content_length=2097153
            if len(request.get_data(cache=True))>2097152: abort(413)
            hook=app.extensions.get('ci_review_before_write')
            if hook: hook()
        with SessionLocal() as db:
            doctor = require_role(db, 'doctor')
            row = document_access(db, doctor, document_id, lock=True)
            receipt = source = None
            raw_content = data['content']
            if transfer:
                from .clinical_intelligence_review_services import prepare_transfer, transfer_payload, final_check
                source,receipt,raw_content = prepare_transfer(db,doctor,row,data)
                if raw_content is None:
                    final_check(app,db,doctor,source,receipt.suggestion_id)
                    result=document_payload(db,row)
                    result['ci_transfer']=transfer_payload(receipt)
                    db.commit()
                    return result
            content, scopes = validate_content(row.kind, data['mode'], raw_content)
            authorize_scopes(db, doctor, row.patient_id, scopes, lock=True)
            now = stamp()
            result = db.execute(update(ClinicalDocument).where(ClinicalDocument.id == row.id,
                ClinicalDocument.status == 'draft', ClinicalDocument.revision == rev)
                .values(content_json=json.dumps(content, ensure_ascii=False), mode=data['mode'],
                    required_scopes=scopes, revision=rev + 1, updated_at=now))
            if result.rowcount != 1:
                return conflict()
            db.refresh(row)
            synchronize_orders(db, row, now)
            append_revision(db, row, doctor, 'save', now)
            if transfer:
                db.add(receipt)
                final_check(app,db,doctor,source,receipt.suggestion_id)
            db.commit()
            result=document_payload(db,row)
            if transfer: result['ci_transfer']=transfer_payload(receipt)
            return result

    def transition(document_id, state):
        data = body(('revision',), ('revision',))
        rev = revision(data)
        with SessionLocal() as db:
            doctor = require_role(db, 'doctor')
            row = document_access(db, doctor, document_id, lock=True)
            now = stamp()
            prior = 'draft' if state == 'signed' else 'signed'
            if state == 'published' and (not row.signed_at or row.signed_hash != signature(row)):
                return conflict()
            values = dict(status=state, revision=rev + 1, updated_at=now)
            if state == 'signed':
                values.update(signed_at=now, signed_hash=signature(row))
            else:
                values.update(published_at=now)
            changed = db.execute(update(ClinicalDocument).where(ClinicalDocument.id == row.id,
                ClinicalDocument.status == prior, ClinicalDocument.revision == rev).values(**values))
            if changed.rowcount != 1:
                return conflict()
            db.refresh(row)
            append_revision(db, row, doctor, 'sign' if state == 'signed' else 'publish', now)
            if state == 'published':
                publish_plan(db, row, now)
                person = db.scalar(select(User).where(User.patient_id == row.patient_id,
                    User.role == 'patient', User.organization_id == doctor.organization_id))
                notice=UserNotification(id=uid('cdn_'), recipient_id=person.id, category='record',
                    text='Врач явно опубликовал новую запись в медицинской карте', created_at=now)
                db.add(notice);db.flush()
                from .clinical_review_services import set_notification_destination
                set_notification_destination(db,notice,'clinical_document',row.id)
            db.commit()
            return document_payload(db, row)

    @app.post(BASE + '/documents/<document_id>/sign')
    def cw_sign(document_id):
        return transition(document_id, 'signed')

    @app.post(BASE + '/documents/<document_id>/publish')
    def cw_publish(document_id):
        return transition(document_id, 'published')

    @app.post(BASE + '/documents/<document_id>/amend')
    def cw_amend(document_id):
        data = body(('revision', 'reason'), ('revision', 'reason'))
        rev, reason = revision(data), text(data['reason'], 2000, required=True)
        with SessionLocal() as db:
            doctor = require_role(db, 'doctor')
            original = document_access(db, doctor, document_id, lock=True)
            if original.status not in ('signed', 'published') or original.revision != rev:
                return conflict()
            if not original.signed_at or original.signed_hash != signature(original):
                return conflict()
            new = new_document(db, doctor, original.patient_id, original.kind, original.mode,
                json.loads(original.content_json), original.required_scopes, stamp(), parent=original.id, reason=reason)
            db.commit()
            return document_payload(db, new), 201

    @app.get(BASE + '/patients/<patient_id>/medication-orders')
    def cw_orders(patient_id):
        with SessionLocal() as db:
            user = auth(db)
            if user.role == 'doctor':
                authorize_scopes(db, user, patient_id, 'medications')
                query = select(MedicationOrder.id, MedicationOrder.document_id).where(
                    MedicationOrder.patient_id == patient_id, MedicationOrder.clinician_id == user.id)
            else:
                if user.patient_id != patient_id:
                    abort(404)
                query = select(MedicationOrder.id, MedicationOrder.document_id).where(MedicationOrder.patient_id == patient_id)
            from werkzeug.exceptions import HTTPException
            items = []
            for oid, did in db.execute(query).all():
                try:
                    document_access(db, user, did)
                except HTTPException as exc:
                    if exc.code == 404:
                        continue
                    raise
                items.append(order_payload(db, db.get(MedicationOrder, oid)))
            return {'items': items}

    @app.post(BASE + '/medication-orders/<order_id>/report')
    def cw_report(order_id):
        data = body(('outcome', 'note'), ('outcome',))
        if data['outcome'] not in ('completed', 'missed', 'partial', 'uncertain'):
            abort(422)
        note = text(data.get('note', ''), 2000)
        with SessionLocal() as db:
            user = require_role(db, 'patient')
            did = db.scalar(select(MedicationOrder.document_id).where(MedicationOrder.id == order_id,
                MedicationOrder.patient_id == user.patient_id))
            if not did:
                abort(404)
            document_access(db, user, did, lock=True)
            row = MedicationAdherence(id=uid('mrep_'), order_id=order_id, patient_user_id=user.id,
                outcome=data['outcome'], note=note, recorded_at=stamp())
            db.add(row)
            from .extension_models import Audit
            db.add(Audit(id=uid('cda_'), actor=user.id, action='medication_adherence_reported',
                object_type='medication_order', object_id=order_id, created_at=stamp()))
            db.commit()
            return dict(id=row.id, order_id=order_id, outcome=row.outcome, note=row.note, recorded_at=row.recorded_at), 201
