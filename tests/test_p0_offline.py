"""Endpoint-function ACL/DB unit checks without Flask transport.

A fake Flask request/decorator is used because Flask is not installed in the
artifact environment. This is NOT a substitute for Flask CSRF/E2E testing.
"""
import importlib
import json
import sys
import types
from pathlib import Path
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
import pytest

ROOT = Path(__file__).resolve().parents[1]

class Denied(Exception):
    def __init__(self, code):self.code=code

class FakeApp:
    config={'SECRET_KEY':'synthetic-test-key','DEMO_MODE':True}
    def __init__(self):self.handlers={}
    def get(self,path):return self._decorate('GET',path)
    def post(self,path):return self._decorate('POST',path)
    def _decorate(self,method,path):
        def wrap(fn):self.handlers[method,path]=fn;return fn
        return wrap

@pytest.fixture
def api(monkeypatch):
    pkg=types.ModuleType('cc_api');pkg.__path__=[str(ROOT/'backend/cc_api')]
    fake=types.ModuleType('flask')
    fake.request=types.SimpleNamespace(args={},get_json=lambda silent=False:{})
    fake.abort=lambda code:(_ for _ in ()).throw(Denied(code))
    monkeypatch.setitem(sys.modules,'cc_api',pkg)
    monkeypatch.setitem(sys.modules,'flask',fake)
    from cc_api.models import Base,User,Patient,DoctorPatientLink
    from cc_api.extension_models import ResearchObservation
    from cc_api.p0_models import CarePlan,PlanItem
    # Current legacy adapters depend on additive stores too. Create the full
    # real model graph; this remains an endpoint-function unit harness.
    for path in sorted((ROOT/'backend/cc_api').glob('*_models.py')):
        importlib.import_module('cc_api.'+path.stem)
    routes=importlib.import_module('cc_api.p0_routes')
    # pytest imports other Flask-backed test modules during collection. If
    # p0_routes was already imported then simply shadowing sys.modules['flask']
    # does not replace the request LocalProxy cached in the module globals.
    # Bind the fake request/abort explicitly for this offline-only unit test.
    monkeypatch.setattr(routes,'request',fake.request)
    monkeypatch.setattr(routes,'abort',fake.abort)
    # The shared ACL module can also be cached from real Flask collection.
    # Preserve this harness's exact Denied(404) transport for that dependency.
    access=importlib.import_module('cc_api.doctor_access')
    monkeypatch.setattr(access,'abort',fake.abort)
    for module_name in ('clinical_workflow_services','released_plan_access','clinical_review_services','admin_booking_routes'):
        module=importlib.import_module('cc_api.'+module_name)
        if hasattr(module,'abort'):monkeypatch.setattr(module,'abort',fake.abort)
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    SessionLocal=sessionmaker(engine,expire_on_commit=False)
    with SessionLocal.begin() as db:
        db.add_all([
          User(id='doc',display_name='Doc',role='doctor',organization_id='one'),
          User(id='doc2',display_name='Different doc',role='doctor',organization_id='two'),
          User(id='pat',display_name='Patient',role='patient',organization_id='one',patient_id='p1'),
          User(id='pat2',display_name='Patient2',role='patient',organization_id='two',patient_id='p2'),
          User(id='admin',display_name='Admin',role='clinic_admin',organization_id='one'),
          User(id='research',display_name='Research',role='researcher',organization_id='one'),
          Patient(id='p1',display_name='Sensitive Name',diagnosis_label='SENSITIVE',medication_label='SECRET',severity_label='secret',trend='stable'),
          Patient(id='p2',display_name='Other Name',diagnosis_label='OTHER',medication_label='OTHER',severity_label='other',trend='stable'),
          DoctorPatientLink(doctor_id='doc',patient_id='p1',categories='symptoms,medications,diagnosis'),
        ])
        for cohort,count in [('A',7),('B',3)]:
            for i in range(count):
                db.add(ResearchObservation(id=f'{cohort}{i}',study_id='study_demo_v1',study_subject=f'{cohort}{i}',cohort=cohort,
                    measure='synthetic_mood',value=i+1,source='synthetic',recorded_at='2026-10-17T00:00:00Z'))
    from cc_api.research_workflow_service import provision_grant
    with SessionLocal.begin() as db:
        provision_grant(db,db.get(User,'research'))
    actor={'uid':'doc'}
    def current_user(db):return db.get(User,actor['uid'])
    def require_role(db,role):
        user=current_user(db)
        if user.role!=role:raise Denied(403)
        return user
    def error(code,reason,message):return {'error':{'code':reason,'message':message}},code
    app=FakeApp()
    routes.register_p0_routes(app,SessionLocal,current_user,require_role,error,lambda:'2026-10-18T00:00:00Z')
    def invoke(method,path,payload=None,args=None,**kwargs):
        fake.request.args=args or {}
        fake.request.get_json=lambda silent=False:payload or {}
        return app.handlers[method,path](**kwargs)
    yield types.SimpleNamespace(call=invoke,actor=actor,db=SessionLocal,models=(CarePlan,PlanItem))
    engine.dispose()
    for name in list(sys.modules):
        if name=='cc_api' or name.startswith('cc_api.'):
            sys.modules.pop(name,None)


def test_patient_cannot_create_plan_and_cross_tenant_doctor_blocked(api):
    route='/api/v1/p0/care-plans'
    data={'patient_id':'p1','items':[{'item_type':'behavioral','title':'Synthetic diary task'}]}
    api.actor['uid']='pat'
    with pytest.raises(Denied) as exc:api.call('POST',route,data)
    assert exc.value.code==403
    api.actor['uid']='doc2'
    with pytest.raises(Denied) as exc:api.call('POST',route,data)
    assert exc.value.code==404
    api.actor['uid']='doc'
    result,status=api.call('POST',route,data)
    assert status==201 and result['status']=='draft' and result['publication_required'] is True
    from cc_api.clinical_workflow_models import ClinicalDocument
    from cc_api.p0_models import CarePlan,PlanItem,UserNotification
    with api.db() as db:
        document=db.get(ClinicalDocument,result['id'])
        assert document.status=='draft' and document.signed_at is None and document.published_at is None
        assert 'Synthetic diary task' in document.content_json
        assert db.get(CarePlan,result['id']) is None
        assert list(db.scalars(select(PlanItem)))==[]
        assert list(db.scalars(select(UserNotification)))==[]
    api.actor['uid']='pat'
    assert api.call('GET',route)['items']==[]  # Explicit signing/publication is exercised with real Flask.
    api.actor['uid']='pat2'
    assert api.call('GET',route)['items']==[]  # Other patient sees no plan


def test_clinic_minimization_and_forbidden_to_patient(api):
    api.actor['uid']='admin'
    patients=api.call('GET','/api/v1/p0/clinic/patients')['items']
    assert len(patients)==1
    assert set(patients[0])=={'patient_ref','fields','contact_visible','clinical_record_access'}
    assert patients[0]['fields']=={} and patients[0]['contact_visible'] is False
    assert patients[0]['clinical_record_access'] is False
    detail=api.call('GET','/api/v1/p0/clinic/patients/<patient_ref>',patient_ref=patients[0]['patient_ref'])
    assert 'diagnosis' not in json.dumps(detail) and 'Sensitive Name' not in json.dumps(detail)
    assert detail['clinical_record_access'] is False
    api.actor['uid']='pat'
    with pytest.raises(Denied) as exc:api.call('GET','/api/v1/p0/clinic/patients')
    assert exc.value.code==403


def test_dataset_version_persisted_small_group_suppressed(api):
    api.actor['uid']='research'
    form={'study_id':'study_demo_v1','measure':'synthetic_mood','cohorts':['A','B']}
    saved,status=api.call('POST','/api/v1/p0/dataset-definitions',form)
    assert status==201
    result=api.call('GET','/api/v1/p0/dataset-definitions/<definition_id>/compute',definition_id=saved['id'])
    a,b=result['items']
    assert a['cohort']=='A' and a['n']==7 and a['suppressed'] is False
    assert b['cohort']=='B' and b['mean'] is None and b['suppressed'] is True
    api.actor['uid']='admin'
    with pytest.raises(Denied) as exc:api.call('GET','/api/v1/p0/dataset-definitions')
    assert exc.value.code==403


def test_adverse_event_patient_submission_and_scoped_assessment(api):
    api.actor['uid']='pat'
    result,status=api.call('POST','/api/v1/p0/adverse-events',{'description':'Synthetic headache reported'})
    assert status==201 and result['causality']=='not_assessed'
    api.actor['uid']='doc2'
    with pytest.raises(Denied) as exc:api.call('POST','/api/v1/p0/adverse-events/<eid>/review',
               {'status':'assessed','review_text':'Uncertain link'},eid=result['id'])
    assert exc.value.code==404
    api.actor['uid']='doc'
    reviewed=api.call('POST','/api/v1/p0/adverse-events/<eid>/review',
                {'status':'assessed','review_text':'Synthetic report, no conclusion'},eid=result['id'])
    assert reviewed['status']=='assessed'
