"""Own-physician review/history: no clinical decisions or independent document store."""
from collections import OrderedDict, deque
from threading import Lock
from time import monotonic
from flask import abort, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from .clinical_intelligence_review_models import CiSuggestionClaim
from .clinical_intelligence_sources import selected_source
from .clinical_intelligence_review_services import enabled,review_body,write_review,claim_payload,final_check,safe_storage_errors

BASE='/api/v1/clinical-intelligence'


def register_clinical_intelligence_review_routes(app,SessionLocal,current_user,require_role,error,utc_now):
    attempts=OrderedDict();mutex=Lock()
    def guard():
        if not enabled(app):abort(404)
    def limit(actor):
        now=monotonic()
        with mutex:
            for key in list(attempts):
                while attempts[key] and now-attempts[key][0]>=60:attempts[key].popleft()
                if not attempts[key]:attempts.pop(key)
            if actor not in attempts and len(attempts)>=256:abort(429)
            times=attempts.setdefault(actor,deque())
            if len(times)>=60:abort(429)
            times.append(now)

    @app.get(BASE+'/patients/<patient_id>/reviews')
    @safe_storage_errors
    def ci_reviews_get(patient_id):
        guard()
        if set(request.args)!={'encounter_id'} or len(request.args.getlist('encounter_id'))!=1:abort(422)
        case_id=request.args['encounter_id']
        if not case_id or len(case_id)>64:abort(422)
        with SessionLocal() as db:
            doctor=require_role(db,'doctor');source=selected_source(db,doctor,patient_id,case_id)
            claims=db.scalars(select(CiSuggestionClaim).where(CiSuggestionClaim.actor_id==doctor.id,
                CiSuggestionClaim.organization_id==doctor.organization_id,CiSuggestionClaim.patient_id==patient_id,
                CiSuggestionClaim.case_id==case_id,CiSuggestionClaim.source_version==source.source_version,
                CiSuggestionClaim.grant_version==source.grant_version).order_by(CiSuggestionClaim.created_at.desc()).limit(100)).all()
            from .clinical_intelligence_review_services import check_claim
            items=[]
            for claim in claims:
                current,provenance=check_claim(db,doctor,claim,allow_historical=True)
                items.append(claim_payload(db,claim,current,provenance))
            return {'items':items,'patient_ref':patient_id,'encounter_ref':case_id,'review_enabled':True}

    @app.post(BASE+'/suggestions/<suggestion_id>/reviews')
    @safe_storage_errors
    def ci_review_post(suggestion_id):
        guard()
        request.max_content_length=16385
        if request.content_length and request.content_length>16384:abort(413)
        if len(request.get_data(cache=True))>16384:abort(413)
        data=review_body(request.get_json(silent=True))
        # Test seam before the fresh locked transaction; no environment/HTTP bypass.
        hook=app.extensions.get('ci_review_before_write')
        if hook:hook()
        try:
            with SessionLocal() as db:
                doctor=require_role(db,'doctor');limit(doctor.id)
                claim=db.get(CiSuggestionClaim,suggestion_id)
                source,provenance,revision=write_review(db,doctor,claim,data)
                final_check(app,db,doctor,source,claim.id)
                payload=claim_payload(db,claim,source,provenance,until=revision)
                db.commit()
                return payload
        except IntegrityError:
            return error(409,'CI_REVIEW_CONFLICT','Оценка изменилась. Обновите данные.')
        except OperationalError:
            return error(503,'CI_REVIEW_UNAVAILABLE','Запись временно недоступна. Проверьте сохранение перед повтором.')
