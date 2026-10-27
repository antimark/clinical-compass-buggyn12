"""Evaluation-only protected signal workflow and opaque test inbox."""
import json,uuid
from flask import request,abort
from sqlalchemy import select,update
from werkzeug.exceptions import HTTPException
from .safety_models import SafetyDetection,SafetyOutbox,SafetyInbox,SafetyAction
from .safety_service import authorize,dto,enabled,audit
from .safety_worker import SafetyRuntime
from .clinical_copilot_services import now
from .clinical_intelligence_sources import digest
from .clinical_intelligence_review_services import receipt_key,safe_storage_errors,final_check
BASE='/api/v1/safety-signals'

def register_safety_routes(app,SessionLocal,current_user,require_role,error,utc_now):
    runtime=SafetyRuntime(app,SessionLocal);app.extensions['safety_runtime']=runtime
    if enabled(app) and app.config.get('SAFETY_AUTOSTART',not app.testing):runtime.start()
    @app.before_request
    def safety_guard():
        if request.path.startswith((BASE,'/api/v1/safety-inbox')):
            if not enabled(app):abort(403)
            if request.content_length and request.content_length>4096:abort(413)
            if request.args:abort(422)
    @app.get(BASE)
    @safe_storage_errors
    def safety_list():
        with SessionLocal() as db:
            doctor=require_role(db,'doctor');items=[]
            ids=db.scalars(select(SafetyDetection.signal_id).where(SafetyDetection.recipient_id==doctor.id,SafetyDetection.tenant_id==doctor.organization_id,SafetyDetection.signal_id.is_not(None))).all()
            for ident in ids:
                try:row,_=authorize(db,doctor,ident)
                except HTTPException:continue
                items.append(dto(db,row))
            items.sort(key=lambda x:(x['critical'],x['created_at']),reverse=True)
            return dict(items=items,clinical_review_status='experimental_needs_validation')
    @app.get(BASE+'/<ident>')
    @safe_storage_errors
    def safety_detail(ident):
        with SessionLocal() as db:
            doctor=require_role(db,'doctor');row,_=authorize(db,doctor,ident)
            return dto(db,row)
    def change(ident,action):
        body=request.get_json(silent=True)
        required={'revision'} if action=='seen' else {'revision','confirmed','idempotency_key'}
        if not isinstance(body,dict) or set(body)!=required or type(body.get('revision')) is not int:abort(422)
        if action=='acknowledged' and body['confirmed'] is not True:abort(422)
        with SessionLocal() as db:
            doctor=require_role(db,'doctor');row,source=authorize(db,doctor,ident,lock=True)
            key=receipt_key(body.get('idempotency_key')) if action=='acknowledged' else None
            fingerprint=digest([ident,action,body])
            if key:
                prior=db.scalar(select(SafetyAction).where(SafetyAction.actor_id==doctor.id,SafetyAction.key_hash==key))
                if prior:
                    if prior.request_digest!=fingerprint:abort(409)
                    return dto(db,row)
            if row.revision!=body['revision']:abort(409)
            if row.workflow_status=='acknowledged' or (action=='seen' and row.workflow_status!='unseen'):abort(409)
            revision=row.revision+1
            changed=db.execute(update(SafetyDetection).where(SafetyDetection.id==row.id,SafetyDetection.revision==body['revision']).values(revision=revision,workflow_status=action))
            if changed.rowcount!=1:abort(409)
            db.add(SafetyAction(id='sa_'+uuid.uuid4().hex,detection_id=row.id,actor_id=doctor.id,revision=revision,action=action,key_hash=key,request_digest=fingerprint,created_at=now()))
            audit(db,doctor.id,'safety_'+action,row.id)
            final_check(app,db,doctor,source)
            db.commit();db.refresh(row)
            return dto(db,row)
    @app.post(BASE+'/<ident>/seen')
    @safe_storage_errors
    def safety_seen(ident):return change(ident,'seen')
    @app.post(BASE+'/<ident>/ack')
    @safe_storage_errors
    def safety_ack(ident):return change(ident,'acknowledged')
    @app.get('/api/v1/safety-inbox')
    @safe_storage_errors
    def safety_inbox():
        with SessionLocal() as db:
            doctor=require_role(db,'doctor');items=[]
            # Receiver metadata is reauthorized too; revoked doctor cannot infer counts.
            pairs=db.execute(select(SafetyInbox.id,SafetyDetection.signal_id).join(SafetyOutbox,SafetyOutbox.id==SafetyInbox.outbox_id).join(SafetyDetection,SafetyDetection.id==SafetyOutbox.detection_id).where(SafetyInbox.recipient_id==doctor.id)).all()
            for receipt,signal in pairs:
                try:authorize(db,doctor,signal)
                except HTTPException:continue
                item=db.get(SafetyInbox,receipt)
                items.append(dict(receipt=item.id,received_at=item.received_at,envelope=json.loads(item.envelope_json)))
            return dict(items=items,transport='protected_local_test_inbox',clinical_response_guaranteed=False)
