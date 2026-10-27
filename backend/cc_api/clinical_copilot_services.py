"""Shared transaction boundary and reauthorized DTOs for manual referrals/private chat."""
import json
from datetime import datetime,timezone
from flask import abort
from sqlalchemy import select,update,func
from .models import User
from .extension_models import Audit
from .clinical_intelligence_sources import selected_source,digest
from .clinical_intelligence_review_services import source_locked,final_check,receipt_key
from .clinical_workflow_services import uid,text
from .clinical_copilot_models import Referral,ReferralEvent,CopilotReceipt,CopilotThread,CopilotMessage,CopilotJob
from .verification import workspace_enabled

BASE='/api/v1/clinical-intelligence'

def now():return datetime.now(timezone.utc).isoformat()
def dump(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def enabled(app,flag):return workspace_enabled(app.config) and app.config.get('CI_API_V1') is True and app.config.get(flag) is True

def expected(source,body):
    if body.get('source_version')!=source.source_version or body.get('grant_version')!=source.grant_version:abort(409)

def audit(db,actor,action,ident):
    db.add(Audit(id=uid('au_'),actor=actor.id,action=action,object_type='clinical_copilot',object_id=ident,created_at=now()))

def receipt(db,actor,data,resource):
    key=receipt_key(data.get('idempotency_key'));fingerprint=digest([resource,data])
    row=db.scalar(select(CopilotReceipt).where(CopilotReceipt.actor_id==actor.id,CopilotReceipt.key_hash==key))
    if row:
        if row.request_digest!=fingerprint:abort(409)
        return key,fingerprint,json.loads(row.response_json)
    return key,fingerprint,None

def save_receipt(db,actor,key,fingerprint,dto):
    db.add(CopilotReceipt(id=uid('rc_'),actor_id=actor.id,key_hash=key,request_digest=fingerprint,response_json=dump(dto),created_at=now()))

def finish(app,db,actor,source,extra_check=None):
    hook=app.extensions.get('copilot_before_commit')
    if hook:hook(db)
    if getattr(source,'audience','doctor')=='patient':
        from .patient_context import recheck
        recheck(db,actor,source)
    else:
        final_check(app,db,actor,source)
        if actor.role!='doctor':abort(403)
    if extra_check is not None and not extra_check():abort(409)
    db.commit()

def access(db,actor,model,ident,lock=False,strict=True):
    if not actor:abort(404)
    query=select(model).where(model.id==ident,model.actor_id==actor.id,model.tenant_id==actor.organization_id)
    if model is CopilotThread:query=query.where(CopilotThread.audience==actor.role)
    row=db.scalar(query)
    if not row:abort(404)
    if model is CopilotThread:
        if actor.role not in ('patient','doctor') or row.audience!=actor.role:abort(404)
        source=chat_source(db,actor,row.patient_id,row.source_id or row.case_id,row.source_type,lock)
    else:
        if actor.role!='doctor':abort(403)
        source=(source_locked if lock else selected_source)(db,actor,row.patient_id,row.case_id)
    if strict and (row.source_version!=source.source_version or row.grant_version!=source.grant_version):abort(409)
    return row,source

def chat_source(db,actor,patient_id,ident,source_type='intake',lock=False):
    if actor.role=='patient':
        from .patient_context import selected
        return selected(db,actor,patient_id,ident,source_type,lock)
    if actor.role!='doctor':abort(403)
    if source_type!='intake':abort(404)
    return (source_locked if lock else selected_source)(db,actor,patient_id,ident)

def referral_dto(db,row):
    return dict(id=row.id,patient_ref=row.patient_id,case_ref=row.case_id,actor_id=row.actor_id,
        authority='manual_physician',status=row.status,revision=row.revision,source_version=row.source_version,grant_version=row.grant_version,
        **json.loads(row.content_json),confirmation_hash=row.confirmation_hash,created_at=row.created_at,updated_at=row.updated_at,
        clinical_review_status='independent_physician_decision',technical_status='implemented',
        history=[dict(action=x.action,revision=x.revision,actor_id=x.actor_id,created_at=x.created_at,reason=x.reason)
            for x in db.scalars(select(ReferralEvent).where(ReferralEvent.referral_id==row.id).order_by(ReferralEvent.revision))])

def job_dto(row):
    values=json.loads(row.timings_json)
    return dict(id=row.id,thread_id=row.thread_id,status=row.status,safe_error_code=row.safe_error_code,
        queued_at=row.queued_at,started_at=row.started_at,finished_at=row.finished_at,
        timings={k:v for k,v in values.items() if k!='auth_session_hash'})

def thread_dto(db,row,source,full=True):
    result=dict(id=row.id,audience=row.audience,source_type=row.source_type,source_id=row.source_id or row.case_id,patient_ref=row.patient_id,case_ref=row.case_id,status=row.status,revision=row.revision,
        source_version=row.source_version,grant_version=row.grant_version,retention_state=row.retention_state,
        created_at=row.created_at,updated_at=row.updated_at,technical_status='implemented',clinical_review_status='experimental_needs_validation',
        context_preview=dict(source_type=row.source_type,scope='patient_self' if row.audience=='patient' else 'symptoms',case_ref=row.case_id,source_version=source.source_version,
            description=('Только явно выбранная собственная запись и история этого ИИ-чата. Врач не получает эту историю или личный дневник.' if row.audience=='patient' else 'Только выбранное обращение и история этого врачебного чата. Дневники, лекарства, чужие заметки и черновики не включены.')))
    if full:
        messages=[]
        from .copilot_catalog import citation
        for msg in db.scalars(select(CopilotMessage).where(CopilotMessage.thread_id==row.id).order_by(CopilotMessage.ordinal)):
            meta=json.loads(msg.provenance_json)
            refs=meta.pop('catalog_citations',[])
            # A retired/changed public fragment is no longer serialized as a verified old citation.
            current=[x for x in refs if citation(x['kind'],x['catalog_id'],audience=row.audience)==x]
            messages.append(dict(id=msg.id,ordinal=msg.ordinal,role=msg.role,content=msg.content,
                created_at=msg.created_at,status='completed',mode=meta.pop('mode','user'),model=meta.pop('model',None),
                catalog_citations=[{k:v for k,v in x.items() if k!='snippet'} for x in current],
                citations_stale=len(current)!=len(refs),evidence=meta.pop('evidence',[]),**meta))
        result['messages']=messages
        result['jobs']=[job_dto(x) for x in db.scalars(select(CopilotJob).where(CopilotJob.thread_id==row.id).order_by(CopilotJob.queued_at))]
    return result
