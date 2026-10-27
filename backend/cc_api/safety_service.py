"""Atomic intake detection, exact current-source authorization and minimized DTOs."""
import json,uuid
from flask import abort
from sqlalchemy import select
from werkzeug.exceptions import HTTPException
from .models import User
from .doctor_experience_models import DoctorSignal
from .safety_models import SafetyDetection,SafetyOutbox,SafetyAction
from .clinical_intelligence_sources import selected_source,digest
from .clinical_intelligence_review_services import source_locked
from .clinical_copilot_services import now,dump
from .extension_models import Audit
from .safety_rules import evaluate,RULES,POLICY
from .verification import workspace_enabled

def enabled(app):return workspace_enabled(app.config) and app.config.get('CI_SAFETY_V1',app.config.get('APP_ENV')=='evaluation_sandbox') is True

def audit(db,actor,action,key):
    db.add(Audit(id='sa_'+uuid.uuid4().hex,actor=actor,action=action,object_type='safety',object_id=key,created_at=now()))

def ingest(app,db,case):
    if not enabled(app):return
    db.flush()
    patient=db.get(User,case.patient_user_id);doctor=db.get(User,case.doctor_id)
    if not patient or not doctor:return
    text=json.loads(case.intake_json).get('text','')
    findings=evaluate(text)
    # Persist a trace even for negative/ambiguous inputs; private diary never enters here.
    try:source=selected_source(db,doctor,patient.patient_id,case.id)
    except HTTPException:
        source=None
    version=source.source_version if source else digest(['unshared-intake',text,case.created_at])
    trace_key='sd_'+digest([case.id,version,digest([POLICY,RULES]),doctor.id])[:48]
    if db.get(SafetyDetection,trace_key):return
    evaluations=findings or [{'rule':None,'evidence':None}]
    for n,finding in enumerate(evaluations):
        rule=finding['rule'];ident=trace_key if n==0 else trace_key+'_'+str(n)
        signal_id='ss_'+digest([ident,rule])[:48] if rule and source else None
        stamp=now(); trace={'source_type':'intake','scope':'symptoms','visibility':'case_consent_and_clinical_link' if source else 'no_authorized_recipient',
            'clinical_review_status':'experimental_needs_validation',**finding}
        db.add(SafetyDetection(id=ident,signal_id=signal_id,source_id=case.id,patient_id=patient.patient_id,
            recipient_id=doctor.id,tenant_id=doctor.organization_id,source_version=version,grant_version=source.grant_version if source else '',
            trace_json=dump(trace),status='detected' if signal_id else ('no_authorized_recipient' if rule else 'not_assessed'),workflow_status='unseen',revision=1,created_at=stamp))
        if signal_id:
            db.add(DoctorSignal(id=signal_id,doctor_id=doctor.id,patient_id=patient.patient_id,kind='system_signal',source='consented_intake_safety',event_key=ident,
                rule_version=rule['rule_id']+':'+rule['version'],reason='Точное текстовое основание экспериментального правила; требуется оценка врача.',
                evidence_json=dump({'required_scope':'symptoms',**finding}),occurred_at=stamp,status='open',created_at=stamp))
            db.flush()
            db.add(SafetyOutbox(id='so_'+digest(ident)[:48],detection_id=ident,status='queued',attempts=0,next_at=0,lease_until=0,lease_token='',receipt='',delivered_at='',created_at=stamp))
        audit(db,patient.id,'safety_evaluated',ident)

def authorize(db,doctor,ident,lock=False):
    if doctor.role!='doctor':abort(403)
    meta=db.execute(select(SafetyDetection.id,SafetyDetection.source_id,SafetyDetection.patient_id,SafetyDetection.source_version,SafetyDetection.grant_version).where(
        SafetyDetection.signal_id==ident,SafetyDetection.recipient_id==doctor.id,SafetyDetection.tenant_id==doctor.organization_id)).first()
    if not meta:abort(404)
    source=(source_locked if lock else selected_source)(db,doctor,meta.patient_id,meta.source_id)
    if source.source_version!=meta.source_version or source.grant_version!=meta.grant_version:abort(404)
    row=db.get(SafetyDetection,meta.id,populate_existing=True)
    if row.status!='detected':abort(404)
    return row,source

def dto(db,row):
    trace=json.loads(row.trace_json);rule=trace['rule'];out=db.scalar(select(SafetyOutbox).where(SafetyOutbox.detection_id==row.id))
    patient_name=db.scalar(select(User.display_name).where(User.patient_id==row.patient_id,User.role=='patient',User.organization_id==row.tenant_id))
    return dict(id=row.signal_id,patient_name=patient_name or 'Пациент',patient_ref=row.patient_id,case_ref=row.source_id,revision=row.revision,signal_type=rule['signal_type'],severity=rule['severity'],critical=rule['critical'],
        detection_status=row.status,workflow_status=row.workflow_status,technical_status='implemented',clinical_review_status='experimental_needs_validation',
        reason='Точное совпадение с экспериментальным текстовым правилом; это не прогноз риска и не медицинское решение.',evidence=trace['evidence'],rule=rule,
        source_version=row.source_version,grant_version=row.grant_version,created_at=row.created_at,
        transport=dict(status=out.status,attempts=out.attempts,receipt=out.receipt,delivered_at=out.delivered_at),
        history=[dict(action=a.action,actor_id=a.actor_id,created_at=a.created_at,revision=a.revision) for a in db.scalars(select(SafetyAction).where(SafetyAction.detection_id==row.id).order_by(SafetyAction.revision))])
