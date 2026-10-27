"""Incremental synthetic P0 vertical slices. Missing production prerequisites stay blocked."""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from flask import abort, request
from sqlalchemy import select, update, func
from .models import User, Patient, DoctorPatientLink, Checkin, Alert
from .extension_models import (Audit, Appointment, AISummaryDraft, ClinicalCondition,
                               MedicationRecord, ResearchObservation)
from .p0_models import (CarePlan, PlanItem, PlanEvent, AdverseEvent, Encounter,
    ClinicalDecision, AlertReview, DatasetDefinition, UserNotification, SummaryRevision,
    ReferenceArticle)
from .research import aggregate_observations
from .released_plan_access import plan_visible, require_released_plan
from .doctor_access import authorized_patient
from .physician_history_models import AdverseEventReviewRevision

TYPES={'medication','consultation','measurement','behavioral','action','custom'}
OUTCOMES={'completed','missed','uncertain','partial'}

def stamp():return datetime.now(timezone.utc).isoformat()
def uid():return uuid.uuid4().hex[:20]
def obj(item):return {col.name:getattr(item,col.name) for col in item.__table__.columns}
def bounded(value, limit):return isinstance(value,str) and 1<=len(value.strip())<=limit

def register_p0_routes(app, SessionLocal, current_user, require_role, error, utc_now):
    def actor(db):
        user=current_user(db)
        if not user:abort(401)
        return user

    def patient_for_doctor(db, clinician, patient_id, scope, lock=False):
        authorized_patient(db,clinician,patient_id,scope,lock=lock)
        patient=db.get(Patient,patient_id)
        if not patient:abort(404)
        return patient

    def plan_access(db, u, plan):
        if not plan:abort(404)
        require_released_plan(db,u,plan)
        if u.role=='patient' and plan.patient_id==u.patient_id:return
        if u.role=='doctor':patient_for_doctor(db,u,plan.patient_id,'medications');return
        abort(404)

    def audit(db,actor_id,verb,kind,item):
        db.add(Audit(id=uid(),actor=actor_id,action=verb,object_type=kind,object_id=item,created_at=stamp()))

    def notice(db,who,category,message):
        db.add(UserNotification(id=uid(),recipient_id=who,category=category,
                                text=message[:300],created_at=stamp()))

    def data():
        body=request.get_json(silent=True)
        return body if isinstance(body,dict) else {}

    @app.get('/api/v1/p0/auth/capabilities')
    def p0_auth_capabilities():
        from .verification import synthetic_enabled
        from .oidc_browser import settings
        from .staff_enrollment_services import invited_enrollment_enabled
        return {'synthetic_registration_enabled': synthetic_enabled(app.config),
                'synthetic_email_provider': 'synthetic_auto' if synthetic_enabled(app.config) else 'disabled',
                'synthetic_professional_provider': 'synthetic_auto' if synthetic_enabled(app.config) else 'disabled',
                'production_verification': 'DEFERRED_BY_PRODUCT_DECISION',
                'registration_enabled':False,'oidc_interactive_enabled':settings() is not None,
                'synthetic_invited_enrollment_enabled':invited_enrollment_enabled(app.config),
                'verified_staff_enrollment_enabled':False,
                'demo_mode':bool(app.config['DEMO_MODE']),
                'reason':'Real email and professional verification remain deferred; actual OIDC and synthetic invited enrollment depend on explicit configuration. Infrastructure test evidence is separate from production acceptance.'}

    @app.get('/api/v1/p0/notifications')
    def p0_notifications():
        with SessionLocal() as db:
            u=actor(db)
            entries=db.scalars(select(UserNotification).where(UserNotification.recipient_id==u.id)
                  .order_by(UserNotification.created_at.desc()).limit(100))
            from .clinical_review_services import notification_destination
            return {'items':[{**obj(n),'href':notification_destination(db,u,n)} for n in entries]}

    @app.post('/api/v1/p0/notifications/<nid>/read')
    def p0_read_notification(nid):
        with SessionLocal.begin() as db:
            u=actor(db);n=db.get(UserNotification,nid)
            if not n or n.recipient_id!=u.id:abort(404)
            if not n.read_at:n.read_at=stamp()
            return {'id':n.id,'read_at':n.read_at}

    @app.get('/api/v1/p0/care-plans')
    def p0_plans():
        with SessionLocal() as db:
            u=actor(db)
            if u.role=='patient':
                q=select(CarePlan).where(CarePlan.patient_id==u.patient_id,CarePlan.status=='active')
            elif u.role=='doctor':
                pid=request.args.get('patient_id','')
                patient_for_doctor(db,u,pid,'medications')
                q=select(CarePlan).where(CarePlan.patient_id==pid)
            else:abort(403)
            plans=list(db.scalars(q.order_by(CarePlan.created_at.desc())))
            result=[]
            for p in plans:
                if not plan_visible(db,u,p):continue
                items=list(db.scalars(select(PlanItem).where(PlanItem.plan_id==p.id)))
                entry=obj(p);entry['items']=[]
                for item in items:
                    it=obj(item)
                    events=list(db.scalars(select(PlanEvent).where(PlanEvent.item_id==item.id).order_by(PlanEvent.reported_at.desc()).limit(10)))
                    it['reports']=[obj(e) for e in events]
                    entry['items'].append(it)
                result.append(entry)
            return {'items':result,'source':'clinician_authored_synthetic_plan'}

    @app.post('/api/v1/p0/care-plans')
    def p0_create_plan():
        b=data();pid=b.get('patient_id','');items=b.get('items')
        if not isinstance(items,list) or not 1<=len(items)<=40:return error(422,'INVALID_ITEMS','Provide 1–40 plan items')
        for item in items:
            if not isinstance(item,dict) or item.get('item_type') not in TYPES or not bounded(item.get('title'),200):
                return error(422,'INVALID_ITEM','Unknown type or title')
            if any(not isinstance(item.get(k,''),str) or len(item.get(k,''))>size for k,size in [('scheduled_at',40),('frequency',120),('completion_criteria',300)]):
                return error(422,'INVALID_ITEM','Invalid plan fields')
        with SessionLocal.begin() as db:
            u=require_role(db,'doctor');patient_for_doctor(db,u,pid,'medications')
            # Compatibility creation now enters the same persisted document
            # lifecycle; signing and release remain two explicit later actions.
            from .clinical_workflow_services import new_document,validate_content,authorize_scopes
            content,scopes=validate_content('treatment','quick',{'items':[
                {k:v for k,v in item.items() if k in ('item_type','title','frequency')}
                for item in items]})
            # Retain legacy scheduling/completion instructions in structured notes.
            for source,target in zip(items,content['items']):
                notes=[]
                if source.get('scheduled_at'):notes.append('Плановое время: '+source['scheduled_at'])
                if source.get('completion_criteria'):notes.append('Критерий выполнения: '+source['completion_criteria'])
                if notes:target['notes']='; '.join(notes)
            authorize_scopes(db,u,pid,scopes,lock=True)
            row=new_document(db,u,pid,'treatment','quick',content,scopes,stamp())
            return {'id':row.id,'status':row.status,'revision':row.revision,
                'publication_required':True,'document_url':'/api/v1/clinical-workflow/documents/'+row.id},201

    @app.post('/api/v1/p0/plan-items/<item_id>/report')
    def p0_report_item(item_id):
        b=data();outcome=b.get('outcome')
        if outcome not in OUTCOMES:return error(422,'INVALID_OUTCOME','Unsupported outcome')
        with SessionLocal.begin() as db:
            u=require_role(db,'patient')
            plan_id=db.scalar(select(PlanItem.plan_id).where(PlanItem.id==item_id))
            plan=db.get(CarePlan,plan_id) if plan_id else None
            if not plan or plan.patient_id!=u.patient_id or plan.status!='active':abort(404)
            require_released_plan(db,u,plan,lock=True)
            item=db.get(PlanItem,item_id)
            event=PlanEvent(id=uid(),item_id=item.id,patient_user_id=u.id,outcome=outcome,reported_at=stamp())
            db.add(event);audit(db,u.id,'plan_progress_reported','plan_item',item_id)
            return obj(event),201

    @app.post('/api/v1/p0/adverse-events')
    def p0_new_event():
        b=data()
        if not bounded(b.get('description'),2000):return error(422,'INVALID_DESCRIPTION','Description required, maximum 2000 characters')
        with SessionLocal.begin() as db:
            u=require_role(db,'patient')
            if not u.patient_id:abort(403)
            event=AdverseEvent(id=uid(),patient_id=u.patient_id,reporter_id=u.id,
                description=b['description'].strip(),status='reported',created_at=stamp())
            db.add(event);audit(db,u.id,'adverse_event_reported','adverse_event',event.id)
            return {'id':event.id,'status':event.status,'causality':'not_assessed'},201

    @app.get('/api/v1/p0/adverse-events')
    def p0_list_events():
        with SessionLocal() as db:
            u=actor(db)
            if u.role=='patient':pid=u.patient_id
            elif u.role=='doctor':
                pid=request.args.get('patient_id','');patient_for_doctor(db,u,pid,'medications')
            else:abort(403)
            result=[obj(x) for x in db.scalars(select(AdverseEvent).where(AdverseEvent.patient_id==pid).order_by(AdverseEvent.created_at.desc()))]
            # Patients do not receive internal clinician review notes before dedicated policy review.
            if u.role=='patient':
                result=[{'id':r['id'],'description':r['description'],'status':r['status'],'created_at':r['created_at']} for r in result]
            else:
                for entry in result:
                    entry['reviews']=[obj(review) for review in db.scalars(select(AdverseEventReviewRevision)
                        .where(AdverseEventReviewRevision.event_id==entry['id'])
                        .order_by(AdverseEventReviewRevision.version))]
            return {'items':result,'causality':'never_automatic'}

    @app.post('/api/v1/p0/adverse-events/<eid>/review')
    def p0_review_event(eid):
        b=data()
        if b.get('status') not in ('assessed','closed') or not bounded(b.get('review_text'),2000):
            return error(422,'INVALID_REVIEW','Explicit clinician assessment required')
        with SessionLocal.begin() as db:
            u=require_role(db,'doctor')
            pid=db.scalar(select(AdverseEvent.patient_id).where(AdverseEvent.id==eid))
            if not pid:abort(404)
            patient_for_doctor(db,u,pid,'medications',lock=True)
            # Serialize repeat assessments after consent locks; retain the old
            # compatibility summary while each assessment is append-only.
            db.execute(update(AdverseEvent).where(AdverseEvent.id==eid).values(status=AdverseEvent.status))
            e=db.get(AdverseEvent,eid,populate_existing=True)
            version=db.scalar(select(func.max(AdverseEventReviewRevision.version))
                .where(AdverseEventReviewRevision.event_id==eid)) or 0
            if not version and e.review_text and e.reviewer_id:
                db.add(AdverseEventReviewRevision(id=uid(),event_id=eid,version=1,
                    status=e.status,review_text=e.review_text,reviewer_id=e.reviewer_id,
                    created_at=e.reviewed_at or e.created_at))
                version=1
            e.status=b['status'];e.review_text=b['review_text'].strip();e.reviewer_id=u.id;e.reviewed_at=stamp()
            db.add(AdverseEventReviewRevision(id=uid(),event_id=eid,version=version+1,
                status=e.status,review_text=e.review_text,reviewer_id=u.id,created_at=e.reviewed_at))
            audit(db,u.id,'adverse_event_reviewed','adverse_event',eid)
            return {'id':eid,'status':e.status,'reviewed_at':e.reviewed_at}

    @app.get('/api/v1/p0/observations/<patient_id>')
    def p0_observations(patient_id):
        with SessionLocal() as db:
            u=require_role(db,'doctor');patient_for_doctor(db,u,patient_id,'symptoms')
            rows=list(db.scalars(select(Checkin).where(Checkin.patient_id==patient_id).order_by(Checkin.recorded_at)))
            return {'items':[{'date':x.recorded_at,'value':x.mood_score,'unit':'1–5 self-report','source':'patient_self_report'} for x in rows],
                    'missingness':'No imputation; no values fabricated'}

    @app.get('/api/v1/p0/history/<patient_id>')
    def p0_history(patient_id):
        with SessionLocal() as db:
            u=require_role(db,'doctor');patient_for_doctor(db,u,patient_id,'diagnosis')
            conditions=[obj(x) for x in db.scalars(select(ClinicalCondition).where(ClinicalCondition.patient_id==patient_id))]
            encounters=[{'id':e.id,'mode':e.mode,'status':e.status,'created_at':e.created_at,'signed_at':e.signed_at} for e in db.scalars(select(Encounter).where(Encounter.patient_id==patient_id))]
            return {'clinician_confirmed_diagnoses':conditions,'encounters':encounters,
                    'patient_reported_problems':'Consult separate consent-scoped intake; not converted to confirmed diagnoses'}

    @app.get('/api/v1/p0/encounters/<patient_id>')
    def p0_encounters(patient_id):
        with SessionLocal() as db:
            u=require_role(db,'doctor');patient_for_doctor(db,u,patient_id,'diagnosis')
            entries=list(db.scalars(select(Encounter).where(Encounter.patient_id==patient_id).order_by(Encounter.created_at.desc())))
            return {'items':[obj(e) for e in entries]}

    @app.post('/api/v1/p0/encounters/<encounter_id>/amend')
    def p0_encounter_addendum(encounter_id):
        from .clinical_review_services import add_encounter_addendum
        b=data()
        with SessionLocal.begin() as db:
            row=add_encounter_addendum(db,require_role(db,'doctor'),encounter_id,b.get('text'),b.get('reason'))
            return obj(row),201

    @app.get('/api/v1/p0/care-plans/amendments')
    def p0_plan_amendments():
        from .clinical_workflow_models import ClinicalDocument
        from .clinical_workflow_services import document_access,document_payload
        from werkzeug.exceptions import HTTPException
        with SessionLocal() as db:
            user=require_role(db,'doctor');items=[]
            ids=db.scalars(select(ClinicalDocument.id).where(ClinicalDocument.clinician_id==user.id,
                ClinicalDocument.kind=='treatment',ClinicalDocument.parent_id.is_not(None))).all()
            for document_id in ids:
                try: row=document_access(db,user,document_id)
                except HTTPException: continue
                items.append(document_payload(db,row))
            return {'items':items,'workflow':'draft_sign_explicit_publication'}

    @app.post('/api/v1/p0/encounters/<patient_id>')
    def p0_new_encounter(patient_id):
        b=data();mode=b.get('mode');narrative=b.get('narrative');assessment=b.get('assessment','');follow_up=b.get('follow_up','')
        if mode not in ('quick','extended') or not bounded(narrative,5000) or not all(isinstance(v,str) and len(v)<=3000 for v in (assessment,follow_up)):
            return error(422,'INVALID_ENCOUNTER','Invalid mode or fields')
        with SessionLocal.begin() as db:
            u=require_role(db,'doctor');patient_for_doctor(db,u,patient_id,'diagnosis')
            e=Encounter(id=uid(),patient_id=patient_id,clinician_id=u.id,mode=mode,
                content_json=json.dumps({'narrative':narrative,'assessment':assessment,'follow_up':follow_up},ensure_ascii=False),
                status='signed' if b.get('sign') is True else 'draft',created_at=stamp(),signed_at=stamp() if b.get('sign') is True else None)
            db.add(e);audit(db,u.id,'encounter_created','encounter',e.id)
            return {'id':e.id,'status':e.status},201

    @app.get('/api/v1/p0/decisions/<patient_id>')
    def p0_decisions(patient_id):
        with SessionLocal() as db:
            u=require_role(db,'doctor');patient_for_doctor(db,u,patient_id,'diagnosis')
            return {'items':[obj(e) for e in db.scalars(select(ClinicalDecision).where(ClinicalDecision.patient_id==patient_id))]}

    @app.post('/api/v1/p0/decisions/<patient_id>')
    def p0_new_decision(patient_id):
        b=data()
        if b.get('explicit_confirmation') is not True or not bounded(b.get('text'),3000):
            return error(422,'CONFIRMATION_REQUIRED','Clinician must explicitly confirm decision')
        with SessionLocal.begin() as db:
            u=require_role(db,'doctor');patient_for_doctor(db,u,patient_id,'diagnosis')
            decision=ClinicalDecision(id=uid(),patient_id=patient_id,clinician_id=u.id,text=b['text'],confirmed_at=stamp())
            db.add(decision);audit(db,u.id,'clinical_decision_confirmed','decision',decision.id)
            return {'id':decision.id,'confirmed_at':decision.confirmed_at},201

    @app.get('/api/v1/p0/alerts/<alert_id>')
    def p0_alert_detail(alert_id):
        with SessionLocal() as db:
            u=require_role(db,'doctor');a=db.get(Alert,alert_id)
            if not a or a.assigned_doctor_id!=u.id:abort(404)
            patient_for_doctor(db,u,a.patient_id,'symptoms')
            return {'alert':obj(a),'reviews':[obj(x) for x in db.scalars(select(AlertReview).where(AlertReview.alert_id==alert_id))],
                    'signal_provenance':'Legacy synthetic fixture; no validated SignalEngine evidence available'}

    @app.post('/api/v1/p0/alerts/<alert_id>/assess')
    def p0_assess_alert(alert_id):
        b=data()
        if b.get('status') not in ('assessed','closed') or not bounded(b.get('assessment'),2000):
            return error(422,'ASSESSMENT_REQUIRED','Explicit assessment required')
        with SessionLocal.begin() as db:
            u=require_role(db,'doctor');a=db.get(Alert,alert_id)
            if not a or a.assigned_doctor_id!=u.id:abort(404)
            patient_for_doctor(db,u,a.patient_id,'symptoms')
            if a.status=='closed':return error(409,'ALERT_CLOSED','Alert already closed')
            review=AlertReview(id=uid(),alert_id=alert_id,clinician_id=u.id,
                assessment=b['assessment'],status=b['status'],created_at=stamp())
            db.add(review);a.status=b['status'];audit(db,u.id,'alert_assessed','alert',alert_id)
            return {'id':review.id,'alert_status':a.status},201

    @app.get('/api/v1/p0/summary-proposals')
    def p0_structured_summary_proposals():
        from .clinical_review_models import SummaryField
        from .clinical_review_services import draft_access,field_payload
        from werkzeug.exceptions import HTTPException
        with SessionLocal() as db:
            doctor=require_role(db,'doctor');items=[]
            ids=db.scalars(select(AISummaryDraft.id).where(AISummaryDraft.recipient_doctor_id==doctor.id,
                AISummaryDraft.state=='approved_for_recipient')).all()
            for draft_id in ids:
                try:draft_access(db,doctor,draft_id)
                except HTTPException:continue
                rows=db.scalars(select(SummaryField).where(SummaryField.draft_id==draft_id)).all()
                if rows:items.append({'draft_id':draft_id,'fields':[field_payload(row) for row in rows]})
            return {'items':items,'clinical_record_updated':False,'requires_explicit_field_review':True}

    @app.get('/api/v1/p0/reference-articles')
    def p0_reference_articles():
        with SessionLocal() as db:
            require_role(db,'doctor')
            return {'items':[obj(x) for x in db.scalars(select(ReferenceArticle).where(ReferenceArticle.approval_status=='approved'))],
                    'note':'No unreviewed or unlicensed clinical text is bundled'}

    @app.get('/api/v1/p0/reference-articles/<article_id>')
    def p0_reference_article(article_id):
        with SessionLocal() as db:
            require_role(db,'doctor');x=db.get(ReferenceArticle,article_id)
            if not x or x.approval_status!='approved':abort(404)
            return obj(x)

    @app.get('/api/v1/p0/clinic/patients')
    def p0_clinic_patients():
        from .admin_privacy_service import projected_patients
        with SessionLocal.begin() as db:
            u=require_role(db,'clinic_admin')
            result=projected_patients(db,u,app.config['SECRET_KEY'],filter_field=request.args.get('filter_field'),
                filter_value=request.args.get('filter_value'),sort_field=request.args.get('sort_field'))
            return {**result,'field_policy':'explicit_patient_controlled_projection'}

    @app.get('/api/v1/p0/clinic/patients/<patient_ref>')
    def p0_clinic_patient(patient_ref):
        from .admin_privacy_service import patient_by_ref,projected_patient
        with SessionLocal.begin() as db:
            u=require_role(db,'clinic_admin')
            person=patient_by_ref(db,u,patient_ref,app.config['SECRET_KEY'])
            return {**projected_patient(db,u,person,app.config['SECRET_KEY']),
                'purpose':'appointment_administration','clinical_record_access':False}

    @app.post('/api/v1/p0/clinic/patients/<patient_ref>/reveal')
    def p0_reveal_contact(patient_ref):
        from .admin_privacy_service import patient_by_ref,projected_patient
        b=data()
        if b.get('purpose')!='appointment_administration' or b.get('requested_fields')!=['contact']:
            return error(422,'PURPOSE_REQUIRED','Укажите цель организации записи и контактные поля')
        with SessionLocal.begin() as db:
            u=require_role(db,'clinic_admin')
            person=patient_by_ref(db,u,patient_ref,app.config['SECRET_KEY'])
            result=projected_patient(db,u,person,app.config['SECRET_KEY'],requested_fields={'phone','email'})
            if not result['fields']:abort(403)
            return {**result,'purpose_grant_verified':True,'purpose':'appointment_administration'}

    @app.get('/api/v1/p0/clinic/appointments')
    def p0_clinic_appointments():
        from .admin_privacy_service import projected_appointments
        with SessionLocal.begin() as db:
            return projected_appointments(db,require_role(db,'clinic_admin'),app.config['SECRET_KEY'])

    @app.post('/api/v1/p0/clinic/appointments/reschedule')
    def p0_clinic_reschedule():
        from .admin_booking_routes import request_admin_reschedule
        from .booking_services import parse,now
        b=data()
        if b.get('new_time') is not None and parse(b['new_time'])<=now():abort(422)
        with SessionLocal.begin() as db:
            row=request_admin_reschedule(db,require_role(db,'clinic_admin'),b.get('appointment_id'),
                b.get('reason') or 'Запрос администратора: '+str(b.get('new_time','другое время')),b.get('doctor_id'))
            return {'id':row.id,'status':row.status,'booking_confirmed':False,
                'requires_physician_proposal':True,'requires_patient_acceptance':True}

    @app.get('/api/v1/p0/dataset-definitions')
    def p0_datasets():
        from .research_workflow_models import ResearchStudyGrant
        from .research_workflow_service import require_grant
        with SessionLocal() as db:
            u=require_role(db,'researcher');require_grant(db,u,'study_demo_v1')
            return {'sources':[{'id':'study_demo_v1','measures':['synthetic_mood'],'cohorts':['A','B']}],
                'items':[obj(x) for x in db.scalars(select(DatasetDefinition).where(DatasetDefinition.researcher_id==u.id))],
                'synthetic_only':True}

    @app.post('/api/v1/p0/dataset-definitions')
    def p0_save_dataset():
        from .research_workflow_service import create_definition
        with SessionLocal.begin() as db:
            result=create_definition(db,require_role(db,'researcher'),data())
            return {**result,'applied_criteria':result['definition']['criteria']},201

    @app.get('/api/v1/p0/dataset-definitions/<definition_id>/compute')
    def p0_compute_dataset(definition_id):
        from .research_workflow_service import compute
        with SessionLocal.begin() as db:
            return compute(db,require_role(db,'researcher'),definition_id,app.config['SECRET_KEY'])

    @app.get('/api/v1/p0/summary-drafts/<draft_id>')
    def p0_get_draft(draft_id):
        with SessionLocal() as db:
            u=require_role(db,'patient');d=db.get(AISummaryDraft,draft_id)
            if not d or d.patient_user_id!=u.id:abort(404)
            return {'id':d.id,'content':d.content,'state':d.state,'recipient_doctor_id':d.recipient_doctor_id,
                    'versions':[{'version':x.version,'created_at':x.created_at} for x in db.scalars(select(SummaryRevision).where(SummaryRevision.draft_id==draft_id))]}

    @app.post('/api/v1/p0/summary-drafts/<draft_id>/edit')
    def p0_edit_draft(draft_id):
        b=data()
        if not isinstance(b.get('content'),str) or len(b['content'])>5000:return error(422,'INVALID_CONTENT','Draft exceeds limit')
        with SessionLocal.begin() as db:
            u=require_role(db,'patient');d=db.get(AISummaryDraft,draft_id)
            if not d or d.patient_user_id!=u.id:abort(404)
            if d.state!='needs_review':return error(409,'DRAFT_LOCKED','Approved draft cannot be silently rewritten')
            revisions=list(db.scalars(select(SummaryRevision).where(SummaryRevision.draft_id==draft_id)))
            version=max((x.version for x in revisions),default=0)+1
            d.content=b['content'];db.add(SummaryRevision(id=uid(),draft_id=d.id,author_id=u.id,
                    version=version,content=d.content,created_at=stamp()))
            audit(db,u.id,'ai_draft_edited','ai_summary',d.id)
            return {'id':d.id,'version':version,'state':d.state}
