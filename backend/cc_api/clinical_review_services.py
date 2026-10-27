"""Patient-authored fields require explicit, separately audited physician review.

No function in this module writes a diagnosis, encounter or treatment order.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from flask import abort
from sqlalchemy import func, select, update
from werkzeug.exceptions import HTTPException
from .models import User
from .extension_models import AISummaryDraft, Audit, Appointment
from .onboarding_models import PatientConsent
from .p0_models import Encounter, ClinicalDecision, SummaryRevision, UserNotification, CarePlan
from .clinical_review_models import (SummaryField, SummaryFieldRevision, EncounterAddendum,
    DecisionClassification, NotificationDestination, ClinicalReviewPacket)
from .doctor_access import authorized_patient
from .clinical_workflow_services import document_access
from .icd10 import resolve_icd10


SCOPES = ('symptoms', 'diagnosis', 'medications')
FIELD_SCOPES = {'concern':'symptoms', 'history':'symptoms', 'patient_diagnosis':'diagnosis',
                'medications':'medications', 'adverse_effects':'medications'}


def uid(): return 'cr_' + uuid.uuid4().hex
def stamp(): return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')
def canonical(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def bounded(value, maximum, required=True):
    if not isinstance(value, str) or len(value)>maximum or (required and not value.strip()): abort(422)
    return value.strip()


def audit(db, actor, action, kind, key):
    db.add(Audit(id=uid(), actor=actor.id, action=action, object_type=kind, object_id=key, created_at=stamp()))


def clinical_access(db, doctor, patient_id, lock=False):
    """The structured shared draft can span all categories; require all three.

    Unlike legacy links, this new workflow requires a current consent ledger.
    """
    person = authorized_patient(db, doctor, patient_id, None, lock=lock)
    ledgers = db.scalars(select(PatientConsent).where(PatientConsent.patient_user_id==person.id,
        PatientConsent.doctor_id==doctor.id).execution_options(populate_existing=True)).all()
    granted=set().union(*(set(x.categories.split(',')) for x in ledgers if x.revoked_at is None))
    if not set(SCOPES)<=granted: abort(404)
    for scope in SCOPES: authorized_patient(db, doctor, patient_id, scope)
    return person


def draft_access(db, actor, draft_id, lock=False):
    metadata=db.execute(select(AISummaryDraft.patient_user_id, AISummaryDraft.recipient_doctor_id,
        AISummaryDraft.state).where(AISummaryDraft.id==draft_id)).first()
    if not metadata: abort(404)
    if actor.role not in ('patient','doctor'): abort(403)
    if actor.id != (metadata.patient_user_id if actor.role=='patient' else metadata.recipient_doctor_id): abort(404)
    person=db.get(User, metadata.patient_user_id);doctor=db.get(User,metadata.recipient_doctor_id)
    if not person or not doctor or person.organization_id!=actor.organization_id or doctor.organization_id!=actor.organization_id: abort(404)
    clinical_access(db, doctor, person.patient_id, lock=lock)
    if lock:
        db.execute(update(AISummaryDraft).where(AISummaryDraft.id==draft_id).values(state=AISummaryDraft.state))
        metadata=db.execute(select(AISummaryDraft.state).where(AISummaryDraft.id==draft_id)).first()
    if metadata.state!='approved_for_recipient': abort(404)
    return db.get(AISummaryDraft,draft_id,populate_existing=True)


def field_payload(row):
    return dict(id=row.id,draft_id=row.draft_id,key=row.field_key,label=row.label,scope=row.scope,
        source_version=row.source_version,value=json.loads(row.value_json),revision=row.revision,
        status=row.status,reviewed_value=json.loads(row.reviewed_value_json) if row.reviewed_value_json else None,
        reviewer_id=row.reviewer_id,created_at=row.created_at,updated_at=row.updated_at)


def append_field_revision(db,row,actor,action):
    db.add(SummaryFieldRevision(id=uid(),field_id=row.id,revision=row.revision,actor_id=actor.id,
        action=action,snapshot_json=canonical(field_payload(row)),created_at=stamp()))


def create_fields(db, patient, draft_id, source_version, fields):
    if patient.role!='patient':abort(403)
    draft=draft_access(db,patient,draft_id,True)
    current=db.scalar(select(func.max(SummaryRevision.version)).where(SummaryRevision.draft_id==draft_id)) or 1
    if type(source_version) is not int or source_version!=current:abort(409)
    if not isinstance(fields,list) or not 1<=len(fields)<=len(FIELD_SCOPES):abort(422)
    if db.scalar(select(SummaryField.id).where(SummaryField.draft_id==draft_id)):abort(409)
    rows=[];keys=set()
    for entry in fields:
        if not isinstance(entry,dict) or set(entry)!={'key','label','value'}:abort(422)
        key=entry['key']
        if not isinstance(key,str) or key not in FIELD_SCOPES or key in keys:abort(422)
        keys.add(key);label=bounded(entry['label'],160);value=bounded(entry['value'],5000)
        row=SummaryField(id=uid(),draft_id=draft.id,field_key=key,label=label,scope=FIELD_SCOPES[key],
            source_version=current,value_json=canonical(value),revision=1,status='pending',reviewed_value_json=None,
            reviewer_id=None,created_at=stamp(),updated_at=stamp())
        db.add(row);db.flush();append_field_revision(db,row,patient,'patient_proposed');rows.append(row)
    audit(db,patient,'summary_fields_proposed','ai_summary',draft.id)
    return rows


def review_field(db,doctor,field_id,revision,action,value=None):
    if doctor.role!='doctor':abort(403)
    metadata=db.execute(select(SummaryField.draft_id).where(SummaryField.id==field_id)).first()
    if not metadata:abort(404)
    draft_access(db,doctor,metadata.draft_id,True)
    row=db.get(SummaryField,field_id,populate_existing=True)
    if type(revision) is not int or revision!=row.revision:abort(409)
    if action not in ('accept','edit','reject'):abort(422)
    reviewed=json.loads(row.value_json) if action=='accept' else bounded(value,5000) if action=='edit' else None
    changed=db.execute(update(SummaryField).where(SummaryField.id==field_id,SummaryField.revision==revision)
        .values(revision=revision+1,status={'accept':'accepted','edit':'edited','reject':'rejected'}[action],
            reviewed_value_json=canonical(reviewed) if reviewed is not None else None,
            reviewer_id=doctor.id,updated_at=stamp()))
    if changed.rowcount!=1:abort(409)
    db.refresh(row);append_field_revision(db,row,doctor,action);audit(db,doctor,'summary_field_'+action,'summary_field',row.id)
    return row


def encounter_access(db,doctor,encounter_id,lock=False):
    if doctor.role!='doctor':abort(403)
    metadata=db.execute(select(Encounter.patient_id,Encounter.clinician_id).where(Encounter.id==encounter_id)).first()
    if not metadata or metadata.clinician_id!=doctor.id:abort(404)
    for scope in SCOPES:
        authorized_patient(db,doctor,metadata.patient_id,scope,lock=lock)
    return db.get(Encounter,encounter_id)


def add_encounter_addendum(db,doctor,encounter_id,text,reason):
    encounter=encounter_access(db,doctor,encounter_id,True)
    if encounter.status!='signed' or not encounter.signed_at:abort(409)
    row=EncounterAddendum(id=uid(),encounter_id=encounter_id,author_id=doctor.id,
        text=bounded(text,12000),reason=bounded(reason,2000),created_at=stamp())
    db.add(row);audit(db,doctor,'encounter_addendum_created','encounter',encounter_id)
    return row


def classify_decision(db,doctor,decision_id,code,version):
    if doctor.role!='doctor':abort(403)
    metadata=db.execute(select(ClinicalDecision.patient_id,ClinicalDecision.clinician_id).where(ClinicalDecision.id==decision_id)).first()
    if not metadata or metadata.clinician_id!=doctor.id:abort(404)
    clinical_access(db,doctor,metadata.patient_id,True)
    if not isinstance(code,str) or not isinstance(version,str):abort(422)
    reference=resolve_icd10(code,version)
    if not reference:abort(422)
    existing=db.get(DecisionClassification,decision_id)
    if existing:
        if (existing.code,existing.version)!=(code,version):abort(409)
        return existing
    row=DecisionClassification(decision_id=decision_id,code=code,version=version,label=reference['label'],created_at=stamp())
    db.add(row);audit(db,doctor,'decision_classified','decision',decision_id)
    return row


def set_notification_destination(db,notice,entity_type,entity_id):
    if entity_type not in ('clinical_document','appointment','questionnaire'):abort(422)
    if not isinstance(entity_id,str) or len(entity_id)>64:abort(422)
    db.add(NotificationDestination(notification_id=notice.id,entity_type=entity_type,entity_id=entity_id))


def notification_destination(db,actor,notice):
    """Return an internal route only after current entity ACL; no arbitrary href."""
    if notice.recipient_id!=actor.id:return None
    row=db.get(NotificationDestination,notice.id)
    if not row:return None
    try:
        if row.entity_type=='clinical_document':
            doc=document_access(db,actor,row.entity_id)
            return '/patient?view=chart' if actor.role=='patient' else '/doctor/patients/'+doc.patient_id+'/treatment'
        if row.entity_type=='appointment':
            from .booking_services import case_access
            meta=db.execute(select(Appointment.case_id).where(Appointment.id==row.entity_id)).first()
            if not meta:return None
            case_access(db,actor,meta.case_id)
            return '/patient/appointments' if actor.role=='patient' else '/doctor/appointments'
        if row.entity_type=='questionnaire':
            from .patient_experience_models import DemoQuestionnaireAssignment,DemoQuestionnaireSubmission
            assignment=db.get(DemoQuestionnaireAssignment,row.entity_id)
            if not assignment:return None
            if actor.role=='patient':
                if actor.patient_id!=assignment.patient_id:return None
            elif actor.role=='doctor':
                authorized_patient(db,actor,assignment.patient_id,'symptoms')
            else:return None
            result=db.scalar(select(DemoQuestionnaireSubmission.id).where(DemoQuestionnaireSubmission.assignment_id==assignment.id))
            if not result:return None
            return '/patient/questionnaires/'+assignment.id+'/result' if actor.role=='patient' else '/doctor/patients/'+assignment.patient_id

    except HTTPException:return None
    return None


def create_review_packet(db,actor,kind,source_id,version,review_question):
    """Snapshot actual source material for review; never approve or validate it."""
    if actor.role!='doctor':abort(403)
    source_id=bounded(source_id,100);version=bounded(version,120);question=bounded(review_question,4000)
    if kind=='medication_reference':
        from .reference_models import DrugReference
        row=db.get(DrugReference,(source_id,version))
        if not row:abort(404)
        source=json.loads(row.raw_original_json);status='imported_unreviewed'
    elif kind=='therapy_reference':
        from .reference_models import TherapyReference
        row=db.get(TherapyReference,(source_id,version))
        if not row:abort(404)
        source=json.loads(row.content_json);status=row.review_status
    elif kind=='clinical_document':
        row=document_access(db,actor,source_id,lock=True)
        if str(row.revision)!=version:abort(409)
        source=json.loads(row.content_json);status='synthetic_patient_record'
    else:abort(422)
    content=canonical(source);fingerprint=hashlib.sha256(content.encode()).hexdigest()
    packet={'source_kind':kind,'source_id':source_id,'source_version':version,'source_status':status,
        'source_content':source,'source_sha256':fingerprint,'review_question':question,
        'medical_approval':'pending_actual_specialist_review','validated_scale_workflow':'not_approved',
        'limitation':'Запрос рецензирования не подтверждает медицинскую валидность или разрешение на клиническое применение.'}
    result=ClinicalReviewPacket(id=uid(),source_kind=kind,source_id=source_id,source_version=version,
        content_sha256=fingerprint,packet_json=canonical(packet),status='pending_specialist_review',creator_id=actor.id,requested_at=stamp())
    db.add(result);audit(db,actor,'clinical_review_requested','review_packet',result.id)
    return result


def review_packet_access(db,actor,row):
    if actor.role!='doctor':abort(403)
    if not row or row.creator_id!=actor.id:abort(404)
    if row.source_kind=='clinical_document':document_access(db,actor,row.source_id)
    return row


def event_notice(db,recipient_id,category,text,entity_type,entity_id):
    """Transactional in-app event only; no external delivery or timer claim."""
    notice=UserNotification(id=uid(),recipient_id=recipient_id,category=category,text=text,created_at=stamp())
    db.add(notice);db.flush()
    set_notification_destination(db,notice,entity_type,entity_id)
    return notice
