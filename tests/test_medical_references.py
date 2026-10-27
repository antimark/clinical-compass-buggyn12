"""Imported real reference integrity and clinician-only, explicit assistance gates.

Structural extension fixtures are technical placeholders, not medical facts.
"""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
import pytest
from sqlalchemy import select,text
from sqlalchemy.exc import IntegrityError
from cc_api import create_app
from cc_api.models import User
from test_onboarding import actor,mutate
from test_clinical_workflow import participants,create,transition,CW

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'backend/cc_api/data/medications'
REF='/api/v1/references'
MANIFEST=json.loads((ASSETS/'manifest.json').read_text())
PROVENANCE=json.loads((ASSETS/'provenance.json').read_text())

@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev','SEED_PATIENT_PERSONAS':True,
        'SECRET_KEY':'phase4-reference-tests','DB_PATH':str(tmp_path/'references.sqlite')})

def read(client,path):
    result=client.get(REF+path)
    assert result.status_code==200,(path,result.json)
    return result.json

def medication(client):
    return read(client,'/medications')['items'][0]

def pointer(value,path):
    assert path.startswith('/')
    for component in path[1:].split('/'):
        component=component.replace('~1','/').replace('~0','~')
        value=value[int(component)] if isinstance(value,list) else value[component]
    return value


@pytest.mark.parametrize('entry',MANIFEST['records'],ids=lambda entry:entry['filename'])
def test_all_eight_exact_source_hash_raw_export_sections_and_provenance(app,entry):
    doctor=actor(app)
    filename=PROVENANCE['filename_aliases'].get(entry['filename'],entry['filename'])
    raw=(ASSETS/filename).read_bytes()
    fingerprint=hashlib.sha256(raw).hexdigest()
    assert fingerprint==entry['sha256']
    reference_id=Path(filename).stem
    detail=read(doctor,'/medications/'+reference_id)
    assert detail['id']==reference_id and detail['version']=='sha256_'+fingerprint
    assert detail['review_status']=='imported_unreviewed'
    assert detail['provenance']['sha256']==fingerprint
    assert detail['provenance']['schema_version']==json.loads(raw)['schema_version']
    assert detail['provenance']['source_filename'] in (filename,entry['filename'])
    sections={section['key']:section['value'] for section in detail['sections']}
    original=json.loads(raw)
    for key,value in original.items():
        if key in ('schema_version','record_type','language'):continue
        assert key in sections and sections[key]==value,(reference_id,key)
    exported=doctor.get(REF+'/medications/'+reference_id+'/raw?version='+detail['version'])
    assert exported.status_code==200
    assert exported.data==raw and json.loads(exported.data)==original
    assert fingerprint in list(exported.headers.values()),'Raw export must expose full import fingerprint'
    # Original archive is optional in clean checkouts; exact approved hashes above
    # remain mandatory. If handed-off source is present, verify byte equivalence too.
    archive=ROOT/'.handoff/inputs'/PROVENANCE['source_archive']
    if archive.exists():
        assert hashlib.sha256(archive.read_bytes()).hexdigest()==PROVENANCE['source_archive_sha256']
        with ZipFile(archive) as zipped:
            candidates=[name for name in zipped.namelist() if Path(name).name==filename]
            assert len(candidates)==1
            assert zipped.read(candidates[0])==raw


def test_catalogue_manifest_alias_and_heterogeneous_fields_without_invented_metadata(app):
    assert MANIFEST['record_count']==8 and len(MANIFEST['records'])==8
    assert PROVENANCE['filename_aliases']=={'aviandr_maritupirdine_instruction(2).json':'aviandr_maritupirdine_instruction.json'}
    doctor=actor(app)
    items=read(doctor,'/medications')['items']
    assert len(items)==8 and len({item['id'] for item in items})==8
    atom=read(doctor,'/medications/atomoxetine_canon_40mg')
    avi=read(doctor,'/medications/aviandr_maritupirdine_instruction')
    def product(detail):return next(s['value'] for s in detail['sections'] if s['key']=='product')
    assert 'strength_per_capsule' in product(atom) and 'strength_per_tablet' not in product(atom)
    assert 'strength_per_tablet' in product(avi) and 'strength_per_capsule' not in product(avi)
    assert product(atom)['country_of_registration']=='Россия'
    assert read(doctor,'/medications?q=атомоксетин')['items'][0]['id']=='atomoxetine_canon_40mg'
    assert read(doctor,'/medications?q=no-such-reference')['items']==[]
    assert doctor.get(REF+'/medications?q='+'x'*101).status_code==422
    assert doctor.get(REF+'/medications/unknown').status_code==404
    assert doctor.get(REF+'/medications/'+items[0]['id']+'?version=wrong').status_code==404


def test_matching_exact_source_pointers_and_never_creates_orders(app):
    from cc_api.clinical_workflow_models import MedicationOrder
    doctor=actor(app)
    version=doctor.get(CW+'/icd10?q=F32').json['version']
    with app.extensions['cc_session_factory']() as db:before=len(db.scalars(select(MedicationOrder)).all())
    matches=read(doctor,'/matches?code=F32&version='+version)
    assert matches['label']=='Справочное совпадение (демо)'
    assert matches['items'] and 'Не является медицинской рекомендацией' in matches['limitation']
    for item in matches['items']:
        reference,rule=item['reference'],item['rule']
        assert rule['code']=='F32' and rule['version']=='1' and rule['curation_status']=='synthetic_demo'
        assert rule['source_field_paths'] and rule['match_basis'] and rule['display_limitation']
        raw=doctor.get(REF+'/medications/'+reference['id']+'/raw?version='+reference['version']).json
        resolved=[pointer(raw,path) for path in rule['source_field_paths']]
        assert 'F32' in resolved
        assert any('/icd10_codes/' in path for path in rule['source_field_paths'])
        assert any(path.endswith('/diagnosis_or_condition') for path in rule['source_field_paths'])
        assert rule['match_basis'] in resolved
    for code in ('F3','F32.1','F90.0','F99','UNSUPPORTED'):
        assert read(doctor,'/matches?code='+code+'&version='+version)['items']==[]
    assert doctor.get(REF+'/matches?code=F32&version=wrong').status_code==422
    with app.extensions['cc_session_factory']() as db:assert len(db.scalars(select(MedicationOrder)).all())==before


@pytest.mark.parametrize('identity',['pat_01','clinic_01','researcher_01','platform_01'])
def test_matches_and_therapy_are_doctor_only(app,identity):
    client=actor(app,identity)
    assert client.get(REF+'/matches?code=F32&version=anything').status_code==403
    assert client.get(REF+'/therapies').status_code==403
    assert client.get(REF+'/therapies/cbt_demo_v1').status_code==403
    if identity=='pat_01':assert len(read(client,'/medications')['items'])==8
    else:assert client.get(REF+'/medications').status_code==403


def test_reference_assistance_requires_explicit_pinned_physician_order(app):
    from cc_api.clinical_workflow_models import MedicationOrder
    patient,doctor,pid=participants(app)
    reference=medication(doctor)
    # Other opt-in personas have explicitly authored fixture orders. This
    # patient's reference browsing must not create an order for this patient.
    with app.extensions['cc_session_factory']() as db:
        assert list(db.scalars(select(MedicationOrder).where(MedicationOrder.patient_id==pid)))==[]
    draft=create(doctor,pid,'treatment',{'items':[{'item_type':'medication','title':reference['title'],
        'reference_id':reference['id'],'reference_version':reference['version']}]})
    order=draft['orders'][0]
    assert order['reference_id']==reference['id'] and order['reference_version']==reference['version']
    assert not {'dose','frequency','duration','route'}&order['regimen'].keys(),'Instruction dosage must never silently become an order'
    for version in ('wrong',''):
        response=mutate(doctor,'POST',CW+'/patients/'+pid+'/documents',{'kind':'treatment','mode':'quick','content':{
            'items':[{'item_type':'medication','title':'Synthetic invalid pinned reference','reference_id':reference['id'],'reference_version':version}]}})
        assert response.status_code==422,response.json
    signed=transition(doctor,draft,'sign').json
    published=transition(doctor,signed,'publish')
    assert published.status_code==200,published.json
    own=patient.get(CW+'/patients/'+pid+'/medication-orders').json['items'][0]
    assert own['reference_version']==reference['version']
    assert patient.get(REF+'/medications/'+reference['id']+'?version='+own['reference_version']).status_code==200
    restarted=create_app(dict(app.config))
    assert medication(actor(restarted))['version']==reference['version']


def test_database_composite_fk_rejects_unknown_reference_version(app):
    from cc_api.clinical_workflow_models import MedicationOrder
    _,doctor,pid=participants(app)
    doc=create(doctor,pid,'treatment',{'items':[{'item_type':'medication','title':'Synthetic manual entry'}]})
    with app.extensions['cc_session_factory']() as db:
        order=db.get(MedicationOrder,doc['orders'][0]['id'])
        order.reference_id='not-imported'
        order.reference_version='sha256_'+'0'*64
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()


def test_cbt_is_structured_illustrative_and_unreviewed(app):
    doctor=actor(app)
    items=read(doctor,'/therapies')['items']
    assert any(item['id']=='cbt_demo_v1' for item in items)
    detail=read(doctor,'/therapies/cbt_demo_v1')
    assert detail['version']=='1' and detail['review_status']=='illustrative_unreviewed'
    serialized=json.dumps(detail,ensure_ascii=False).lower()
    assert 'кпт' in serialized or 'когнитивно' in serialized
    assert 'иллюстратив' in serialized and ('не ' in serialized or 'не является' in serialized)
    assert isinstance(detail.get('content'),dict) or isinstance(detail.get('sections'),list)


@pytest.mark.parametrize('environment',['development','production'])
def test_references_are_explicit_profile_only(app,environment):
    disabled=create_app({**dict(app.config),'APP_ENV':environment,'SEED_PATIENT_PERSONAS':False})
    client=disabled.test_client()
    assert client.get('/api/v1/onboarding/bootstrap').json['enabled'] is False
    assert read(disabled.test_client(),'/capabilities')['enabled'] is False
    for path in ('/medications','/matches?code=F32&version=anything','/therapies'):
        assert client.get(REF+path).status_code==403
    assert app.test_client().get(REF+'/medications').status_code==401


def test_original_adherence_report_projects_without_dual_write_and_revocation_hides_it(app):
    from cc_api.clinical_workflow_models import MedicationAdherence
    from cc_api.p0_models import PlanEvent
    patient,doctor,pid=participants(app)
    draft=create(doctor,pid,'treatment',{'items':[{'item_type':'medication','title':'Synthetic compatibility adherence'}]})
    signed=transition(doctor,draft,'sign').json
    published=transition(doctor,signed,'publish')
    assert published.status_code==200,published.json
    oid=published.json['orders'][0]['id']
    report=mutate(patient,'POST','/api/v1/p0/plan-items/'+oid+'/report',{'outcome':'partial'})
    assert report.status_code==201,report.json
    viewed=doctor.get(CW+'/patients/'+pid+'/medication-orders')
    assert viewed.status_code==200,viewed.json
    order=next(item for item in viewed.json['items'] if item['id']==oid)
    projected=[r for r in order['reports'] if r['id']==report.json['id']]
    assert len(projected)==1 and projected[0]['outcome']=='partial' and projected[0]['source']=='legacy_plan_report'
    with app.extensions['cc_session_factory']() as db:
        assert len(db.scalars(select(PlanEvent).where(PlanEvent.item_id==oid)).all())==1
        assert list(db.scalars(select(MedicationAdherence).where(MedicationAdherence.order_id==oid)))==[]
    assert mutate(patient,'DELETE','/api/v1/patients/me/clinical-links/doc_psy',{}).status_code==200
    assert doctor.get(CW+'/patients/'+pid+'/medication-orders').status_code==404
    assert patient.get(CW+'/patients/'+pid+'/medication-orders').json['items']==[]


def test_future_optional_nested_fields_preserved_in_typed_sections():
    from cc_api.medical_references import typed_sections
    structural={'product':{'name':'SYNTHETIC STRUCTURE ONLY'},'optional_future_metadata':{
        'jurisdictions':[{'jurisdiction':'TEST_ONLY','registration_date':'2000-01-01','documents':[
            {'title':'Synthetic schema link','url':'https://example.invalid/structure'}]}],
        'evidence_fields':{'reviewed':False,'record_count':0,'nested':{'future_key':'Technical placeholder'}},
        'absent_optional':None}}
    sections=typed_sections(structural)
    assert {section['key']:section['value'] for section in sections}==structural
    assert all(section['title'] and section['type'] for section in sections)


def test_actual_javascript_renderer_escapes_nested_future_structure_and_unsafe_urls():
    """Current catalog projection + actual designer renderer; simulated HTTP is unit-only."""
    import shutil,subprocess
    from cc_api.clinical_catalog_v3 import _safe_sections
    raw={'future_optional':{'jurisdictions':[{'jurisdiction':'TEST_ONLY','registration_date':'2000-01-01',
        'evidence':{'reviewed':False,'count':0},'trial_links':['https://example.invalid/test','javascript:alert(1)']}],
        'unsafe_text':'<img src=x onerror=alert(1)>','null_field':None,'empty_field':[],
        'nested':{'next_version':'SYNTHETIC STRUCTURE ONLY'}}}
    item={'kind':'medicine','id':'test_only','title':'Synthetic renderer object',
        'reference_sections':_safe_sections(raw,('future_optional',)),'links':[]}
    script=r'''import {strict as assert} from 'node:assert';
import {catalogDetail} from './frontend/dist/assets/js/views.js';
let input='';for await(const chunk of process.stdin)input+=chunk;
const item=JSON.parse(input);globalThis.location={hash:'',search:''};
globalThis.fetch=async()=>new Response(JSON.stringify(item),{headers:{'content-type':'application/json'}});
const html=await catalogDetail('medicine','test_only');
for(const value of ['TEST_ONLY','2000-01-01','SYNTHETIC STRUCTURE ONLY','https://example.invalid/test'])assert.ok(html.includes(value));
assert.ok(!html.includes('href="javascript:')&&!html.includes('<img'));
assert.ok(html.includes('&lt;img')&&html.includes('javascript:alert(1)'));
assert.ok(!html.includes('null field')&&!html.includes('empty field'));
assert.ok(html.includes('да')||html.includes('нет'));
assert.ok(html.includes('count: 0'));
process.stdout.write('Actual designer renderer: nested structure, false/zero, safe URL and escaped text passed\n');
'''
    node=shutil.which('node')
    assert node,'Existing Node runtime required; use cc-m1 PATH'
    result=subprocess.run([node,'--input-type=module','-e',script],cwd=ROOT,input=json.dumps(item),text=True,capture_output=True)
    assert result.returncode==0,result.stdout+result.stderr

