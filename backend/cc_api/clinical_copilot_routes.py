"""Explicit confirmed physician decisions and private asynchronous chat endpoints."""
import hashlib
import json
from datetime import datetime,timedelta,timezone
from flask import request,abort,session
from sqlalchemy import select,update,func,delete
from .clinical_copilot_models import Referral,ReferralEvent,CopilotThread,CopilotMessage,CopilotJob
from .clinical_copilot_services import (BASE,enabled,now,dump,expected,receipt,save_receipt,finish,access,
    referral_dto,thread_dto,job_dto,audit,chat_source)
from .clinical_intelligence_sources import selected_source
from .clinical_intelligence_review_services import source_locked,safe_storage_errors
from .clinical_workflow_services import uid,text
from .clinical_copilot_worker import ChatRuntime
from .clinical_proposals import derive


def register_clinical_copilot_routes(app,SessionLocal,current_user,require_role,error,utc_now):
    runtime=ChatRuntime(app,SessionLocal);app.extensions['copilot_runtime']=runtime
    def gate(flag):
        if not enabled(app,flag):abort(404)
    def body(required,optional=()):
        request.max_content_length=20000
        if request.content_length and request.content_length>20000:abort(413)
        raw=request.get_data(cache=True)
        if len(raw)>20000:abort(413)
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or not set(required)<=set(data) or set(data)-set(required)-set(optional):abort(422)
        return data
    def case_query():
        if set(request.args)!={'encounter_id'} or len(request.args.getlist('encounter_id'))!=1:abort(422)
        return text(request.args['encounter_id'],64,required=True)
    def revision(data):
        if type(data.get('revision')) is not int or data['revision']<1:abort(422)
    def confirmed(data):
        if data.get('confirmed') is not True:abort(422)
    def actor(db):return require_role(db,'doctor')

    @app.get(BASE+'/patients/<patient_id>/referrals')
    @safe_storage_errors
    def list_manual_referrals(patient_id):
        gate('CI_REFERRALS_V1');cid=case_query()
        with SessionLocal() as db:
            doctor=actor(db);source=selected_source(db,doctor,patient_id,cid)
            rows=db.scalars(select(Referral).where(Referral.actor_id==doctor.id,Referral.tenant_id==doctor.organization_id,
                Referral.patient_id==patient_id,Referral.case_id==cid).order_by(Referral.created_at.desc()).limit(100)).all()
            return dict(items=[referral_dto(db,r) for r in rows],source_version=source.source_version,grant_version=source.grant_version)

    @app.post(BASE+'/patients/<patient_id>/referrals')
    @safe_storage_errors
    def create_manual_referral(patient_id):
        gate('CI_REFERRALS_V1');cid=case_query()
        data=body(('source_version','grant_version','authority','confirmed','decision','target_specialty','category','urgency','clinical_reason','idempotency_key'),('proposal_id',))
        confirmed(data)
        if data['authority']!='manual_physician' or data['decision'] not in ('create','decline'):abort(422)
        if data['target_specialty'] not in ('psychiatrist','psychotherapist','general_practice','neurologist') or data['category'] not in ('mandatory','desired') or data['urgency'] not in ('emergency','urgent','planned'):abort(422)
        reason=text(data['clinical_reason'],4000,required=True)
        proposal_id=data.get('proposal_id')
        if proposal_id is not None and (not isinstance(proposal_id,str) or len(proposal_id)!=64):abort(422)
        with SessionLocal() as db:
            doctor=actor(db);source=source_locked(db,doctor,patient_id,cid);expected(source,data)
            key,fingerprint,prior=receipt(db,doctor,data,['referral',patient_id,cid])
            if prior:return prior,200
            if proposal_id and proposal_id not in {p['id'] for p in derive(source,app.config)['proposals'] if p['type']=='referral'}:abort(409)
            stamp=now();ident=uid('rf_')
            content=dict(target_specialty=data['target_specialty'],category=data['category'],urgency=data['urgency'],clinical_reason=reason,
                proposal_id=proposal_id,proposal_authority='context_only' if proposal_id else 'none',rule_approved=False,
                severity='not_assessed',critical=False)
            from .clinical_intelligence_sources import digest
            row=Referral(id=ident,actor_id=doctor.id,tenant_id=doctor.organization_id,patient_id=patient_id,case_id=cid,
                source_version=source.source_version,grant_version=source.grant_version,revision=1,
                status='created' if data['decision']=='create' else 'declined',content_json=dump(content),
                confirmation_hash=digest([ident,doctor.id,doctor.organization_id,source.source_version,source.grant_version,stamp,content]),created_at=stamp,updated_at=stamp)
            db.add(row);db.flush()
            db.add(ReferralEvent(id=uid('re_'),referral_id=ident,revision=1,actor_id=doctor.id,action=row.status,reason=reason,created_at=stamp))
            audit(db,doctor,'manual_referral_'+row.status,ident);db.flush();dto=referral_dto(db,row)
            save_receipt(db,doctor,key,fingerprint,dto);finish(app,db,doctor,source)
            return dto,201

    @app.get(BASE+'/referrals/<ident>')
    @safe_storage_errors
    def read_manual_referral(ident):
        gate('CI_REFERRALS_V1')
        with SessionLocal() as db:
            row,source=access(db,actor(db),Referral,ident,strict=False)
            return referral_dto(db,row)

    @app.post(BASE+'/referrals/<ident>/decisions')
    @safe_storage_errors
    def cancel_manual_referral(ident):
        gate('CI_REFERRALS_V1')
        data=body(('revision','source_version','grant_version','idempotency_key','confirmed','action','reason'));confirmed(data);revision(data)
        if data['action']!='cancel':abort(422)
        reason=text(data['reason'],4000,required=True)
        with SessionLocal() as db:
            doctor=actor(db);row,source=access(db,doctor,Referral,ident,lock=True,strict=False);expected(source,data)
            key,fingerprint,prior=receipt(db,doctor,data,['referral-cancel',ident])
            if prior:return prior
            stamp=now()
            changed=db.execute(update(Referral).where(Referral.id==ident,Referral.revision==data['revision'],Referral.status=='created').values(status='cancelled',revision=data['revision']+1,updated_at=stamp))
            if changed.rowcount!=1:abort(409)
            db.add(ReferralEvent(id=uid('re_'),referral_id=ident,revision=data['revision']+1,actor_id=doctor.id,action='cancelled',reason=reason,created_at=stamp))
            audit(db,doctor,'manual_referral_cancelled',ident);db.flush();db.refresh(row);dto=referral_dto(db,row)
            save_receipt(db,doctor,key,fingerprint,dto);finish(app,db,doctor,source);return dto

    def chat_actor(db):
        user=current_user(db)
        if not user:abort(401)
        if user.role not in ('doctor','patient'):abort(403)
        return user
    def chat_query():
        if set(request.args)-{'encounter_id','source_type'} or not request.args.get('encounter_id'):abort(422)
        if any(len(request.args.getlist(k))!=1 for k in request.args):abort(422)
        return text(request.args['encounter_id'],64,required=True),request.args.get('source_type','intake')

    @app.get(BASE+'/patients/<patient_id>/threads')
    @safe_storage_errors
    def list_doctor_threads(patient_id):
        gate('CI_CHAT_V1');cid,kind=chat_query()
        with SessionLocal() as db:
            doctor=chat_actor(db);source=chat_source(db,doctor,patient_id,cid,kind)
            rows=db.scalars(select(CopilotThread).where(CopilotThread.actor_id==doctor.id,CopilotThread.tenant_id==doctor.organization_id,
                CopilotThread.patient_id==patient_id,CopilotThread.audience==doctor.role,CopilotThread.source_type==kind,CopilotThread.source_id==cid,CopilotThread.source_version==source.source_version,
                CopilotThread.grant_version==source.grant_version,CopilotThread.status=='open').order_by(CopilotThread.created_at.desc()).limit(20))
            return dict(items=[thread_dto(db,r,source,False) for r in rows],source_version=source.source_version,grant_version=source.grant_version)

    @app.post(BASE+'/patients/<patient_id>/threads')
    @safe_storage_errors
    def create_doctor_thread(patient_id):
        gate('CI_CHAT_V1')
        if request.args:abort(422)
        data=body(('encounter_id','source_version','grant_version','idempotency_key'),('source_type',));cid=text(data['encounter_id'],64,required=True)
        with SessionLocal() as db:
            doctor=chat_actor(db);kind=data.get('source_type','intake');source=chat_source(db,doctor,patient_id,cid,kind,True);expected(source,data)
            key,fingerprint,prior=receipt(db,doctor,data,['create-thread',patient_id,cid])
            if prior:
                old,_=access(db,doctor,CopilotThread,prior['id'])
                if old.status!='open':abort(410)
                return thread_dto(db,old,source),200
            stamp=now();row=CopilotThread(id=uid('ct_'),actor_id=doctor.id,tenant_id=doctor.organization_id,
                patient_id=patient_id,case_id=source.case_id,audience=doctor.role,source_type=kind,source_id=cid,source_version=source.source_version,grant_version=source.grant_version,
                revision=1,status='open',retention_state='retained_private',created_at=stamp,updated_at=stamp)
            db.add(row);db.flush();dto=thread_dto(db,row,source);save_receipt(db,doctor,key,fingerprint,{'id':row.id})
            audit(db,doctor,doctor.role+'_chat_thread_created',row.id);finish(app,db,doctor,source);return dto,201

    @app.get(BASE+'/threads/<ident>')
    @safe_storage_errors
    def read_doctor_thread(ident):
        gate('CI_CHAT_V1')
        with SessionLocal() as db:
            row,source=access(db,chat_actor(db),CopilotThread,ident)
            if row.status!='open':abort(410)
            return thread_dto(db,row,source)

    @app.delete(BASE+'/threads/<ident>')
    @safe_storage_errors
    def close_doctor_thread(ident):
        gate('CI_CHAT_V1');data=body(('revision','confirmed'));revision(data);confirmed(data)
        with SessionLocal() as db:
            doctor=chat_actor(db);row,source=access(db,doctor,CopilotThread,ident,lock=True)
            if row.status=='closed':return {'id':ident,'status':'closed','retention_state':'purged'}
            changed=db.execute(update(CopilotThread).where(CopilotThread.id==ident,CopilotThread.revision==data['revision'],CopilotThread.status=='open').values(status='closed',retention_state='purged',revision=data['revision']+1,updated_at=now()))
            if changed.rowcount!=1:abort(409)
            # Keep audit/job identity and ordinal receipts; erase sensitive content/manifests.
            db.execute(update(CopilotMessage).where(CopilotMessage.thread_id==ident).values(content='',provenance_json='{}'))
            db.execute(update(CopilotJob).where(CopilotJob.thread_id==ident,CopilotJob.status.in_(('queued','running'))).values(status='cancelled',safe_error_code='cancelled',finished_at=now(),timings_json='{}'))
            audit(db,doctor,doctor.role+'_chat_purged',ident);finish(app,db,doctor,source)
            return {'id':ident,'status':'closed','retention_state':'purged'}

    @app.post(BASE+'/threads/<ident>/messages')
    @safe_storage_errors
    def send_doctor_message(ident):
        gate('CI_CHAT_V1');data=body(('revision','source_version','grant_version','content','idempotency_key'));revision(data)
        question=text(data['content'],2000,required=True)
        with SessionLocal() as db:
            doctor=chat_actor(db);row,source=access(db,doctor,CopilotThread,ident,lock=True);expected(source,data)
            if row.status!='open':abort(410)
            key,fingerprint,prior=receipt(db,doctor,data,['chat-message',ident])
            if prior:return prior,202
            if row.revision!=data['revision']:abort(409)
            pending=db.scalar(select(func.count()).select_from(CopilotJob).where(CopilotJob.thread_id==ident,CopilotJob.status.in_(('queued','running'))))
            if pending:abort(409)
            queued=db.scalar(select(func.count()).select_from(CopilotJob).where(CopilotJob.status.in_(('queued','running'))))
            minute=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
            recent=db.scalar(select(func.count()).select_from(CopilotJob).join(CopilotThread).where(CopilotThread.actor_id==doctor.id,CopilotJob.queued_at>minute))
            if queued>=8 or recent>=8:abort(429)
            count=db.scalar(select(func.count()).select_from(CopilotMessage).where(CopilotMessage.thread_id==ident))
            if count>=40:abort(429)
            changed=db.execute(update(CopilotThread).where(CopilotThread.id==ident,CopilotThread.revision==data['revision']).values(revision=data['revision']+1,updated_at=now()))
            if changed.rowcount!=1:abort(409)
            from .safety_rules import urgent_notice
            notice=urgent_notice(question) if doctor.role=='patient' else None
            message=CopilotMessage(id=uid('cm_'),thread_id=ident,ordinal=count+1,role='user',content=question,provenance_json=dump({'urgent_notice':notice}) if notice else '{}',created_at=now())
            db.add(message);db.flush()
            session_token=session.get('auth_session')
            token_hash=hashlib.sha256(session_token.encode()).hexdigest() if isinstance(session_token,str) else None
            job=CopilotJob(id=uid('cj_'),thread_id=ident,input_id=message.id,status='queued',safe_error_code='',queued_at=now(),started_at='',finished_at='',timings_json=dump({'auth_session_hash':token_hash}))
            db.add(job);db.flush();dto=job_dto(job)
            if doctor.role=='patient':dto['urgent_notice']=notice
            save_receipt(db,doctor,key,fingerprint,dto)
            audit(db,doctor,doctor.role+'_chat_turn_requested',job.id);finish(app,db,doctor,source)
        runtime.kick();return dto,202

    def job_access(db,ident,lock=False):
        doctor=chat_actor(db)
        job=db.scalar(select(CopilotJob).join(CopilotThread).where(CopilotJob.id==ident,CopilotThread.actor_id==doctor.id,CopilotThread.tenant_id==doctor.organization_id,CopilotThread.audience==doctor.role))
        if not job:abort(404)
        row,source=access(db,doctor,CopilotThread,job.thread_id,lock=lock)
        if row.status!='open':abort(410)
        return doctor,row,source,job

    @app.get(BASE+'/jobs/<ident>')
    @safe_storage_errors
    def read_doctor_job(ident):
        gate('CI_CHAT_V1')
        with SessionLocal() as db:
            _,_,_,job=job_access(db,ident);return job_dto(job)

    @app.post(BASE+'/jobs/<ident>/cancel')
    @safe_storage_errors
    def cancel_doctor_job(ident):
        gate('CI_CHAT_V1');data=body(('confirmed',));confirmed(data)
        with SessionLocal() as db:
            doctor,row,source,job=job_access(db,ident,True);db.refresh(job)
            if job.status in ('queued','running'):
                job.status='cancelled';job.safe_error_code='cancelled';job.finished_at=now();audit(db,doctor,doctor.role+'_chat_cancelled',ident)
            dto=job_dto(job);finish(app,db,doctor,source);return dto

    @app.get(BASE+'/patient-chat/sources')
    @safe_storage_errors
    def patient_chat_sources():
        gate('CI_CHAT_V1')
        from .extension_models import PrevisitCase
        from .clinical_intelligence_sources import active_case
        from .clinical_copilot_models import PatientDiary
        with SessionLocal() as db:
            user=require_role(db,'patient');items=[]
            cases=db.execute(select(PrevisitCase.id,PrevisitCase.status,PrevisitCase.allowed_until,PrevisitCase.consent_version,PrevisitCase.created_at).where(PrevisitCase.patient_user_id==user.id).order_by(PrevisitCase.created_at.desc())).all()
            diaries=db.execute(select(PatientDiary.id,PatientDiary.revision,PatientDiary.created_at).where(PatientDiary.actor_id==user.id,PatientDiary.tenant_id==user.organization_id).order_by(PatientDiary.created_at.desc())).all()
            for kind,rows in [('intake',[r for r in cases if active_case(r)]),('diary',diaries)]:
                for row in rows[:50]:
                    source=chat_source(db,user,user.patient_id,row.id,kind)
                    items.append(dict(source_type=kind,source_id=row.id,encounter_id=row.id,source_version=source.source_version,grant_version=source.grant_version,
                        title=('Собственное обращение' if kind=='intake' else 'Личный дневник')+' · '+row.created_at[:10],revision=getattr(row,'revision',1)))
            return dict(patient_ref=user.patient_id,items=items,clinical_review_status='experimental_needs_validation')

    @app.post(BASE+'/patient-chat/notice')
    @safe_storage_errors
    def patient_chat_notice():
        gate('CI_CHAT_V1');data=body(('content',))
        with SessionLocal() as db:require_role(db,'patient')
        from .safety_rules import urgent_notice
        return dict(urgent_notice=urgent_notice(text(data['content'],2000,required=True)))

    @app.post(BASE+'/patient-chat/diary')
    @safe_storage_errors
    def patient_chat_diary():
        gate('CI_CHAT_V1');data=body(('content','confirmed'));confirmed(data)
        content=text(data['content'],4000,required=True)
        from .clinical_copilot_models import PatientDiary
        with SessionLocal() as db:
            user=require_role(db,'patient');stamp=now()
            row=PatientDiary(id=uid('pd_'),actor_id=user.id,tenant_id=user.organization_id,content=content,revision=1,created_at=stamp,updated_at=stamp)
            db.add(row);db.flush();source=chat_source(db,user,user.patient_id,row.id,'diary',True)
            audit(db,user,'patient_private_diary_created',row.id);finish(app,db,user,source)
            return dict(id=row.id,source_id=row.id,source_type='diary',revision=1,source_version=source.source_version,grant_version=source.grant_version),201

    @app.delete(BASE+'/patient-chat/diary/<ident>')
    @safe_storage_errors
    def patient_chat_diary_delete(ident):
        gate('CI_CHAT_V1');data=body(('revision','confirmed'));revision(data);confirmed(data)
        from .clinical_copilot_models import PatientDiary
        from .models import User
        with SessionLocal() as db:
            user=require_role(db,'patient');source=chat_source(db,user,user.patient_id,ident,'diary',True)
            row=db.get(PatientDiary,ident)
            if row.revision!=data['revision']:abort(409)
            threads=list(db.scalars(select(CopilotThread.id).where(CopilotThread.actor_id==user.id,CopilotThread.audience=='patient',CopilotThread.source_type=='diary',CopilotThread.source_id==ident)))
            if threads:
                db.execute(update(CopilotMessage).where(CopilotMessage.thread_id.in_(threads)).values(content='',provenance_json='{}'))
                db.execute(update(CopilotJob).where(CopilotJob.thread_id.in_(threads),CopilotJob.status.in_(('queued','running'))).values(status='cancelled',safe_error_code='cancelled',finished_at=now(),timings_json='{}'))
                db.execute(update(CopilotThread).where(CopilotThread.id.in_(threads)).values(status='closed',retention_state='purged'))
            db.delete(row);audit(db,user,'patient_private_diary_purged',ident);db.commit()
            return dict(id=ident,status='deleted',retention_state='purged')
