"""03A actual HTTP/ORM with source-scoped exact synthetic fixtures, no inference."""
import json
from copy import deepcopy
from datetime import datetime, timezone
import pytest
from sqlalchemy import select, func
from cc_api import create_app, clinical_proposals as rules
from cc_api.clinical_proposal_fixtures import install, ROUTINE_TEXT, CRITICAL_TEXT, FIXTURES
from cc_api.extension_models import PrevisitCase
from cc_api.models import User, DoctorPatientLink
from cc_api.onboarding_models import PatientConsent
from test_phase02a import doctor, consent
from test_onboarding import issue, accept
from cc_api.onboarding_models import LocalIdentity

BASE='/api/v1/clinical-intelligence/patients/'
PID='pxp_history_02'
CID='phase03a_aviandr_visit'

def url(pid=PID,cid=CID):return BASE+pid+'/proposals?encounter_id='+cid

@pytest.fixture
def app(tmp_path):
    app=create_app(dict(TESTING=True,DEMO_MODE=True,APP_ENV='synthetic_dev',SEED_PATIENT_PERSONAS=True,
        SECRET_KEY='disposable-03a',CI_API_V1=True,CI_PROPOSALS_V1=True,CI_REVIEW_V1=True,
        CI_NLP_PROVIDER='mock',DB_PATH=str(tmp_path/'03a.sqlite')))
    install(app)
    yield app
    app.extensions['cc_session_factory'].kw['bind'].dispose()

def counts(app):
    with app.extensions['cc_session_factory']() as db:
        return {t.name:db.scalar(select(func.count()).select_from(t)) for t in User.metadata.sorted_tables}

def test_http_readonly_registry_links_and_unknown(app):
    client=doctor(app);before=counts(app)
    def no_nlp(*a):raise AssertionError('GET invoked NLP')
    app.extensions['ci_runtime'].provider_factory=no_nlp
    response=client.get(url());assert response.status_code==200,response.json
    dto=response.json
    assert response.headers['Cache-Control']=='no-store'
    assert len(dto['proposals'])==4 and len(dto['evidence'])==1
    assert dto['evidence'][0]['quote']==ROUTINE_TEXT
    assert dto['evidence'][0]['scope']=='symptoms'
    assert dto['alert_delivery']=='not_implemented' and not dto['referral_order_created']
    assert not dto['clinical_action_enabled']
    referral=dto['proposals'][0]
    assert (referral['category'],referral['urgency'],referral['critical'],referral['severity'])==('desired','planned',False,'not_assessed')
    for item in dto['proposals']:
        assert not item['rule_approved'] and item['label']==rules.LABEL and item['status']=='proposed_readonly'
        assert set(item['assessments'].values())=={'not_assessed'}
        assert item['rule']['source']['qualified_clinical_reviewer'] is None
        for link in item['catalog_links']:
            assert client.get('/api/v1/clinical-catalog/'+link['kind']+'/'+link['id']).status_code==200
    assert [len(x['catalog_links']) for x in dto['proposals']]==[0,1,1,1]
    assert client.get(url()).json==dto
    assert counts(app)==before and app.extensions['ci_runtime'].cache=={}

@pytest.mark.parametrize('uid',['doc_ther','doc_other','pat_02','clinic_01','researcher_01','platform_01'])
def test_acl(app,uid):
    client=doctor(app,uid);before=counts(app);response=client.get(url())
    assert response.status_code in (403,404)
    assert ROUTINE_TEXT not in response.text and 'proposals' not in (response.json or {})
    assert counts(app)==before

@pytest.mark.parametrize('change',['revoke','scope','expiry','case_doctor','tenant','missing_source','changed_source','grant_scope'])
def test_source_reauthorization_and_fail_closed(app,change):
    client=doctor(app);old=client.get(url()).json
    with app.extensions['cc_session_factory'].begin() as db:
        row=db.get(PrevisitCase,CID)
        if change=='revoke':consent(db).revoked_at='2020-01-01T00:00:00Z'
        elif change=='scope':consent(db).categories='medications'
        elif change=='expiry':row.allowed_until='2020-01-01T00:00:00Z'
        elif change=='case_doctor':row.doctor_id='doc_ther'
        elif change=='tenant':db.get(User,'doc_psy').organization_id='foreign_org'
        elif change=='missing_source':row.intake_json='{}'
        elif change=='changed_source':row.intake_json=json.dumps({'text':'Изменённый источник <script>alert(1)</script>'})
        else:
            for link in db.scalars(select(DoctorPatientLink).where(DoctorPatientLink.patient_id==PID)):
                link.categories='medications'
    before=counts(app);response=client.get(url())
    if change=='changed_source':
        assert response.status_code==200 and response.json['proposals']==[] and response.json['evidence']==[]
        stale=client.get(url()+'&source_version='+old['source_version']);assert stale.status_code==409
        assert ROUTINE_TEXT not in stale.text
    else:assert response.status_code in (404,422)
    assert ROUTINE_TEXT not in response.text and counts(app)==before

@pytest.mark.parametrize('setting,value',[('CI_PROPOSALS_V1',False),('CI_API_V1',False),('APP_ENV','production'),('DEMO_MODE',False)])
def test_experimental_never_outside_explicit_demo(app,setting,value):
    client=doctor(app);app.config[setting]=value
    response=client.get(url());assert response.status_code==404 and ROUTINE_TEXT not in response.text

@pytest.mark.parametrize('change',['expired','pending','approved','unknown_source','future','missing_provenance'])
def test_rule_policy_fail_closed(app,monkeypatch,change):
    registry=deepcopy(rules.REGISTRY)
    for rule in registry:
        if change=='expired':rule['expires_at']='2020-01-01T00:00:00+00:00'
        elif change in ('pending','approved'):rule['status']=change
        elif change=='unknown_source':rule['source']['source_id']='not-known'
        elif change=='future':rule['effective_at']='2099-01-01T00:00:00+00:00'
        else:rule['source']['provenance_uri']=None
    monkeypatch.setattr(rules,'REGISTRY',registry)
    dto=doctor(app).get(url()).json
    assert dto['proposals']==[] and dto['evidence']==[]

def test_axes_independent_and_separate_patient_branch(app,monkeypatch):
    # No category-to-urgency conversion in the model: mandatory+planned is legal data.
    client=doctor(app);r=client.get(url()).json['proposals'][0]
    registry=deepcopy(rules.REGISTRY)
    registry[0]['referral_category']='mandatory'
    registry[0]['version']='2-axes-test'
    monkeypatch.setattr(rules,'REGISTRY',registry)
    mandatory=client.get(url()).json['proposals'][0]
    assert mandatory['category']=='mandatory' and mandatory['urgency']=='planned' and not mandatory['critical']
    assert mandatory['id']!=r['id']
    # Separate case+patient permission required, not inherited from routine source.
    response=client.get(url('pat_a','phase03a_alternate_visit'))
    assert response.status_code==404  # no explicit accepted symptoms consent ledger in baseline pat_a
    assert CRITICAL_TEXT not in response.text
    assert FIXTURES[0][1:3]!=FIXTURES[1][1:3]
    patient=doctor(app,'pat_01')
    with app.extensions['cc_session_factory']() as db:email=db.get(LocalIdentity,'pat_01').email
    invitation=issue(client,email)
    assert accept(patient,invitation).status_code==200
    before=counts(app)
    critical=client.get(url('pat_a','phase03a_alternate_visit'))
    assert critical.status_code==200,critical.json
    item=critical.json['proposals'][0]
    assert item['critical'] and item['severity']=='critical' and item['category'] is None
    assert item['type']=='safety_illustration' and critical.json['alert_delivery']=='not_implemented'
    assert critical.json['evidence'][0]['quote']==CRITICAL_TEXT
    assert counts(app)==before
    with app.extensions['cc_session_factory'].begin() as db:
        db.scalar(select(PatientConsent).where(PatientConsent.patient_user_id=='pat_01',PatientConsent.doctor_id=='doc_psy')).revoked_at='2020-01-01T00:00:00Z'
    assert client.get(url('pat_a','phase03a_alternate_visit')).status_code==404
    assert client.get(url()).status_code==200

def test_source_override_and_method_rejected(app):
    client=doctor(app);before=counts(app)
    for suffix in ('&text=override','&encounter_id=other','&source_version=bad','&patient_ref=pat_a'):
        assert client.get(url()+suffix).status_code==422
    assert client.post(url(),json={}).status_code in (403,405)
    assert client.get(url(cid='nonexistent')).status_code==404
    assert app.test_client().get(url()).status_code in (401,403)
    assert counts(app)==before

def test_fixture_collision_and_production_guard(app):
    install(app)
    with app.extensions['cc_session_factory'].begin() as db:db.get(PrevisitCase,CID).intake_json='{}'
    with pytest.raises(ValueError):install(app)
    app.config['APP_ENV']='production'
    with pytest.raises(ValueError):install(app)

@pytest.mark.parametrize('change',['revoke','source','unchanged'])
def test_reauthorize_between_derivation_and_response(app,monkeypatch,change):
    derive=rules.derive
    def changed(selected,config):
        dto=derive(selected,config)
        with app.extensions['cc_session_factory'].begin() as db:
            if change=='revoke':consent(db).revoked_at='2020-01-01T00:00:00Z'
            elif change=='source':db.get(PrevisitCase,CID).intake_json=json.dumps({'text':'New source'})
        return dto
    monkeypatch.setattr(rules,'derive',changed)
    client=doctor(app);before=counts(app);response=client.get(url())
    assert response.status_code=={'revoke':404,'source':409,'unchanged':200}[change]
    if change!='unchanged':assert ROUTINE_TEXT not in response.text and 'proposals' not in (response.json or {})
    assert counts(app)==before

def test_actual_response_matches_openapi_schema(app):
    from pathlib import Path
    import yaml
    from jsonschema import Draft202012Validator
    spec=yaml.safe_load((Path(__file__).resolve().parents[1]/'contracts/openapi.yaml').read_text())
    schema={'$ref':'#/components/schemas/GovernedClinicalProposals','components':spec['components']}
    response=doctor(app).get(url());assert response.status_code==200
    Draft202012Validator(schema).validate(response.json)
