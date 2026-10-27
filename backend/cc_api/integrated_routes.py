"""Additional resource-specific endpoints. Synthetic-only prototype; explicit server ACL.

Patient-submitted data and clinician-confirmed data remain separate sources.
"""
import hashlib
import hmac
import json
import os
import statistics
import uuid
from types import SimpleNamespace
from datetime import datetime, timezone
from flask import request, abort, Response
from sqlalchemy import select, update
from .models import DoctorPatientLink, User, Checkin, Patient
from .onboarding_models import PatientConsent
from .extension_models import (Audit, ClinicalCondition, MedicationRecord, QuestionnaireAssignment,
    ResearchObservation, Message, PrevisitCase, Appointment, CareTeamVisibility, AISummaryDraft)

from .instruments import INSTRUMENTS, numeric_total
from .research import aggregate_observations
from .messaging import pair_thread_key
from .ai_adapter import SummaryRequest, summarize, AdapterDisabled, AdapterUnavailable
from .doctor_access import authorized_patient


def identifier(): return uuid.uuid4().hex[:20]
def stamp(): return datetime.now(timezone.utc).isoformat()
def fields(o): return {c.name:getattr(o,c.name) for c in o.__table__.columns}


def register_integrated_routes(app, SessionLocal, current_user, require_role, error, utc_now):
    def actor(db):
        user = current_user(db)
        if not user: abort(401)
        return user

    def link_for(db, doctor, patient_id):
        result = db.scalar(select(DoctorPatientLink).where(
            DoctorPatientLink.doctor_id == doctor.id, DoctorPatientLink.patient_id == patient_id))
        if not result: abort(404)
        # Tenant-scoped clinical relationships, not just a guessed resource ID.
        patient_user = db.scalar(select(User).where(User.patient_id == patient_id, User.role == 'patient'))
        if not patient_user: abort(404)
        if patient_user.organization_id != doctor.organization_id: abort(403)
        authorized_patient(db, doctor, patient_id, None)
        granted = set(result.categories.split(','))
        ledgers = db.scalars(select(PatientConsent).where(PatientConsent.patient_user_id == patient_user.id,
            PatientConsent.doctor_id == doctor.id)).all()
        if ledgers:
            granted &= set().union(*(set(c.categories.split(',')) for c in ledgers if c.revoked_at is None))
        return SimpleNamespace(categories=','.join(sorted(granted)))

    def write_audit(db, u, action, objtype, id_):
        db.add(Audit(id=identifier(), actor=u.id, action=action, object_type=objtype,
                     object_id=id_, created_at=stamp()))

    @app.get('/api/v1/patients/me/clinical')
    def patient_clinical():
        with SessionLocal() as db:
            u = require_role(db, 'patient')
            diagnoses = list(db.scalars(select(ClinicalCondition).where(ClinicalCondition.patient_id == u.patient_id)))
            meds = list(db.scalars(select(MedicationRecord).where(MedicationRecord.patient_id == u.patient_id)))
            return {'diagnoses':[fields(c) for c in diagnoses], 'medications':[fields(m) for m in meds],
                    'data_source':'clinician_confirmed_or_patient_reported_as_labeled'}

    @app.get('/api/v1/doctors/me/patients/<patient_id>/clinical')
    def clinician_clinical(patient_id):
        with SessionLocal() as db:
            u = require_role(db, 'doctor')
            scope = set(link_for(db,u,patient_id).categories.split(','))
            result = {'patient_ref':patient_id, 'scope':sorted(scope)}
            if 'diagnosis' in scope:
                result['diagnoses'] = [fields(c) for c in db.scalars(select(ClinicalCondition).where(ClinicalCondition.patient_id == patient_id))]
            if 'medications' in scope:
                result['medications'] = [fields(m) for m in db.scalars(select(MedicationRecord).where(MedicationRecord.patient_id == patient_id))]
            return result

    @app.post('/api/v1/doctors/me/patients/<patient_id>/diagnoses')
    def add_clinician_diagnosis(patient_id):
        b = request.get_json(silent=True) or {}
        if not isinstance(b.get('label'),str) or not 2 <= len(b['label'].strip()) <= 160:
            return error(422, 'INVALID_LABEL', 'Enter a diagnosis label')
        with SessionLocal.begin() as db:
            u = require_role(db,'doctor')
            if 'diagnosis' not in link_for(db,u,patient_id).categories.split(','): abort(403)
            c = ClinicalCondition(id=identifier(), patient_id=patient_id, clinician_id=u.id,
                label=b['label'].strip(), status='active', confirmed_at=stamp())
            db.add(c);write_audit(db,u,'diagnosis_confirmed','clinical_condition',c.id)
            return fields(c),201

    @app.post('/api/v1/doctors/me/patients/<patient_id>/medications')
    def add_medication(patient_id):
        b = request.get_json(silent=True) or {}
        if not isinstance(b.get('label'),str) or not 1 <= len(b['label'].strip()) <= 160:
            return error(422, 'INVALID_LABEL', 'Enter a medication label')
        with SessionLocal.begin() as db:
            u=require_role(db,'doctor')
            if 'medications' not in link_for(db,u,patient_id).categories.split(','): abort(403)
            m=MedicationRecord(id=identifier(),patient_id=patient_id,clinician_id=u.id,
                label=b['label'].strip(),source='clinician',status='active')
            db.add(m);write_audit(db,u,'medication_updated','medication',m.id)
            return fields(m),201

    @app.get('/api/v1/instruments')
    def instruments():
        return {'items':[{'id':k,**v} for k,v in INSTRUMENTS.items()],
                'notice':'Metadata only. Do not substitute for approved instrument text or clinical interpretation.'}

    @app.post('/api/v1/instruments/assignments')
    def assign_questionnaire():
        b=request.get_json(silent=True) or {}
        if b.get('instrument_id') not in INSTRUMENTS: return error(422,'INVALID_INSTRUMENT','Unknown instrument')
        with SessionLocal.begin() as db:
            u=require_role(db,'doctor');patient_id=b.get('patient_id','')
            if 'symptoms' not in link_for(db,u,patient_id).categories.split(','): abort(403)
            instr=INSTRUMENTS[b['instrument_id']]
            a=QuestionnaireAssignment(id=identifier(),patient_id=patient_id,clinician_id=u.id,
                instrument_id=b['instrument_id'],instrument_version=instr['version'],status='assigned')
            db.add(a);write_audit(db,u,'instrument_assigned','assignment',a.id)
            return {'id':a.id,'instrument_id':a.instrument_id,'status':a.status},201

    @app.get('/api/v1/instruments/assignments')
    def assignments():
        with SessionLocal() as db:
            u=actor(db)
            if u.role == 'patient': q=select(QuestionnaireAssignment).where(QuestionnaireAssignment.patient_id==u.patient_id)
            elif u.role == 'doctor':
                q=(select(QuestionnaireAssignment).join(DoctorPatientLink,
                    (DoctorPatientLink.patient_id==QuestionnaireAssignment.patient_id) &
                    (DoctorPatientLink.doctor_id==u.id))
                    .join(User,(User.patient_id==QuestionnaireAssignment.patient_id) &
                          (User.role=='patient') & (User.organization_id==u.organization_id))
                    .where(QuestionnaireAssignment.clinician_id==u.id,DoctorPatientLink.categories.contains('symptoms')))
            else: abort(403)
            return {'items':[fields(a) for a in db.scalars(q)]}

    @app.post('/api/v1/instruments/assignments/<assignment_id>/submit')
    def submit_questionnaire(assignment_id):
        b=request.get_json(silent=True) or {}
        with SessionLocal.begin() as db:
            u=require_role(db,'patient');a=db.get(QuestionnaireAssignment,assignment_id)
            if not a or a.patient_id!=u.patient_id: abort(404)
            if a.status!='assigned': return error(409,'ALREADY_SUBMITTED','Assignment already submitted')
            spec=INSTRUMENTS[a.instrument_id]
            scores=b.get('scores')
            try: total=numeric_total(a.instrument_id,scores)
            except ValueError: return error(422,'INVALID_SCORES','Incorrect item count or response bounds')
            # Raw scores are self-report, not diagnosis; no external scoring/AI.
            a.response_json=json.dumps({'scores':scores,'total':total,'source':'patient_self_report'})
            a.status='submitted';a.submitted_at=stamp()
            write_audit(db,u,'instrument_submitted','assignment',a.id)
            return {'id':a.id,'status':a.status,'total':total,'max_score':spec['max_score']}

    @app.get('/api/v1/patient/care-team-visibility')
    def visibility_list():
        with SessionLocal() as db:
            u=require_role(db,'patient')
            records=db.scalars(select(CareTeamVisibility).where(CareTeamVisibility.patient_id==u.patient_id))
            return {'items':[{'doctor_a':v.doctor_a,'doctor_b':v.doctor_b,'active':bool(v.active)} for v in records]}

    def thread_participants(db,u,kind,other_id):
        other=db.get(User,other_id)
        if kind=='doctor_peer':
            if u.role!='doctor' or not other or other.role!='doctor' or other.id==u.id: abort(403)
            return pair_thread_key(u.id,other_id)
        if kind=='patient_doctor':
            if u.role=='patient' and other and other.role=='doctor':
                link_for(db,other,u.patient_id)
                return pair_thread_key(u.id,other_id)
            if u.role=='doctor' and other and other.role=='patient':
                link_for(db,u,other.patient_id)
                return pair_thread_key(u.id,other_id)
        abort(403)

    @app.get('/api/v1/threads/<kind>/<other_id>/messages')
    def thread_messages(kind,other_id):
        if kind not in ('doctor_peer','patient_doctor'): abort(404)
        with SessionLocal() as db:
            u=actor(db);key=thread_participants(db,u,kind,other_id)
            q=select(Message).where(Message.thread_type==kind,Message.context_id==key).order_by(Message.created_at)
            return {'items':[fields(m) for m in db.scalars(q)]}

    @app.post('/api/v1/threads/<kind>/<other_id>/messages')
    def thread_send(kind,other_id):
        if kind not in ('doctor_peer','patient_doctor'): abort(404)
        body=request.get_json(silent=True) or {};text=body.get('text','')
        if not isinstance(text,str) or not 1<=len(text.strip())<=2000:
            return error(422,'INVALID_MESSAGE','Message must be 1..2000 characters')
        with SessionLocal.begin() as db:
            u=actor(db);key=thread_participants(db,u,kind,other_id)
            m=Message(id=identifier(),thread_type=kind,context_id=key,sender_id=u.id,
                      recipient_id=other_id,text=text.strip(),created_at=stamp())
            db.add(m);write_audit(db,u,'message_sent',kind,key)
            return fields(m),201

    @app.post('/api/v1/previsit-cases/<case_id>/appointment-requests')
    def request_slot(case_id):
        with SessionLocal.begin() as db:
            u=require_role(db,'patient')
            from .booking_services import case_access
            c=case_access(db,u,case_id,mutation=True)
            if c.allowed_until<stamp() or c.status in ('declined','withdrawn','expired'): abort(403)
            existing=db.scalar(select(Appointment).where(Appointment.case_id==case_id, Appointment.status=='requested'))
            if existing: return error(409,'REQUEST_EXISTS','Request pending')
            a=Appointment(id=identifier(),case_id=c.id,doctor_id=c.doctor_id,patient_user_id=u.id,
                proposed_at='',format='unspecified',status='requested')
            db.add(a);write_audit(db,u,'appointment_requested','appointment',a.id)
            return fields(a),201

    @app.get('/api/v1/research/cohorts')
    def cohorts():
        from .legacy_research import legacy_aggregate
        with SessionLocal.begin() as db:
            result=legacy_aggregate(db,require_role(db,'researcher'),app.config['SECRET_KEY'],
                request.args.get('study_id','study_demo_v1'),request.args.get('cohort'))
            return {**result,'dataset':'study_demo_v1','measure':'synthetic_mood','small_cell_threshold':result['min_cell'],
                'missingness':'null excluded from mean; counts explicit'}

    @app.get('/api/v1/research/export')
    def research_export():
        result=cohorts()
        return Response(json.dumps(result,ensure_ascii=False),mimetype='application/json',
            headers={'Content-Disposition':'attachment; filename=synthetic-aggregate.json','Cache-Control':'no-store'})

    @app.post('/api/v1/ai/summary-drafts')
    def ai_draft():
        b=request.get_json(silent=True) or {}
        mode=os.environ.get('CC_AI_MODE','disabled')
        try:
            # Fail closed before any database retrieval if adapter is disabled or unavailable.
            if mode=='disabled':raise AdapterDisabled()
            if mode=='approved_provider':raise AdapterUnavailable()
            if mode!='deterministic_mock':raise ValueError('invalid adapter')
        except AdapterDisabled:return error(503,'AI_DISABLED','AI summaries disabled')
        except AdapterUnavailable:return error(501,'PROVIDER_UNAVAILABLE','External AI provider not connected in prototype')
        except ValueError:return error(503,'CONFIG_ERROR','Unknown adapter mode')
        with SessionLocal.begin() as db:
            u=require_role(db,'patient');doctor=db.get(User,b.get('recipient_doctor_id',''))
            if not doctor or doctor.role!='doctor': abort(404)
            link_for(db,doctor,u.patient_id)
            observations=list(db.scalars(select(Checkin).where(Checkin.patient_id==u.patient_id).order_by(Checkin.recorded_at.desc()).limit(7)))
            # Minimal deterministic template; no patient text, name, diagnosis, or prompt to any provider.
            content=summarize('deterministic_mock',SummaryRequest(observation_count=len(observations))).content
            a=AISummaryDraft(id=identifier(),patient_user_id=u.id,recipient_doctor_id=doctor.id,
                content=content,state='needs_review',created_at=stamp())
            db.add(a);write_audit(db,u,'ai_draft_created','ai_summary',a.id)
            return fields(a),201

    @app.post('/api/v1/ai/summary-drafts/<draft_id>/approve')
    def approve_ai(draft_id):
        body=request.get_json(silent=True) or {}
        if body.get('approve') is not True:return error(422,'APPROVAL_REQUIRED','Explicit recipient approval required')
        with SessionLocal.begin() as db:
            u=require_role(db,'patient');a=db.get(AISummaryDraft,draft_id)
            if not a or a.patient_user_id!=u.id:abort(404)
            if a.state!='needs_review':return error(409,'FINALIZED','Draft already finalized')
            if 'symptoms' not in link_for(db,db.get(User,a.recipient_doctor_id),u.patient_id).categories.split(','):abort(403)
            a.state='approved_for_recipient';write_audit(db,u,'ai_draft_approved','ai_summary',a.id)
            return {'id':a.id,'state':a.state,'recipient_doctor_id':a.recipient_doctor_id}

    @app.get('/api/v1/doctors/me/ai-summaries')
    def approved_ai():
        with SessionLocal() as db:
            u=require_role(db,'doctor')
            metadata=db.execute(select(AISummaryDraft.id,User.patient_id)
                .join(User,User.id==AISummaryDraft.patient_user_id)
                .where(AISummaryDraft.recipient_doctor_id==u.id,
                    AISummaryDraft.state=='approved_for_recipient',User.role=='patient',
                    User.organization_id==u.organization_id)).all()
            from werkzeug.exceptions import HTTPException
            output=[]
            for reference in metadata:
                try:
                    for scope in ('symptoms','diagnosis','medications'):
                        authorized_patient(db,u,reference.patient_id,scope)
                except HTTPException:continue
                item=db.get(AISummaryDraft,reference.id)
                output.append({'id':item.id,'content':item.content,'created_at':item.created_at})
            return {'items':output}

    @app.get('/api/v1/patients/me/check-ins')
    def list_checkins():
        with SessionLocal() as db:
            u=require_role(db,'patient')
            items=list(db.scalars(select(Checkin).where(Checkin.patient_id==u.patient_id)
                .order_by(Checkin.recorded_at.desc()).limit(90)))
            return {'items':[{'id':o.id,'recorded_at':o.recorded_at,'mood_score':o.mood_score,
                'comparison':o.comparison,'source_type':'patient_self_report'} for o in items]}

    @app.get('/api/v1/patients/me/links')
    def patient_doctor_links():
        with SessionLocal() as db:
            u=require_role(db,'patient')
            links=list(db.scalars(select(DoctorPatientLink).where(DoctorPatientLink.patient_id==u.patient_id)))
            doctors=[db.get(User,l.doctor_id) for l in links]
            return {'items':[{'id':d.id,'display_name':d.display_name,'specialty':d.specialty} for d in doctors
                if d and d.organization_id==u.organization_id]}

    @app.get('/api/v1/doctors/me/linked-patients')
    def doctor_linked_patient_accounts():
        with SessionLocal() as db:
            u=require_role(db,'doctor')
            links=list(db.scalars(select(DoctorPatientLink).where(DoctorPatientLink.doctor_id==u.id)))
            from werkzeug.exceptions import HTTPException
            accounts=[]
            for link in links:
                try:accounts.append(authorized_patient(db,u,link.patient_id,None))
                except HTTPException:continue
            return {'items':[{'id':a.id,'patient_ref':a.patient_id,'display_name':a.display_name} for a in accounts]}

    @app.delete('/api/v1/patients/me/clinical-links/<doctor_id>')
    def revoke_clinical_link(doctor_id):
        with SessionLocal.begin() as db:
            u=require_role(db,'patient')
            link=db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.doctor_id==doctor_id,
                                                        DoctorPatientLink.patient_id==u.patient_id))
            if not link:abort(404)
            # Lock the consent rows before touching the link, matching publication lock order.
            consents=list(db.scalars(select(PatientConsent).where(
                PatientConsent.patient_user_id==u.id,PatientConsent.doctor_id==doctor_id,
                PatientConsent.revoked_at.is_(None)).with_for_update()))
            for consent in consents:consent.revoked_at=stamp()
            db.flush()
            db.delete(link)
            # Revoke all paired disclosure grants involving this doctor too; re-linking never resurrects them.
            for visibility in db.scalars(select(CareTeamVisibility).where(CareTeamVisibility.patient_id==u.patient_id)):
                if doctor_id in (visibility.doctor_a,visibility.doctor_b):visibility.active=0
            write_audit(db,u,'clinical_link_revoked','clinical_link',doctor_id)
            return {'status':'revoked','doctor_id':doctor_id,
                'affected_scopes':[], 'pair_visibility_revoked':True}

    @app.post('/api/v1/previsit-cases/<case_id>/withdraw')
    def withdraw_previsit(case_id):
        with SessionLocal.begin() as db:
            u=require_role(db,'patient')
            c=db.get(PrevisitCase,case_id)
            if not c or c.patient_user_id!=u.id:abort(404)
            if c.status=='withdrawn':return error(409,'ALREADY_WITHDRAWN','Case withdrawn')
            c.status='withdrawn';write_audit(db,u,'case_consent_withdrawn','previsit',case_id)
            return {'id':c.id,'status':'withdrawn'}
