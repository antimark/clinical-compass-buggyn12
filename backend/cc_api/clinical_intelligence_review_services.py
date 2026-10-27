"""Durable claim binding and append-only review, protected by current source authority."""
import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID
from functools import wraps
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from flask import jsonify, current_app
from werkzeug.exceptions import HTTPException
from flask import abort
from sqlalchemy import select, update
from .models import User
from .onboarding_models import PatientConsent, PatientInvitation
from .extension_models import PrevisitCase, Audit
from .doctor_access import authorized_patient
from .clinical_intelligence_sources import selected_source, digest, POLICY
from .clinical_intelligence_review_models import CiSuggestionClaim, CiReview, CiReviewEvent, CiDraftTransfer
from .clinical_workflow_services import uid, text
from .verification import workspace_enabled

CORRECTNESS = {'supported','unsupported','needs_correction','unreviewed'}
RELEVANCE = {'relevant','low_priority','not_relevant','undecided'}
FIELDS = {'narrative','assessment','follow_up'}


def enabled(app):
    return workspace_enabled(app.config) and app.config.get('CI_API_V1') is True and app.config.get('CI_REVIEW_V1') is True


def stamp():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def dumps(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def quote_digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def receipt_key(value):
    if not isinstance(value,str) or len(value)>64:abort(422)
    try: UUID(value)
    except (ValueError,TypeError,AttributeError):abort(422)
    return digest(['ci-operation-v1',value])


def source_locked(db, doctor, patient_id, case_id):
    # Same consent -> link lock order as native saves and consent withdrawal.
    # SQL no-op updates acquire SQLite writer locks and real PostgreSQL row locks.
    person=authorized_patient(db,doctor,patient_id,'symptoms',lock=True)
    db.execute(update(PatientInvitation).where(PatientInvitation.patient_user_id==person.id,
        PatientInvitation.issuer_id==doctor.id).values(status=PatientInvitation.status))
    db.execute(update(PrevisitCase).where(PrevisitCase.id==case_id).values(status=PrevisitCase.status))
    db.execute(update(User).where(User.id.in_([doctor.id,person.id])).values(role=User.role))
    db.expire_all()
    if doctor.role!='doctor':abort(403)
    return selected_source(db,doctor,patient_id,case_id)


def final_check(app,db,doctor,source,suggestion_id=None):
    hook=app.extensions.get('ci_review_before_commit')
    if hook:hook(db)
    db.flush();db.expire_all()
    current=selected_source(db,doctor,source.patient_id,source.case_id)
    if current.source_version!=source.source_version or current.grant_version!=source.grant_version:abort(409)
    if suggestion_id:
        claim=db.get(CiSuggestionClaim,suggestion_id)
        if not claim or not provenance_current(json.loads(claim.provenance_json)):abort(409)


def provenance_current(provenance):
    # Metadata only: instantiating a provider never calls extract/network/Ollama.
    from .nlp_lab_routes_v3 import specs
    from cc_nlp import __version__
    try:
        provider=current_app.extensions['ci_runtime'].provider_factory(current_app.config)
        modes={'local_llm','deterministic_mock_fallback'} if provider.name=='local_llm' else {'deterministic_mock'}
        return (provenance['mode'] in modes and provenance['primary_model_version']==provider.model_id
            and provenance['catalog_version']==specs()[0]['catalog_version']
            and provenance['prompt_version']=='extract-v1' and provenance['schema_version']=='ci-v1'
            and provenance['nlp_version']==__version__ and provenance['source_policy_version']==POLICY)
    except Exception:return False


def check_claim(db,doctor,claim,*,lock=False,allow_historical=False):
    if not claim or claim.actor_id!=doctor.id or claim.organization_id!=doctor.organization_id:abort(404)
    source=(source_locked if lock else selected_source)(db,doctor,claim.patient_id,claim.case_id)
    if source.source_version!=claim.source_version or source.grant_version!=claim.grant_version:abort(409)
    provenance=json.loads(claim.provenance_json)
    for anchor in provenance['anchors']:
        start,end=anchor['start'],anchor['end']
        if type(start) is not int or type(end) is not int or not 0<=start<end<=len(source.text):abort(409)
        if quote_digest(source.text[start:end])!=anchor['digest']:abort(409)
    if not allow_historical and not provenance_current(provenance):abort(409)
    return source,provenance


def persist_claims(db,doctor,source,dto):
    if dto['analysis_status'] not in ('ready','needs_review'):return
    evidence={x['id']:x for x in dto['evidence']}
    for tag in dto['tags']:
        anchors=[]
        for ref in tag['evidence_refs']:
            ev=evidence[ref]
            if source.text[ev['start']:ev['end']]!=ev['quote']:abort(409)
            anchors.append({'start':ev['start'],'end':ev['end'],'digest':quote_digest(ev['quote'])})
        anchors=sorted([json.loads(x) for x in set(dumps(x) for x in anchors)],key=lambda x:(x['start'],x['end'],x['digest']))
        if not anchors:continue
        provenance={k:dto.get(k) for k in ('schema_version','catalog_version','model_version','primary_model_version',
            'prompt_version','nlp_version','mode','error_code','source_revision','source_policy_version')}
        provenance.update(tag={k:tag[k] for k in ('code','label','category','assertion','temporality')},
            anchors=anchors,source_type='intake',generated_at=dto['generated_at'])
        identity={k:v for k,v in provenance.items() if k!='generated_at'}
        ident='cis_'+digest([doctor.id,doctor.organization_id,source.patient_id,source.case_id,
            source.source_version,source.grant_version,identity])[:56]
        if not db.get(CiSuggestionClaim,ident):
            db.add(CiSuggestionClaim(id=ident,actor_id=doctor.id,organization_id=doctor.organization_id,
                patient_id=source.patient_id,case_id=source.case_id,source_version=source.source_version,
                grant_version=source.grant_version,provenance_json=dumps(provenance),created_at=stamp()))
            db.flush()
            db.add(CiReview(suggestion_id=ident,revision=0,state_json='{}',updated_at=stamp()))
        tag['suggestion_id']=ident
    dto['review_enabled']=True
    dto['claims_persisted']=bool(dto['tags'])
    dto['permissions']['can_review']=bool(dto['tags'])
    # Clinical action permissions intentionally remain false: review is not a diagnosis/order.


def state_status(correctness):
    return {'supported':'confirmed','unsupported':'rejected','needs_correction':'corrected','unreviewed':'pending'}[correctness]


def claim_payload(db,claim,source,provenance,*,until=None):
    events=db.scalars(select(CiReviewEvent).where(CiReviewEvent.suggestion_id==claim.id)
        .order_by(CiReviewEvent.revision)).all()
    history=[json.loads(e.state_json) for e in events if until is None or e.revision<=until]
    state=history[-1] if history else None
    current=provenance_current(provenance)
    return dict(suggestion_id=claim.id,patient_ref=claim.patient_id,encounter_ref=claim.case_id,
        source_version=claim.source_version,grant_version=claim.grant_version,
        source_revision=provenance['source_revision'],source_policy_version=POLICY,
        tag=provenance['tag'],evidence=[{'start':a['start'],'end':a['end'],
            'quote':source.text[a['start']:a['end']]} for a in provenance['anchors']],
        model_version=provenance['model_version'],mode=provenance['mode'],
        schema_version=provenance['schema_version'],catalog_version=provenance['catalog_version'],
        stale=not current,can_review=current,
        can_transfer=current and bool(state and state['correctness'] in ('supported','needs_correction')),
        review=state,history=history,created_at=claim.created_at)


def review_body(data):
    fields={'review_revision','source_version','correctness','relevance','correction','note','idempotency_key'}
    if not isinstance(data,dict) or set(data)!=fields:abort(422)
    if type(data['review_revision']) is not int or data['review_revision']<0:abort(422)
    if not isinstance(data['source_version'],str) or len(data['source_version'])!=64:abort(422)
    if not isinstance(data['correctness'],str) or data['correctness'] not in CORRECTNESS:abort(422)
    if not isinstance(data['relevance'],str) or data['relevance'] not in RELEVANCE:abort(422)
    correction=text(data['correction'],2000);note=text(data['note'],2000)
    if data['correctness']=='needs_correction' and not correction:abort(422)
    if data['correctness']!='needs_correction' and correction:abort(422)
    receipt_key(data['idempotency_key'])
    return {**data,'correction':correction,'note':note}


def write_review(db,doctor,claim,data):
    source,provenance=check_claim(db,doctor,claim,lock=True)
    if data['source_version']!=claim.source_version:abort(409)
    key=receipt_key(data['idempotency_key']);request_digest=digest([claim.id,data])
    old=db.scalar(select(CiReviewEvent).where(CiReviewEvent.actor_id==doctor.id,CiReviewEvent.key_hash==key))
    if old:
        if old.request_digest!=request_digest:abort(409)
        return source,provenance,old.revision
    current=db.scalar(select(CiReview).where(CiReview.suggestion_id==claim.id).with_for_update())
    if not current or current.revision!=data['review_revision']:abort(409)
    rev=current.revision+1;now=stamp()
    state={k:data[k] for k in ('correctness','relevance','correction','note')}
    state.update(revision=rev,status=state_status(data['correctness']),created_at=now)
    prior=digest(json.loads(current.state_json))
    changed=db.execute(update(CiReview).where(CiReview.suggestion_id==claim.id,CiReview.revision==data['review_revision'])
        .values(revision=rev,state_json=dumps(state),updated_at=now))
    if changed.rowcount!=1:abort(409)
    db.add(CiReviewEvent(id=uid('cire_'),suggestion_id=claim.id,actor_id=doctor.id,revision=rev,
        key_hash=key,request_digest=request_digest,prior_digest=prior,state_json=dumps(state),created_at=now))
    db.add(Audit(id=uid('cia_'),actor=doctor.id,action='ci_review_recorded',object_type='ci_suggestion',object_id=claim.id,created_at=now))
    db.flush()
    return source,provenance,rev


def prepare_transfer(db,doctor,document,data):
    transfer=data.get('ci_transfer')
    fields={'suggestion_id','review_revision','source_version','target_field','text','idempotency_key'}
    if not isinstance(transfer,dict) or set(transfer)!=fields:abort(422)
    if not isinstance(transfer['suggestion_id'],str) or len(transfer['suggestion_id'])>64:abort(422)
    if type(transfer['review_revision']) is not int or transfer['review_revision']<1:abort(422)
    if not isinstance(transfer['source_version'],str):abort(422)
    if not isinstance(transfer['target_field'],str) or transfer['target_field'] not in FIELDS:abort(422)
    edited=text(transfer['text'],2000,required=True)
    claim=db.get(CiSuggestionClaim,transfer['suggestion_id'])
    source,_=check_claim(db,doctor,claim,lock=True)
    if claim.patient_id!=document.patient_id:abort(404)
    if transfer['source_version']!=claim.source_version:abort(409)
    key=receipt_key(transfer['idempotency_key']);request_digest=digest([document.id,data])
    old=db.scalar(select(CiDraftTransfer).where(CiDraftTransfer.actor_id==doctor.id,CiDraftTransfer.key_hash==key))
    if old:
        if old.request_digest!=request_digest:abort(409)
        # Historical receipt is immutable. Return current native document for honest read-back;
        # replay never inserts again, even if review/document was subsequently changed/signed.
        return source,old,None
    review=db.scalar(select(CiReview).where(CiReview.suggestion_id==claim.id).with_for_update())
    if not review or review.revision!=transfer['review_revision']:abort(409)
    state=json.loads(review.state_json)
    if state['correctness'] not in ('supported','needs_correction'):abort(422)
    if document.kind!='encounter' or document.status!='draft':abort(409)
    if data['revision']!=document.revision:abort(409)
    original=json.loads(document.content_json)
    if data['content']!=original or data['mode']!=document.mode:abort(409)
    merged=dict(original);field=transfer['target_field']
    merged[field]=(original.get(field,'')+'\n\n' if original.get(field,'') else '')+edited
    receipt=CiDraftTransfer(id=uid('cit_'),suggestion_id=claim.id,actor_id=doctor.id,
        review_revision=review.revision,document_id=document.id,document_revision=document.revision+1,
        target_field=field,text_digest=quote_digest(edited),key_hash=key,request_digest=request_digest,created_at=stamp())
    return source,receipt,merged


def transfer_payload(receipt):
    return dict(id=receipt.id,suggestion_id=receipt.suggestion_id,review_revision=receipt.review_revision,
        document_id=receipt.document_id,document_revision=receipt.document_revision,
        target_field=receipt.target_field,status='native_draft_saved')


def safe_storage_errors(function):
    """Never log SQL statements/parameters from a failed protected write."""
    @wraps(function)
    def call(*args,**kwargs):
        try:return function(*args,**kwargs)
        except HTTPException as exc:
            if exc.code not in (409,410,413,422,429):raise
            return jsonify(error={'code':'CI_REQUEST_REJECTED',
                'message':'Проверьте актуальность источника, версию и поля запроса.'}),exc.code
        except SQLAlchemyError as exc:
            status=409 if isinstance(exc,IntegrityError) else 503
            return jsonify(error={'code':'CI_STORAGE_CONFLICT' if status==409 else 'CI_STORAGE_UNAVAILABLE',
                'message':'Сохранение не подтверждено. Проверьте состояние перед повтором.'}),status
    return call
