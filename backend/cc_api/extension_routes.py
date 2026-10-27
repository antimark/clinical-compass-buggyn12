"""Server-authorized synthetic demo workflows. Never use with real patient data."""
import hashlib, json, secrets, uuid
from datetime import datetime, timedelta, timezone
from flask import request, abort, jsonify
from sqlalchemy import select, update
from .models import User, Patient, DoctorPatientLink
from .extension_models import Invitation, PrevisitCase, Message, Appointment, CareTeamVisibility, Audit

CATEGORIES={'symptoms','diagnosis','medications','severity'}
def now(): return datetime.now(timezone.utc)
def timestamp(): return now().isoformat()
def uid(): return uuid.uuid4().hex[:16]
def digest(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()
def obj(a): return {c.name:getattr(a,c.name) for c in a.__table__.columns}

def register_extension_routes(app, SessionLocal, current_user, require_role, error, utc_now):
    def audit(db,u,action,typ,key): db.add(Audit(id=uid(),actor=u.id,action=action,object_type=typ,object_id=key,created_at=timestamp()))
    def actor(db):
        u=current_user(db)
        if not u: abort(401)
        return u
    def case_for(db,u,case_id,mutation=False):
        meta=db.execute(select(PrevisitCase.doctor_id,PrevisitCase.patient_user_id,
            PrevisitCase.status,PrevisitCase.allowed_until).where(PrevisitCase.id==case_id)).first()
        if not meta:abort(404)
        if u.id not in (meta.patient_user_id,meta.doctor_id):abort(403)
        doctor=db.get(User,meta.doctor_id);patient=db.get(User,meta.patient_user_id)
        if (not doctor or not patient or doctor.role!='doctor' or patient.role!='patient'
                or doctor.organization_id!=patient.organization_id or u.organization_id!=doctor.organization_id):abort(404)
        if mutation:
            db.execute(update(PrevisitCase).where(PrevisitCase.id==case_id).values(status=PrevisitCase.status))
            meta=db.execute(select(PrevisitCase.status,PrevisitCase.allowed_until)
                .where(PrevisitCase.id==case_id)).first()
        if meta.status=='withdrawn' and u.id!=patient.id:abort(403)
        if datetime.fromisoformat(meta.allowed_until.replace('Z','+00:00'))<=now():abort(403)
        return db.get(PrevisitCase,case_id,populate_existing=True)
    @app.get('/api/v1/public/doctors')
    def public_doctors():
        from .profile_services import public_doctor
        with SessionLocal() as db:
            return {'items':[projection for user in db.scalars(select(User).where(User.role=='doctor'))
                             if (projection:=public_doctor(db,user)) is not None]}
    @app.get('/api/v1/public/doctors/<slug>')
    def public_doctor(slug):
        from .profile_services import public_doctor as projection
        with SessionLocal() as db:
            result=projection(db,db.get(User,slug),detail=True)
            if result is None:abort(404)
            return result
    @app.post('/api/v1/invitations')
    def invitation_new():
        body = request.get_json(silent=True) or {}
        target = body.get('target_role')
        categories = body.get('categories', ['symptoms'])
        allowed = {'doctor': {'patient'}, 'clinic_admin': {'doctor'}, 'platform_admin': {'clinic_admin'}}
        if target not in ('patient', 'doctor', 'clinic_admin') or not isinstance(categories, list) or not set(categories) <= CATEGORIES:
            return error(422, 'INVALID_FIELDS', 'Invalid target role or categories')
        with SessionLocal.begin() as db:
            u = actor(db)
            if target not in allowed.get(u.role, set()): abort(403)
            recipient = db.get(User, body.get('recipient_id', ''))
            if not recipient or recipient.role != target:
                return error(422, 'RECIPIENT_REQUIRED', 'Specify an existing verified recipient')
            org = u.organization_id if u.role != 'platform_admin' else recipient.organization_id
            if target != 'clinic_admin' and recipient.organization_id != org: abort(403)
            if target == 'patient' and (not recipient.patient_id or recipient.patient_id != body.get('patient_id') or not db.get(Patient, recipient.patient_id)):
                return error(422, 'PATIENT_BINDING', 'Patient and recipient must match')
            if target != 'patient' and categories:
                return error(422, 'INVALID_SCOPES', 'Staff invitation cannot convey clinical data scopes')
            token = secrets.token_urlsafe(32)
            inv = Invitation(id=uid(), code_hash=digest(token), issuer_id=u.id, target_role=target,
                             recipient_id=recipient.id, patient_id=recipient.patient_id if target == 'patient' else None,
                             categories=','.join(categories), expires_at=(now()+timedelta(days=7)).isoformat(),
                             organization_id=org, status='pending')
            db.add(inv)
            audit(db, u, 'invitation_created', 'invitation', inv.id)
            return {'id':inv.id, 'registration_code':token, 'expires_at':inv.expires_at,
                    'target_role':target, 'recipient_id':recipient.id, 'categories':categories}, 201

    @app.post('/api/v1/invitations/<invitation_id>/revoke')
    def invitation_revoke(invitation_id):
        with SessionLocal.begin() as db:
            u = actor(db)
            inv = db.get(Invitation, invitation_id)
            if not inv or inv.issuer_id != u.id: abort(404)
            if inv.status != 'pending': return error(409, 'NOT_PENDING', 'Invitation already finalized')
            changed=db.execute(update(Invitation).where(Invitation.id==inv.id,Invitation.status=='pending')
                .values(status='revoked',revoked_at=timestamp()))
            if changed.rowcount!=1:return error(409,'NOT_PENDING','Invitation already finalized')
            audit(db, u, 'invitation_revoked', 'invitation', inv.id)
            return {'id':inv.id, 'status':'revoked'}

    @app.post('/api/v1/invitations/accept')
    def invitation_accept():
        body = request.get_json(silent=True) or {}
        token = body.get('registration_code', '')
        if not isinstance(token, str) or not 12 <= len(token) <= 200:
            return error(422, 'INVALID_CODE', 'Invalid code')
        with SessionLocal.begin() as db:
            u = actor(db)
            inv = db.scalar(select(Invitation).where(Invitation.code_hash == digest(token)))
            if not inv or inv.status != 'pending' or inv.expires_at <= timestamp():
                return error(404, 'INVALID_OR_EXPIRED', 'Code missing, used, revoked or expired')
            if inv.target_role != u.role or inv.recipient_id != u.id or inv.organization_id != u.organization_id: abort(403)
            issuer = db.get(User, inv.issuer_id)
            if not issuer or (issuer.role != 'platform_admin' and issuer.organization_id != inv.organization_id): abort(403)
            if inv.target_role == 'patient' and (u.patient_id != inv.patient_id or issuer.role != 'doctor'): abort(403)
            if inv.target_role == 'patient' and (body.get('consent') is not True or body.get('consent_version') != 'clinical-link-v1'):
                return error(422, 'CONSENT_REQUIRED', 'Проверьте категории и явно подтвердите согласие указанной версии')
            # Compare-and-set allows at most one concurrent redemption across workers.
            accepted_at = timestamp()
            result = db.execute(update(Invitation).where(Invitation.id == inv.id, Invitation.status == 'pending',
                             Invitation.expires_at > accepted_at).values(status='accepted', accepted_at=accepted_at))
            if result.rowcount != 1: return error(409, 'REPLAY', 'Invitation already used')
            if inv.target_role == 'patient':
                from .onboarding_models import PatientInvitation, PatientConsent
                shadow = PatientInvitation(id='legacy_' + inv.id, token_hash=digest('legacy:' + inv.code_hash),
                    issuer_id=inv.issuer_id, recipient_hash=digest('legacy-user:' + u.id),
                    organization_id=inv.organization_id, categories=inv.categories, status='accepted',
                    created_at=accepted_at, expires_at=inv.expires_at, accepted_at=accepted_at, patient_user_id=u.id)
                db.add(shadow)
                db.flush()
                db.add(PatientConsent(id='legacy_consent_' + inv.id, patient_user_id=u.id,
                    doctor_id=inv.issuer_id, invitation_id=shadow.id, categories=inv.categories,
                    version='clinical-link-v1', accepted_at=accepted_at))
                link = db.scalar(select(DoctorPatientLink).where(
                    DoctorPatientLink.doctor_id == inv.issuer_id, DoctorPatientLink.patient_id == inv.patient_id))
                if link: link.categories = inv.categories
                else: db.add(DoctorPatientLink(doctor_id=inv.issuer_id, patient_id=inv.patient_id,
                                               categories=inv.categories))
            audit(db, u, 'invitation_accepted', 'invitation', inv.id)
            return {'status':'accepted', 'scope':inv.categories.split(',') if inv.categories else [],
                    'clinical_link_created':inv.target_role == 'patient'}

    @app.post('/api/v1/previsit-cases')
    def new_case():
        body=request.get_json(silent=True) or {}; text=body.get('text',''); symptoms=body.get('symptoms',[]);conditions=body.get('conditions',[])
        if not isinstance(text,str) or not 1<=len(text)<=2000 or not isinstance(symptoms,list) or not isinstance(conditions,list) or len(symptoms)>20 or len(conditions)>20: return error(422,'INVALID_INTAKE','Invalid intake')
        if not all(isinstance(x,str) and len(x)<=80 for x in symptoms+conditions): return error(422,'INVALID_INTAKE','Invalid field')
        with SessionLocal.begin() as db:
            u=require_role(db,'patient'); doc=db.get(User,body.get('doctor_id',''))
            if not doc or doc.role!='doctor' or doc.organization_id!=u.organization_id: abort(404)
            if body.get('case_consent') is not True: return error(422, 'CONSENT_REQUIRED', 'Case-scoped data sharing requires approval')
            c=PrevisitCase(id=uid(),patient_user_id=u.id,doctor_id=doc.id,status='submitted',intake_json=json.dumps({'text':text,'symptoms':symptoms,'conditions':conditions,'questionnaire_results':[]},ensure_ascii=False),created_at=timestamp(),allowed_until=(now()+timedelta(days=90)).isoformat());db.add(c);audit(db,u,'previsit_submitted','previsit',c.id)
            from .safety_service import ingest
            ingest(app,db,c)
            return {'id':c.id,'status':c.status,'intake':json.loads(c.intake_json),
                    'doctor_id':c.doctor_id,'patient_user_id':c.patient_user_id,'created_at':c.created_at},201
    @app.get('/api/v1/previsit-cases')
    def case_list():
        with SessionLocal() as db:
            u=actor(db)
            if u.role not in ('patient','doctor'): abort(403)
            q=select(PrevisitCase.id).where(PrevisitCase.patient_user_id==u.id if u.role=='patient' else PrevisitCase.doctor_id==u.id)
            if u.role=='doctor':q=q.where(PrevisitCase.status!='withdrawn')
            from werkzeug.exceptions import HTTPException
            rows=[]
            for ident in db.scalars(q).all():
                try:c=case_for(db,u,ident)
                except HTTPException:continue
                rows.append({'id':c.id,'status':c.status,'doctor_id':c.doctor_id,'patient_user_id':c.patient_user_id,'created_at':c.created_at})
            return {'items':rows}
    @app.get('/api/v1/previsit-cases/<case_id>')
    def case_detail(case_id):
        with SessionLocal.begin() as db:
            u=actor(db);c=case_for(db,u,case_id);audit(db,u,'previsit_read','previsit',c.id)
            return {'id':c.id,'status':c.status,'intake':json.loads(c.intake_json),'doctor_id':c.doctor_id,'patient_user_id':c.patient_user_id,'patient_ref':db.get(User,c.patient_user_id).patient_id,'created_at':c.created_at}
    @app.post('/api/v1/previsit-cases/<case_id>/review')
    def review_case(case_id):
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) != {'confirmation'} or body['confirmation'] is not True:
            return error(422, 'CONFIRMATION_REQUIRED', 'Подтвердите принятие обращения в работу')
        with SessionLocal.begin() as db:
            doctor = require_role(db, 'doctor')
            case = case_for(db, doctor, case_id, mutation=True)
            if case.doctor_id != doctor.id:
                abort(403)
            if case.status == 'reviewed':
                return {'id': case.id, 'status': case.status}
            if case.status != 'submitted':
                return error(409, 'CASE_CLOSED', 'Обращение недоступно для принятия в работу')
            case.status = 'reviewed'
            audit(db, doctor, 'previsit_reviewed', 'previsit', case.id)
            return {'id': case.id, 'status': case.status}

    @app.get('/api/v1/previsit-cases/<case_id>/messages')
    def case_messages(case_id):
        with SessionLocal() as db:
            u=actor(db);case_for(db,u,case_id)
            return {'items':[obj(m) for m in db.scalars(select(Message).where(Message.thread_type=='previsit',Message.context_id==case_id).order_by(Message.created_at))]}
    @app.post('/api/v1/previsit-cases/<case_id>/messages')
    def case_message_send(case_id):
        text=(request.get_json(silent=True) or {}).get('text','')
        if not isinstance(text,str) or not 1<=len(text.strip())<=2000:return error(422,'INVALID_MESSAGE','Message must be 1-2000 characters')
        with SessionLocal.begin() as db:
            u=actor(db);c=case_for(db,u,case_id,mutation=True)
            if c.status in ('declined', 'withdrawn', 'expired'):
                return error(409, 'CASE_CLOSED', 'This case is closed')
            if u.id == c.patient_user_id and not c.doctor_replied:
                result = db.execute(update(PrevisitCase).where(PrevisitCase.id == case_id,
                    PrevisitCase.first_patient_message == 0, PrevisitCase.doctor_replied == 0)
                    .values(first_patient_message=1))
                if result.rowcount != 1:
                    return error(409, 'WAIT_FOR_DOCTOR', 'Only one initial patient message allowed')
            elif u.id == c.doctor_id:
                c.doctor_replied = 1
            m=Message(id=uid(),thread_type='previsit',context_id=case_id,sender_id=u.id,recipient_id=c.doctor_id if u.role=='patient' else c.patient_user_id,text=text.strip(),created_at=timestamp());db.add(m);audit(db,u,'message_sent','previsit',case_id)
            return obj(m),201
    @app.post('/api/v1/previsit-cases/<case_id>/offers')
    def make_offer(case_id):
        body=request.get_json(silent=True) or {};at=body.get('proposed_at','');fmt=body.get('format','video')
        if fmt not in ('video','audio','in_person') or not isinstance(at,str) or len(at)<10 or len(at)>40:return error(422,'INVALID_OFFER','Invalid time/format')
        with SessionLocal.begin() as db:
            u=require_role(db,'doctor')
            from .booking_services import legacy_offer
            a=legacy_offer(db,u,case_id,at,fmt)
            return obj(a),201
    @app.post('/api/v1/appointments/<appointment_id>/confirm')
    def confirm_offer(appointment_id):
        with SessionLocal.begin() as db:
            from .booking_services import accept_appointment
            u=require_role(db,'patient')
            return obj(accept_appointment(db,u,appointment_id))
    @app.get('/api/v1/appointments')
    def appointments():
        with SessionLocal() as db:
            u=actor(db)
            if u.role not in ('patient','doctor'):abort(403)
            q=select(Appointment).where(Appointment.patient_user_id==u.id if u.role=='patient' else Appointment.doctor_id==u.id)
            return {'items':[obj(a) for a in db.scalars(q)
                if (case := db.get(PrevisitCase,a.case_id)) and (case.status!='withdrawn' or u.role=='patient')]}
    @app.get('/api/v1/doctors/<doctor_id>/shared-patients')
    def shared_patients(doctor_id):
        with SessionLocal() as db:
            u=require_role(db,'doctor');other=db.get(User,doctor_id)
            if not other or other.role!='doctor' or other.organization_id != u.organization_id:abort(404)
            vis=db.scalars(select(CareTeamVisibility).where(CareTeamVisibility.active==1))
            allowed=[]
            for v in vis:
                if {v.doctor_a,v.doctor_b}!={u.id,doctor_id}:continue
                linked=lambda did:db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.doctor_id==did,DoctorPatientLink.patient_id==v.patient_id))
                if linked(u.id) and linked(doctor_id):
                    import os, hmac
                    key=app.config['SECRET_KEY'].encode()
                    ref=hmac.new(key, ('shared:'+':'.join(sorted((u.id,doctor_id)))+':'+v.patient_id).encode(),hashlib.sha256).hexdigest()[:16]
                    allowed.append({'shared_patient_ref':ref})
            return {'items':allowed}
    @app.post('/api/v1/care-team/visibility')
    def grant_visibility():
        body=request.get_json(silent=True) or {};a,b=body.get('doctor_a'),body.get('doctor_b')
        with SessionLocal.begin() as db:
            u=require_role(db,'patient')
            if not a or not b or a==b:return error(422,'INVALID_PAIR','Two doctors required')
            doctors=[db.get(User,doc) for doc in (a,b)]
            if not all(d and d.role=='doctor' and d.organization_id==u.organization_id for d in doctors): abort(403)
            if not all(db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.doctor_id==doc,DoctorPatientLink.patient_id==u.patient_id)) for doc in (a,b)):abort(403)
            vis=db.scalar(select(CareTeamVisibility).where(CareTeamVisibility.patient_id==u.patient_id,CareTeamVisibility.doctor_a==min(a,b),CareTeamVisibility.doctor_b==max(a,b)))
            if not vis: vis=CareTeamVisibility(id=uid(),patient_id=u.patient_id,doctor_a=min(a,b),doctor_b=max(a,b),active=0);db.add(vis)
            vis.active=1 if body.get('allow') is True else 0;audit(db,u,'care_team_visibility_changed','patient',u.patient_id)
            return {'active':bool(vis.active)}
    @app.get('/api/v1/research/synthetic-summary')
    def research_summary():
        from .legacy_research import legacy_aggregate
        with SessionLocal.begin() as db:
            result=legacy_aggregate(db,require_role(db,'researcher'),app.config['SECRET_KEY'])
            return {'dataset':'synthetic_demo_v1','cohorts':[{'label':r['cohort'],'n':r['observed_n'],
                'mean_checkin':r['mean']} for r in result['items'] if not r['suppressed']],
                'privacy':'Aggregate only; current study grant and shared disclosure safeguards'}
    @app.get('/api/v1/audit/me')
    def audit_events():
        with SessionLocal() as db:
            u=actor(db);return {'items':[obj(a) for a in db.scalars(select(Audit).where(Audit.actor==u.id).limit(100))]}
