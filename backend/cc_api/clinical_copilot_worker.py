"""One bounded background drain, durable jobs; cancelled/obsolete answers never commit."""
import json
import threading
import time
from datetime import datetime,timezone
from sqlalchemy import select,update
from werkzeug.exceptions import HTTPException
from .models import User
from .onboarding_models import LocalAuthSession
from .clinical_copilot_models import CopilotThread,CopilotMessage,CopilotJob
from .clinical_copilot_services import now,dump,audit,access,finish,enabled
from .clinical_workflow_services import uid
from . import copilot_provider,copilot_catalog
from .clinical_intelligence_sources import digest

class ChatRuntime:
    def __init__(self,app,sessions):
        self.app=app;self.sessions=sessions;self.lock=threading.Lock();self.active=False
        # A restarted process cannot safely resume an unknown in-flight model response.
        with sessions.begin() as db:
            db.execute(update(CopilotJob).where(CopilotJob.status=='running').values(status='failed',safe_error_code='worker_restarted',finished_at=now()))
        self.kick()

    def kick(self):
        with self.lock:
            if self.active:return
            with self.sessions() as db:
                if not db.scalar(select(CopilotJob.id).where(CopilotJob.status=='queued').limit(1)):return
            self.active=True
            threading.Thread(target=self.drain,daemon=True,name='cc-physician-chat').start()

    def cancelled(self,ident):
        with self.sessions() as db:
            row=db.get(CopilotJob,ident)
            thread=db.get(CopilotThread,row.thread_id) if row else None
            return not row or row.status not in ('queued','running') or not thread or thread.status!='open' or not enabled(self.app,'CI_CHAT_V1')

    def drain(self):
        try:
            while True:
                with self.sessions() as db:
                    ident=db.scalar(select(CopilotJob.id).where(CopilotJob.status=='queued').order_by(CopilotJob.queued_at).limit(1))
                if not ident:return
                self.run(ident)
        finally:
            with self.lock:self.active=False
            self.kick()

    def run(self,ident):
        started=time.monotonic();metrics={}
        try:
            with self.app.app_context():
                with self.sessions.begin() as db:
                    changed=db.execute(update(CopilotJob).where(CopilotJob.id==ident,CopilotJob.status=='queued').values(status='running',started_at=now()))
                    if changed.rowcount!=1:return
                with self.sessions() as db:
                    job=db.get(CopilotJob,ident);thread=db.get(CopilotThread,job.thread_id);actor=db.get(User,thread.actor_id)
                    thread,source=access(db,actor,CopilotThread,thread.id)
                    meta=json.loads(job.timings_json);session_id=meta.get('auth_session_hash')
                    auth=db.get(LocalAuthSession,session_id) if session_id else None
                    if not auth or auth.user_id!=actor.id or auth.revoked_at or auth.expires_at<=now():raise ValueError('context_unavailable')
                    prompt=db.get(CopilotMessage,job.input_id)
                    previous=db.scalars(select(CopilotMessage).where(CopilotMessage.thread_id==thread.id,CopilotMessage.ordinal<prompt.ordinal).order_by(CopilotMessage.ordinal)).all()
                    history=[dict(role=x.role,content=x.content) for x in previous[-8:]]
                    prior_refs=[]
                    for x in previous[-2:]:prior_refs+=json.loads(x.provenance_json).get('catalog_citations',[])
                    audience=thread.audience
                    refs=copilot_catalog.retrieve(prompt.content,source.text,prior_refs,audience=audience)
                    messages,budget=copilot_provider.build_context(source,history,prompt.content,refs)
                    if budget['estimated_token_upper_bound']+budget['response_token_budget']>budget['num_ctx']:raise ValueError('context_budget')
                    metrics.update(queue_ms=max(0,int((datetime.fromisoformat(job.started_at)-datetime.fromisoformat(job.queued_at)).total_seconds()*1000)),prompt_generation_ms=int((time.monotonic()-started)*1000))
                provider=self.app.extensions.get('copilot_provider',copilot_provider.generate)
                call_start=time.monotonic()
                answer,provenance=provider(self.app.config,messages,refs,source.text,cancelled=lambda:self.cancelled(ident))
                metrics['inference_wall_ms']=int((time.monotonic()-call_start)*1000)
                # Validate even injected/testing adapters; no model URL/tool/permission field accepted.
                if not isinstance(answer,dict) or set(answer)!={'answer','citation_ids','evidence_quotes'}:raise ValueError('invalid_model_response')
                if not isinstance(answer['answer'],str) or not 1<=len(answer['answer'])<=2400:raise ValueError('invalid_model_response')
                ids=answer['citation_ids'];quotes=answer['evidence_quotes']
                if not isinstance(ids,list) or not 1<=len(ids)<=3 or any(not isinstance(x,str) or x not in {r['citation_id'] for r in refs} for x in ids):raise ValueError('invalid_citation')
                if not isinstance(quotes,list) or len(quotes)>3 or any(not isinstance(q,str) or not q or source.text.count(q)!=1 for q in quotes):raise ValueError('invalid_evidence')
                if audience!='patient' and not copilot_catalog.answer_supported(answer['answer'],refs):raise ValueError('unsupported_medicine_or_action_claim')
                if not copilot_catalog.revalidate(refs):raise ValueError('catalog_changed')
                if audience=='patient':
                    chosen=[r for r in refs if r['citation_id'] in ids]
                    answer['answer']=copilot_catalog.patient_verified_response(chosen)
                    provenance={**provenance,'answer_policy':'verified_public_extracts_v1','model_prose_published':False}
                with self.sessions() as db:
                    job=db.get(CopilotJob,ident);thread=db.get(CopilotThread,job.thread_id);actor=db.get(User,thread.actor_id)
                    thread,current=access(db,actor,CopilotThread,thread.id,lock=True)
                    # job can have been cancelled or thread purged while inference ran.
                    db.refresh(job)
                    if job.status!='running' or thread.status!='open':return
                    auth=db.get(LocalAuthSession,session_id)
                    if not auth or auth.user_id!=actor.id or auth.revoked_at or auth.expires_at<=now():raise ValueError('context_unavailable')
                    if current.source_version!=source.source_version or current.grant_version!=source.grant_version:raise ValueError('context_changed')
                    if not enabled(self.app,'CI_CHAT_V1'):raise ValueError('context_unavailable')
                    if not copilot_catalog.revalidate(refs):raise ValueError('catalog_changed')
                    last=db.scalar(select(CopilotMessage.ordinal).where(CopilotMessage.thread_id==thread.id).order_by(CopilotMessage.ordinal.desc()).limit(1)) or 0
                    evidence=[dict(quote=q,start=source.text.index(q),end=source.text.index(q)+len(q),scope='patient_self' if audience=='patient' else 'symptoms',case_ref=source.case_id,source_version=source.source_version) for q in quotes]
                    metrics['wall_ms']=int((time.monotonic()-started)*1000)
                    manifest=dict(source_refs=[dict(case_ref=source.case_id,source_id=getattr(source,'source_id',source.case_id),source_type=getattr(source,'source_type','intake'),source_version=source.source_version,scope='patient_self' if audience=='patient' else 'symptoms')],
                        grant_version=source.grant_version,catalog_refs=[{k:v for k,v in r.items() if k in ('kind','catalog_id','catalog_version','fragment_id','text_digest','citation_id')} for r in refs],
                        **budget)
                    db.add(CopilotMessage(id=uid('cm_'),thread_id=thread.id,ordinal=last+1,role='assistant',content=answer['answer'],
                        provenance_json=dump(dict(**provenance,catalog_citations=[r for r in refs if r['citation_id'] in ids],evidence=evidence,context_manifest=manifest,timings=metrics)),created_at=now()))
                    thread.revision+=1;thread.updated_at=now();job.status='completed';job.finished_at=now();job.timings_json=dump(metrics)
                    audit(db,actor,audience+'_chat_completed',job.id);finish(self.app,db,actor,current,lambda:copilot_catalog.revalidate(refs) and enabled(self.app,'CI_CHAT_V1'))
        except Exception as exc:
            safe={'context_changed','context_unavailable','invalid_model_response','invalid_citation','invalid_evidence','catalog_changed','no_catalog_support','context_budget','mock_forbidden','cancelled','provider_unavailable','unsupported_medicine_or_action_claim'}
            code='local_timeout' if isinstance(exc,TimeoutError) else str(exc) if type(exc) is ValueError and str(exc) in safe else 'context_changed' if isinstance(exc,HTTPException) and exc.code==409 else 'context_unavailable' if isinstance(exc,HTTPException) else 'analysis_unavailable'
            # Never log exception, SQL parameters, prompt, response or clinical content.
            try:
                with self.sessions.begin() as db:
                    job=db.get(CopilotJob,ident)
                    if job and job.status=='running':
                        job.status='timeout' if code=='local_timeout' else 'failed';job.safe_error_code=code;job.finished_at=now()
                        job.timings_json=dump({**metrics,'wall_ms':int((time.monotonic()-started)*1000)})
            except Exception:pass
