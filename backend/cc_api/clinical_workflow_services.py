"""Versioned physician-authored documents with explicit release and current consent."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from flask import abort
from sqlalchemy import delete, select
from werkzeug.exceptions import HTTPException
from .models import User
from .extension_models import Audit
from .p0_models import CarePlan, PlanItem, PlanEvent
from .clinical_workflow_models import (ClinicalDocument, ClinicalDocumentRevision,
    MedicationOrder, MedicationAdherence)
from .doctor_access import authorized_patient
from .icd10 import resolve_icd10


def uid(prefix):
    return prefix + uuid.uuid4().hex


def text(value, maximum, *, required=False):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        abort(422)
    return value.strip()


def validate_content(kind, mode, raw):
    if kind not in ('encounter', 'treatment') or mode not in ('quick', 'extended') or not isinstance(raw, dict):
        abort(422)
    if set(raw) - {'narrative', 'assessment', 'follow_up', 'diagnoses', 'items'}:
        abort(422)
    output = {}
    for key, maximum in (('narrative', 12000), ('assessment', 6000), ('follow_up', 2000)):
        if key in raw:
            output[key] = text(raw[key], maximum)
    if kind == 'encounter' and not output.get('narrative'):
        abort(422, description='Напишите текст записи приёма перед сохранением.')
    diagnoses, items = raw.get('diagnoses', []), raw.get('items', [])
    if not isinstance(diagnoses, list) or len(diagnoses) > 20 or not isinstance(items, list) or len(items) > 30:
        abort(422)
    output['diagnoses'] = []
    for diagnosis in diagnoses:
        if not isinstance(diagnosis, dict) or set(diagnosis) != {'code', 'version', 'status'}:
            abort(422)
        if not isinstance(diagnosis['code'], str) or not isinstance(diagnosis['version'], str) or diagnosis['status'] not in ('preliminary', 'confirmed'):
            abort(422)
        reference = resolve_icd10(diagnosis['code'], diagnosis['version'])
        if not reference:
            abort(422)
        output['diagnoses'].append({**reference, 'status': diagnosis['status']})
    output['items'] = []
    for item in items:
        limits = dict(title=200, frequency=120, duration=200, dose=200, route=120, notes=2000,
                      reference_id=80, reference_version=80)
        if not isinstance(item, dict) or set(item) - (set(limits) | {'item_type'}):
            abort(422)
        if item.get('item_type') not in ('medication', 'consultation', 'measurement', 'behavioral', 'action', 'custom'):
            abort(422)
        if not isinstance(item.get('title'),str) or not item['title'].strip():
            abort(422, description='Укажите название каждого добавленного элемента плана или удалите пустой элемент.')
        normalized = {'item_type': item['item_type'], 'title': text(item.get('title'), 200, required=True)}
        for key, maximum in limits.items():
            if key in item and key != 'title':
                normalized[key] = text(item[key], maximum)
        if any(normalized.get(k) for k in ('reference_id', 'reference_version')):
            if normalized['item_type'] != 'medication' or not normalized.get('reference_id') or not normalized.get('reference_version'):
                abort(422)
            try:
                from .medical_references import resolve_medication_reference
            except ImportError:
                abort(422)
            if not resolve_medication_reference(normalized['reference_id'], normalized['reference_version']):
                abort(422)
        output['items'].append(normalized)
    if kind == 'treatment' and not output['items']:
        abort(422, description='Добавьте хотя бы один элемент плана лечения.')
    scopes = {'symptoms'}
    if output['diagnoses']:
        scopes.add('diagnosis')
    if any(i['item_type'] == 'medication' for i in output['items']):
        scopes.add('medications')
    return output, ','.join(sorted(scopes))


def authorize_scopes(db, doctor, patient_id, scopes, *, lock=False):
    person = None
    for scope in sorted(set(scopes.split(','))):
        person = authorized_patient(db, doctor, patient_id, scope=scope, lock=lock)
    return person


def document_access(db, user, document_id, *, lock=False):
    # Select only ACL metadata until every required category and tenant has passed.
    metadata = db.execute(select(ClinicalDocument.patient_id, ClinicalDocument.clinician_id,
        ClinicalDocument.required_scopes, ClinicalDocument.status, ClinicalDocument.signed_at,
        ClinicalDocument.published_at, ClinicalDocument.signed_hash).where(ClinicalDocument.id == document_id)).first()
    if not metadata:
        abort(404)
    if user.role == 'doctor':
        if metadata.clinician_id != user.id:
            abort(404)
        authorize_scopes(db, user, metadata.patient_id, metadata.required_scopes, lock=lock)
    elif user.role == 'patient':
        if (metadata.patient_id != user.patient_id or metadata.status != 'published'
                or not metadata.signed_at or not metadata.published_at or not metadata.signed_hash):
            abort(404)
        doctor = db.get(User, metadata.clinician_id)
        if not doctor:
            abort(404)
        person = authorize_scopes(db, doctor, metadata.patient_id, metadata.required_scopes, lock=lock)
        if person.id != user.id:
            abort(404)
    else:
        abort(403)
    return db.get(ClinicalDocument, document_id)


def order_payload(db, order):
    reports = [dict(id=r.id, outcome=r.outcome, note=r.note, recorded_at=r.recorded_at,
        source='medication_adherence') for r in db.scalars(select(MedicationAdherence)
        .where(MedicationAdherence.order_id == order.id)).all()]
    reports += [dict(id=r.id, outcome=r.outcome, note='', recorded_at=r.reported_at,
        source='legacy_plan_report') for r in db.scalars(select(PlanEvent)
        .where(PlanEvent.item_id == order.id)).all()]
    reports.sort(key=lambda r: (datetime.fromisoformat(r['recorded_at'].replace('Z','+00:00')).astimezone(timezone.utc), r['id']))
    return dict(id=order.id, title=order.title, reference_id=order.reference_id,
        reference_version=order.reference_version, regimen=json.loads(order.regimen_json),
        reports=reports)


def document_payload(db, row, *, patient=False):
    output = {key: getattr(row, key) for key in ('id', 'patient_id', 'clinician_id', 'kind', 'mode',
        'status', 'revision', 'parent_id', 'amendment_reason', 'signed_at', 'published_at', 'created_at', 'updated_at')}
    output['content'] = json.loads(row.content_json)
    output['orders'] = [order_payload(db, order) for order in db.scalars(select(MedicationOrder)
        .where(MedicationOrder.document_id == row.id).order_by(MedicationOrder.id)).all()]
    # No snapshots, private historical text, or unpublished revision details to patient.
    output['versions'] = [] if patient else [dict(revision=r.revision, action=r.action,
        actor_id=r.actor_id, created_at=r.created_at) for r in db.scalars(select(ClinicalDocumentRevision)
            .where(ClinicalDocumentRevision.document_id == row.id).order_by(ClinicalDocumentRevision.revision)).all()]
    return output


def released_documents(db, patient_user, doctor=None):
    if patient_user.role != 'patient':
        abort(403)
    query = select(ClinicalDocument.id).where(ClinicalDocument.patient_id == patient_user.patient_id,
        ClinicalDocument.status == 'published', ClinicalDocument.signed_at.is_not(None), ClinicalDocument.published_at.is_not(None))
    if doctor:
        query = query.where(ClinicalDocument.clinician_id == doctor.id)
    output = []
    for doc_id in db.scalars(query).all():
        try:
            row = document_access(db, doctor or patient_user, doc_id)
        except HTTPException as exc:
            if exc.code == 404:
                continue
            raise
        output.append(document_payload(db, row, patient=doctor is None))
    return sorted(output, key=lambda r: (r['published_at'], r['id']), reverse=True)


def signature(row):
    signed = dict(patient_id=row.patient_id, clinician_id=row.clinician_id, kind=row.kind,
        mode=row.mode, content=json.loads(row.content_json), required_scopes=row.required_scopes)
    return hashlib.sha256(json.dumps(signed, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def append_revision(db, row, actor, action, now):
    db.add(ClinicalDocumentRevision(id=uid('cdr_'), document_id=row.id, revision=row.revision,
        action=action, actor_id=actor.id, snapshot_json=json.dumps(dict(content=json.loads(row.content_json),
            status=row.status, mode=row.mode, signed_hash=row.signed_hash, parent_id=row.parent_id), ensure_ascii=False), created_at=now))
    db.add(Audit(id=uid('cda_'), actor=actor.id, action='clinical_document_' + action,
        object_type='clinical_document', object_id=row.id, created_at=now))


def synchronize_orders(db, row, now):
    old = {order.id: order for order in db.scalars(select(MedicationOrder).where(MedicationOrder.document_id == row.id)).all()}
    kept = set()
    for index, item in enumerate(json.loads(row.content_json)['items']):
        if item['item_type'] != 'medication':
            continue
        oid = 'mord_' + row.id.removeprefix('cdoc_') + '_' + str(index)
        kept.add(oid)
        order = old.get(oid)
        if not order:
            order = MedicationOrder(id=oid, document_id=row.id, patient_id=row.patient_id, clinician_id=row.clinician_id,
                title=item['title'], reference_id=None, reference_version=None, regimen_json='{}', created_at=now)
            db.add(order)
        order.title = item['title']
        order.reference_id = item.get('reference_id') or None
        order.reference_version = item.get('reference_version') or None
        order.regimen_json = json.dumps({key: value for key, value in item.items()
            if key not in ('item_type', 'title', 'reference_id', 'reference_version')}, ensure_ascii=False)
    for oid in old.keys() - kept:
        db.delete(old[oid])
    db.flush()


def publish_plan(db, row, now):
    if row.kind != 'treatment' or db.get(CarePlan, row.id):
        return
    # A published amendment adds a plan version; old orders and reports survive.
    parent = row.parent_id
    while parent:
        old_plan = db.get(CarePlan, parent)
        if old_plan:
            old_plan.status = 'superseded'
        ancestor = db.get(ClinicalDocument, parent)
        parent = ancestor.parent_id if ancestor else None
    db.add(CarePlan(id=row.id, patient_id=row.patient_id, clinician_id=row.clinician_id,
        status='active', version=row.revision, created_at=now))
    db.flush()
    for index, item in enumerate(json.loads(row.content_json)['items']):
        ident = ('mord_' + row.id.removeprefix('cdoc_') + '_' + str(index) if item['item_type'] == 'medication'
                 else 'citem_' + row.id.removeprefix('cdoc_') + '_' + str(index))
        db.add(PlanItem(id=ident, plan_id=row.id, item_type=item['item_type'], title=item['title'],
            scheduled_at=None, frequency=item.get('frequency', ''),
            completion_criteria=item.get('notes', '')[:300], created_at=now))
    db.flush()

def new_document(db, doctor, pid, kind, mode, content, scopes, now, parent=None, reason=None):
    row = ClinicalDocument(id=uid('cdoc_'), patient_id=pid, clinician_id=doctor.id,
        kind=kind, mode=mode, content_json=json.dumps(content, ensure_ascii=False),
        required_scopes=scopes, status='draft', revision=1, parent_id=parent,
        amendment_reason=reason, signed_hash=None, created_at=now, updated_at=now,
        signed_at=None, published_at=None)
    db.add(row)
    db.flush()
    synchronize_orders(db, row, now)
    append_revision(db, row, doctor, 'amend' if parent else 'create', now)
    return row
