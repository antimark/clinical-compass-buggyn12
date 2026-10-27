"""One canonical scoped read/start endpoint; no clinical database mutations."""
from flask import request,abort
from .extension_models import PrevisitCase
from .verification import workspace_enabled
from . import clinical_proposals
from .clinical_intelligence_sources import clinical_grant,selected_source,metadata_query,active_case,POLICY
from .clinical_intelligence_runtime import Runtime,empty_dto,compute
from .clinical_intelligence_review_services import enabled as review_enabled, persist_claims, source_locked, final_check, safe_storage_errors, provenance_current

BASE='/api/v1/clinical-intelligence'


def register_clinical_intelligence_routes(app,SessionLocal,current_user,require_role,error,utc_now):
    runtime=Runtime();app.extensions['ci_runtime']=runtime
    def enabled():
        return workspace_enabled(app.config) and app.config.get('CI_API_V1') is True
    def guard():
        if not enabled():abort(404)
    def source(patient_id,case_id):
        with SessionLocal() as db:
            doctor=require_role(db,'doctor')
            result=selected_source(db,doctor,patient_id,case_id)
            return doctor.id,result
    def query_case():
        if set(request.args)!={'encounter_id'} or len(request.args.getlist('encounter_id'))!=1:abort(422)
        ident=request.args.get('encounter_id')
        if not ident or len(ident)>64:abort(422)
        return ident

    @app.after_request
    def ci_headers(response):
        if request.path.startswith(BASE+'/'):response.headers['Cache-Control']='no-store'
        return response

    @app.get(BASE+'/capabilities')
    def ci_capabilities():
        return {'enabled':enabled(),'clinical_intelligence_api_v1':enabled(),
            'environment':app.config['APP_ENV'],'referrals_enabled':workspace_enabled(app.config) and app.config.get('CI_REFERRALS_V1') is True,'chat_enabled':workspace_enabled(app.config) and app.config.get('CI_CHAT_V1') is True,'proposals_enabled':clinical_proposals.enabled(app.config),'review_enabled':review_enabled(app),'source_policy_version':POLICY,'clinical_action_enabled':False,
            'ruleset_status':'unapproved','source_types':['intake'],'explicit_start_required':True}

    @app.get(BASE+'/patients/<patient_id>/sources')
    def ci_sources(patient_id):
        guard()
        if request.args:abort(422)
        with SessionLocal() as db:
            doctor=require_role(db,'doctor');person,_=clinical_grant(db,doctor,patient_id)
            # Metadata only; do not select any intake text or other patient source type.
            rows=db.execute(metadata_query(person,doctor).order_by(PrevisitCase.created_at.desc()).limit(50)).all()
            return {'patient_ref':patient_id,'items':[{'encounter_ref':row.id,'source_type':'intake','created_at':row.created_at}
                for row in rows if active_case(row)]}

    @app.get(BASE+'/patients/<patient_id>/proposals')
    @safe_storage_errors
    def ci_proposals_get(patient_id):
        if not clinical_proposals.enabled(app.config):abort(404)
        if not set(request.args).issubset({'encounter_id','source_version'}):abort(422)
        if any(len(request.args.getlist(k))!=1 for k in request.args):abort(422)
        case_id=request.args.get('encounter_id')
        if not case_id or len(case_id)>64:abort(422)
        expected=request.args.get('source_version')
        if expected is not None and (len(expected)!=64 or any(c not in '0123456789abcdef' for c in expected)):abort(422)
        actor,selected=source(patient_id,case_id)
        if expected is not None and expected!=selected.source_version:
            return error(409,'SOURCE_CHANGED','Источник изменился. Повторите выбор.')
        dto=clinical_proposals.derive(selected,app.config)
        # Reauthorize derived evidence immediately before serialization, without cached ORM state.
        actor_after,current=source(patient_id,case_id)
        if actor!=actor_after or current.source_version!=selected.source_version or current.grant_version!=selected.grant_version:
            return error(409,'SOURCE_CHANGED','Источник или разрешение изменились. Повторите выбор.')
        return dto

    @app.get(BASE+'/patients/<patient_id>/snapshot')
    def ci_snapshot_get(patient_id):
        guard();case_id=query_case();actor,selected=source(patient_id,case_id);key=(actor,patient_id,case_id)
        dto=runtime.read(key,selected)
        if dto=='stale':return error(409,'SOURCE_CHANGED','Источник или разрешение изменились. Повторите выбор.')
        if dto is not None:
            dto['review_enabled']=review_enabled(app)
            dto['permissions']['can_review']=review_enabled(app) and dto.get('claims_persisted') is True and provenance_current(dto)
            return dto
        with runtime.lock:pending=key in runtime.pending
        return empty_dto(selected,'pending' if pending else 'unavailable','generation_in_progress' if pending else 'not_started')

    @app.post(BASE+'/patients/<patient_id>/snapshot')
    @safe_storage_errors
    def ci_snapshot_start(patient_id):
        guard();case_id=query_case()
        # Read at most one byte beyond the accepted bound, including chunked WSGI streams.
        request.max_content_length=1025
        if request.content_length and request.content_length>1024:abort(413)
        if len(request.get_data(cache=True))>1024:abort(413)
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or set(data)!={'source_revision','source_version'}:abort(422)
        actor,selected=source(patient_id,case_id);key=(actor,patient_id,case_id)
        if type(data['source_revision']) is not int or not isinstance(data['source_version'],str):abort(422)
        if (data['source_revision'],data['source_version'])!=(selected.source_revision,selected.source_version):
            return error(409,'SOURCE_CHANGED','Источник изменился. Повторите выбор.')
        status=runtime.start(key)
        if status:return error(429,'CI_BUSY' if status=='busy' else 'CI_RATE_LIMIT','Анализ временно недоступен. Повторите позже.')
        try:
            try:dto=compute(selected,app.config,runtime)
            except Exception:
                # Never return exception/model/source text; still reauthorize before any response.
                dto=empty_dto(selected,'unavailable','analysis_unavailable')
                dto['error_code']='analysis_unavailable'
            # Fresh session: no stale pre-inference SQLAlchemy identity map/transaction.
            actor_after,current=source(patient_id,case_id)
            if actor_after!=actor:abort(404)
            if current.source_version!=selected.source_version or current.grant_version!=selected.grant_version:
                return error(409,'SOURCE_CHANGED','Источник или разрешение изменились. Повторите выбор.')
            if review_enabled(app):
                with SessionLocal() as db:
                    doctor=require_role(db,'doctor')
                    locked=source_locked(db,doctor,patient_id,case_id)
                    if locked.source_version!=selected.source_version or locked.grant_version!=selected.grant_version:abort(409)
                    persist_claims(db,doctor,locked,dto)
                    final_check(app,db,doctor,locked,next((t.get('suggestion_id') for t in dto['tags']),None))
                    db.commit()
            runtime.put(key,current,dto)
            return dto
        finally:runtime.finish(key)
