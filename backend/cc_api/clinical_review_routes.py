"""Authenticated explicit field review and pending specialist review packets."""
import json
from flask import abort,request
from sqlalchemy import select,update
from .verification import workspace_enabled
from .clinical_review_models import SummaryField,SummaryFieldRevision,EncounterAddendum,ClinicalReviewPacket
from .clinical_review_services import (draft_access,create_fields,field_payload,review_field,
    encounter_access,add_encounter_addendum,classify_decision,create_review_packet,review_packet_access)
BASE='/api/v1/clinical-review'


def register_clinical_review_routes(app,SessionLocal,current_user,require_role,error,utc_now):
    @app.before_request
    def clinical_review_guard():
        if request.path.startswith(BASE+'/') and not workspace_enabled(app.config):
            return error(403,'SYNTHETIC_PROFILE_REQUIRED','Доступно только в синтетической среде')
    def actor(db):
        user=current_user(db)
        if not user:abort(401)
        return user
    def body(keys):
        value=request.get_json(silent=True)
        if not isinstance(value,dict) or set(value)-set(keys):abort(422)
        return value
    def dto(row):return {column.name:getattr(row,column.name) for column in row.__table__.columns}

    @app.get(BASE+'/summary-drafts/<draft_id>/fields')
    def clinical_review_fields(draft_id):
        with SessionLocal() as db:
            user=actor(db);draft_access(db,user,draft_id)
            rows=db.scalars(select(SummaryField).where(SummaryField.draft_id==draft_id).order_by(SummaryField.created_at,SummaryField.id)).all()
            return {'items':[field_payload(row) for row in rows], 'clinical_record_updated':False}

    @app.post(BASE+'/summary-drafts/<draft_id>/fields')
    def clinical_review_propose_fields(draft_id):
        data=body(('source_version','fields'))
        with SessionLocal.begin() as db:
            rows=create_fields(db,require_role(db,'patient'),draft_id,data.get('source_version'),data.get('fields'))
            return {'items':[field_payload(row) for row in rows], 'clinical_record_updated':False},201

    @app.post(BASE+'/summary-drafts/<draft_id>/revoke')
    def clinical_review_revoke_sharing(draft_id):
        from .extension_models import AISummaryDraft
        from .clinical_review_services import audit
        body(())
        with SessionLocal.begin() as db:
            user=require_role(db,'patient')
            changed=db.execute(update(AISummaryDraft).where(AISummaryDraft.id==draft_id,
                AISummaryDraft.patient_user_id==user.id).values(state='revoked'))
            if changed.rowcount!=1:abort(404)
            audit(db,user,'summary_sharing_revoked','ai_summary',draft_id)
            return {'id':draft_id,'state':'revoked'}

    @app.post(BASE+'/fields/<field_id>/review')
    def clinical_review_review_field(field_id):
        data=body(('revision','action','value'))
        with SessionLocal.begin() as db:
            row=review_field(db,require_role(db,'doctor'),field_id,data.get('revision'),data.get('action'),data.get('value'))
            return {**field_payload(row),'clinical_record_updated':False}

    @app.get(BASE+'/fields/<field_id>/history')
    def clinical_review_field_history(field_id):
        with SessionLocal() as db:
            user=actor(db)
            metadata=db.execute(select(SummaryField.draft_id).where(SummaryField.id==field_id)).first()
            if not metadata:abort(404)
            draft_access(db,user,metadata.draft_id)
            return {'items':[dict(revision=x.revision,action=x.action,actor_id=x.actor_id,created_at=x.created_at,
                snapshot=json.loads(x.snapshot_json)) for x in db.scalars(select(SummaryFieldRevision)
                .where(SummaryFieldRevision.field_id==field_id).order_by(SummaryFieldRevision.revision)).all()]}

    @app.get(BASE+'/encounters/<encounter_id>/addenda')
    def clinical_review_addenda(encounter_id):
        with SessionLocal() as db:
            encounter_access(db,require_role(db,'doctor'),encounter_id)
            return {'items':[dto(x) for x in db.scalars(select(EncounterAddendum)
                .where(EncounterAddendum.encounter_id==encounter_id).order_by(EncounterAddendum.created_at,EncounterAddendum.id)).all()]}

    @app.post(BASE+'/encounters/<encounter_id>/addenda')
    def clinical_review_add_addendum(encounter_id):
        data=body(('text','reason'))
        with SessionLocal.begin() as db:
            row=add_encounter_addendum(db,require_role(db,'doctor'),encounter_id,data.get('text'),data.get('reason'))
            return dto(row),201

    @app.post(BASE+'/decisions/<decision_id>/classification')
    def clinical_review_classify_decision(decision_id):
        data=body(('code','version'))
        with SessionLocal.begin() as db:
            row=classify_decision(db,require_role(db,'doctor'),decision_id,data.get('code'),data.get('version'))
            return dto(row)

    @app.get(BASE+'/care-plans/<plan_id>/amendments')
    def clinical_review_plan_amendments(plan_id):
        from .released_plan_access import require_released_plan
        from .clinical_workflow_models import ClinicalDocument
        from .clinical_workflow_services import document_access,document_payload
        from .p0_models import CarePlan
        with SessionLocal() as db:
            user=actor(db)
            metadata=db.execute(select(CarePlan.patient_id,CarePlan.clinician_id).where(CarePlan.id==plan_id)).first()
            if not metadata:abort(404)
            if plan_id.startswith('cdoc_'):
                document_access(db,user,plan_id)
            else:
                if user.role!='doctor' or metadata.clinician_id!=user.id:abort(404)
                from .clinical_review_services import clinical_access
                clinical_access(db,user,metadata.patient_id)
            rows=[]
            for ident in db.scalars(select(ClinicalDocument.id).where(ClinicalDocument.parent_id==plan_id)).all():
                from werkzeug.exceptions import HTTPException
                try:doc=document_access(db,user,ident)
                except HTTPException:continue
                rows.append(document_payload(db,doc,patient=user.role=='patient'))
            return {'items':rows,'amendment_workflow':'explicit_new_signed_document'}

    @app.post(BASE+'/review-packets')
    def clinical_review_request_packet():
        data=body(('source_kind','source_id','source_version','review_question'))
        with SessionLocal.begin() as db:
            row=create_review_packet(db,require_role(db,'doctor'),data.get('source_kind'),data.get('source_id'),data.get('source_version'),data.get('review_question'))
            return {'id':row.id,'status':row.status,'source_sha256':row.content_sha256,'medical_approval':'pending_actual_specialist_review'},201

    @app.get(BASE+'/review-packets')
    def clinical_review_packets():
        with SessionLocal() as db:
            user=require_role(db,'doctor');items=[]
            from werkzeug.exceptions import HTTPException
            for row in db.scalars(select(ClinicalReviewPacket).where(ClinicalReviewPacket.creator_id==user.id)).all():
                try:review_packet_access(db,user,row)
                except HTTPException:continue
                items.append(dict(id=row.id,status=row.status,source_kind=row.source_kind,source_id=row.source_id,
                    source_version=row.source_version,source_sha256=row.content_sha256,requested_at=row.requested_at))
            return {'items':items,'medical_approval':'pending_actual_specialist_review'}

    @app.get(BASE+'/review-packets/<packet_id>')
    def clinical_review_packet(packet_id):
        with SessionLocal() as db:
            row=review_packet_access(db,require_role(db,'doctor'),db.get(ClinicalReviewPacket,packet_id))
            return dict(id=row.id,status=row.status,packet=json.loads(row.packet_json),requested_at=row.requested_at)
