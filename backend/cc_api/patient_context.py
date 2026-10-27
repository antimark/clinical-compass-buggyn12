"""Explicit patient-self sources. A clinical link never grants access to these chats/diaries."""
import json
import re
from dataclasses import dataclass
from flask import abort
from sqlalchemy import select,update
from .models import User
from .extension_models import PrevisitCase
from .clinical_intelligence_sources import digest,active_case

POLICY='patient-self-explicit-source-v1'
@dataclass(frozen=True)
class PatientSource:
    patient_id:str
    case_id:str|None
    text:str
    created_at:str
    source_version:str
    source_revision:int
    grant_version:str
    source_type:str
    source_id:str
    audience:str='patient'

def own(db,actor,patient_id):
    if not actor or actor.role!='patient':abort(403)
    if not actor.patient_id or actor.patient_id!=patient_id:abort(404)
    return actor

def selected(db,actor,patient_id,ident,source_type='intake',lock=False):
    own(db,actor,patient_id)
    if source_type=='intake':
        meta=db.execute(select(PrevisitCase.id,PrevisitCase.status,PrevisitCase.allowed_until,PrevisitCase.consent_version).where(PrevisitCase.id==ident,PrevisitCase.patient_user_id==actor.id)).first()
        if not meta or not active_case(meta):abort(404)
        row=db.scalar(select(PrevisitCase).where(PrevisitCase.id==ident,PrevisitCase.patient_user_id==actor.id))
        if lock:db.execute(update(PrevisitCase).where(PrevisitCase.id==ident).values(status=PrevisitCase.status))
        try:value=json.loads(row.intake_json);content=value.get('text',value.get('message'))
        except (ValueError,TypeError,AttributeError):abort(422)
        revision=digest([row.status,row.allowed_until,row.consent_version])
        case_id=row.id
    elif source_type=='diary':
        from .clinical_copilot_models import PatientDiary
        meta=db.scalar(select(PatientDiary.id).where(PatientDiary.id==ident,PatientDiary.actor_id==actor.id,PatientDiary.tenant_id==actor.organization_id))
        if not meta:abort(404)
        row=db.scalar(select(PatientDiary).where(PatientDiary.id==ident,PatientDiary.actor_id==actor.id,PatientDiary.tenant_id==actor.organization_id))
        if lock:db.execute(update(PatientDiary).where(PatientDiary.id==ident).values(revision=PatientDiary.revision))
        content=row.content;revision=row.revision;case_id=None
    else:abort(422)
    if not isinstance(content,str) or not content.strip() or len(content)>4000:abort(422)
    if lock:
        db.execute(update(User).where(User.id==actor.id).values(role=User.role));db.expire_all()
        return selected(db,actor,patient_id,ident,source_type,False)
    version=digest([POLICY,source_type,ident,content,revision])
    grant=digest([POLICY,actor.id,actor.role,actor.organization_id,actor.patient_id,source_type,ident,revision])
    return PatientSource(patient_id,case_id,content,row.created_at,version,int(version[:12],16)+1,grant,source_type,ident)

def recheck(db,actor,source):
    db.flush();db.expire_all()
    current=selected(db,actor,source.patient_id,source.source_id,source.source_type)
    if current.source_version!=source.source_version or current.grant_version!=source.grant_version:abort(409)
