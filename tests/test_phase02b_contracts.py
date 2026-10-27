"""Cross-layer DTO and immutable-claim identity contracts; no Ollama inference."""
import copy
import json
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator
from sqlalchemy import select
from test_phase02b import app,extract,reviews,payload,save,counts
from test_phase02a import PID,CID,doctor
from cc_api.clinical_intelligence_sources import selected_source
from cc_api.clinical_intelligence_review_services import persist_claims
from cc_api.clinical_intelligence_review_models import CiSuggestionClaim
from cc_api.models import User


def test_real_snapshot_review_and_history_match_openapi(app):
    spec=yaml.safe_load((Path(__file__).resolve().parents[1]/'contracts/openapi.yaml').read_text())
    def check(name,value):
        Draft202012Validator({'$ref':'#/components/schemas/'+name,'components':spec['components']}).validate(value)
    client,snapshot,sid=extract(app)
    check('ScopedCISnapshot',snapshot)
    check('CiReviewInput',payload(snapshot))
    assert snapshot['claims_persisted'] is True and snapshot['permissions']['can_review'] is True
    response=save(client,sid,payload(snapshot));assert response.status_code==200
    check('CiDurableReview',response.json)
    for item in reviews(client).json['items']:check('CiDurableReview',item)
    app.config['CI_REVIEW_V1']=False
    cached=client.get('/api/v1/clinical-intelligence/patients/'+PID+'/snapshot?encounter_id='+CID).json
    assert cached['permissions']['can_review'] is False and cached['review_enabled'] is False


def test_claim_identity_independent_of_ram_ids_array_order_and_generation_time(app):
    client,snapshot,sid=extract(app)
    before=counts(app)
    dto=copy.deepcopy(snapshot)
    dto['generated_at']='2099-01-01T00:00:00Z'
    dto['tags'].reverse();dto['evidence'].reverse()
    for index,ev in enumerate(dto['evidence']):
        old=ev['id'];new='different-ephemeral-'+str(index);ev['id']=new
        for tag in dto['tags']:tag['evidence_refs']=[new if ref==old else ref for ref in tag['evidence_refs']][::-1]
    for tag in dto['tags']:tag['id']='untrusted-client-id-not-used-by-server-identity'
    with app.extensions['cc_session_factory'].begin() as db:
        actor=db.get(User,'doc_psy');source=selected_source(db,actor,PID,CID)
        persist_claims(db,actor,source,dto)
    assert {t['suggestion_id'] for t in dto['tags']}=={t['suggestion_id'] for t in snapshot['tags']}
    assert counts(app)==before


def test_tampered_persisted_anchor_fails_closed_without_quote_or_review_write(app):
    client,snapshot,sid=extract(app)
    with app.extensions['cc_session_factory'].begin() as db:
        claim=db.get(CiSuggestionClaim,sid);data=json.loads(claim.provenance_json)
        data['anchors'][0]['digest']='0'*64;claim.provenance_json=json.dumps(data)
    before=counts(app)
    denied=save(client,sid,payload(snapshot));assert denied.status_code==409
    assert 'evidence' not in denied.json and counts(app)==before
    listed=reviews(client);assert listed.status_code==409 and 'evidence' not in listed.json


def test_superseded_model_claim_archived_but_not_actionable(app):
    from cc_nlp.providers.mock import DeterministicMockProvider
    from test_phase02b import native,transfer
    client,snapshot,sid=extract(app)
    first=save(client,sid,payload(snapshot));assert first.status_code==200
    doc=native(client)
    class NewModel(DeterministicMockProvider):model_id='revised-fixture-model-version'
    app.extensions['ci_runtime'].provider_factory=lambda config:NewModel()
    cached=client.get('/api/v1/clinical-intelligence/patients/'+PID+'/snapshot?encounter_id='+CID).json
    assert cached['permissions']['can_review'] is False
    item=next(x for x in reviews(client).json['items'] if x['suggestion_id']==sid)
    assert item['stale'] is True and item['can_review'] is False and item['can_transfer'] is False
    assert item['review']==first.json['review']
    before=counts(app)
    assert save(client,sid,{**payload(snapshot),'review_revision':1}).status_code==409
    assert transfer(client,doc,sid,snapshot).status_code==409
    assert counts(app)==before


def test_model_superseded_immediately_before_commit_rolls_back_review(app):
    from cc_nlp.providers.mock import DeterministicMockProvider
    client,snapshot,sid=extract(app);before=counts(app)
    class NewModel(DeterministicMockProvider):model_id='changed-before-commit'
    def replace_model(db):app.extensions['ci_runtime'].provider_factory=lambda config:NewModel()
    app.extensions['ci_review_before_commit']=replace_model
    assert save(client,sid,payload(snapshot)).status_code==409
    assert counts(app)==before


def test_native_body_bound_preserves_large_valid_existing_documents(app):
    from test_phase02b import native,CW
    from test_onboarding import mutate
    client,snapshot,sid=extract(app);doc=native(client)
    # Valid legacy content can exceed64KiB on the wire, including escaped Unicode.
    content={**doc['content'],'narrative':'я'*12000,'assessment':'я'*6000,'follow_up':'я'*2000}
    body={'revision':doc['revision'],'mode':doc['mode'],'content':content}
    saved=mutate(client,'PUT',CW+'/documents/'+doc['id'],body)
    assert saved.status_code==200 and saved.json['content']['narrative']==content['narrative']
    token=client.get('/api/v1/onboarding/bootstrap').json['csrf_token']
    oversized=client.put(CW+'/documents/'+doc['id'],data=b'x'*2097153,content_type='application/json',headers={'X-CSRF-Token':token})
    assert oversized.status_code==413
