"""Phase01A managed dataset safety and real multi-role D01 persistence."""
import json
import shutil
import pytest
from sqlalchemy import select, text
from cc_api import create_app
from cc_api.models import User, DoctorPatientLink
from cc_api.extension_models import PrevisitCase, Audit, Message, Appointment
from cc_api import synthetic_dataset as ds
from auth_support import login_response

OB = '/api/v1/onboarding'


def mutate(client, method, path, data):
    token = client.get(OB + '/bootstrap').json['csrf_token']
    return client.open(path, method=method, json=data, headers={'X-CSRF-Token': token})


@pytest.fixture
def managed(monkeypatch):
    monkeypatch.setenv('CC_APP_ENV', 'synthetic_dev')
    monkeypatch.setenv('CC_DEMO_MODE', '1')
    monkeypatch.delenv('CC_DATABASE_URL', raising=False)
    monkeypatch.delenv('CC_DB_PATH', raising=False)
    ident = ds.create_dataset()
    yield ident
    shutil.rmtree(ds.ROOT / (ds.PREFIX + ident))


def test_seed_repeat_reset_graph(managed):
    first = ds.operate(managed)
    assert first == ds.operate(managed)
    assert ds.operate(managed, reset=True)['rows'] == first['rows']
    app = ds.open_app(ds.folder(managed))
    with app.extensions['cc_session_factory']() as db:
        assert not db.execute(text('PRAGMA foreign_key_check')).all()
        assert db.get(User, 'doc_gp').specialty == 'general_practice'
        from pathlib import Path
        from cc_api.models import Patient, Alert
        from cc_api.patient_experience_models import DemoQuestionnaireSubmission, MetricObservation
        manifest = json.loads((Path(__file__).resolve().parents[1] / 'demo_completion/fixtures/DEMO_DATA_MANIFEST.json').read_text())
        for group, model in [('staff', User), ('patients', Patient), ('cases', PrevisitCase), ('appointments', Appointment), ('signals', Alert)]:
            for entity in manifest['entities'][group]:
                assert db.get(model, entity['id']) is not None
        for ident in manifest['phase01a']['references']['observations']:
            assert db.get(MetricObservation, ident).patient_id == 'pxp_history_02'
        assert db.get(DemoQuestionnaireSubmission, 'ds_fixture_history_02') is not None

        for case in db.scalars(select(PrevisitCase)):
            assert db.get(User, case.patient_user_id).role == 'patient'
            assert db.get(User, case.doctor_id).role == 'doctor'
        for appt in db.scalars(select(Appointment)):
            case = db.get(PrevisitCase, appt.case_id)
            assert (appt.patient_user_id, appt.doctor_id) == (case.patient_user_id, case.doctor_id)
        for msg in db.scalars(select(Message).where(Message.thread_type == 'previsit')):
            case = db.get(PrevisitCase, msg.context_id)
            assert {msg.sender_id, msg.recipient_id} == {case.patient_user_id, case.doctor_id}
    app.extensions['cc_session_factory'].kw['bind'].dispose()


@pytest.mark.parametrize('variable,value', [('CC_APP_ENV','production'), ('CC_APP_ENV','development'),
    ('CC_DEMO_MODE','0'), ('CC_DATABASE_URL','sqlite:////tmp/arbitrary.sqlite'), ('CC_DB_PATH','/tmp/arbitrary.sqlite')])
def test_forbidden_operations(monkeypatch, variable, value):
    monkeypatch.setenv('CC_APP_ENV', 'synthetic_dev'); monkeypatch.setenv('CC_DEMO_MODE', '1')
    monkeypatch.setenv(variable, value)
    for operation in (lambda: ds.create_dataset(), lambda: ds.operate('abcdefgh'), lambda: ds.operate('abcdefgh', True)):
        with pytest.raises(ValueError): operation()


def test_reset_refuses_nonowned_rows(managed):
    app = ds.open_app(ds.folder(managed)); session = app.extensions['cc_session_factory']
    with session.begin() as db:
        db.add(User(id='foreign', display_name='Синтетический посторонний', role='patient', organization_id='org_demo'))
    session.kw['bind'].dispose()
    with pytest.raises(ValueError, match='non-owned'): ds.operate(managed, True)
    app = ds.open_app(ds.folder(managed))
    with app.extensions['cc_session_factory']() as db:
        assert db.get(User, 'foreign') and db.get(User, 'doc_psy')
    app.extensions['cc_session_factory'].kw['bind'].dispose()


def test_reset_refuses_changed_rows_and_symlinks(managed):
    path = ds.folder(managed); app = ds.open_app(path); session = app.extensions['cc_session_factory']
    with session.begin() as db: db.get(User, 'pat_03').display_name = 'Изменено пользователем'
    session.kw['bind'].dispose()
    with pytest.raises(ValueError, match='changed'): ds.operate(managed, True)
    ledger = path / 'ownership.json'; saved = path / 'saved.json'; ledger.rename(saved); ledger.symlink_to(saved)
    with pytest.raises(ValueError, match='Symlink'): ds.operate(managed, True)


@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING':True, 'DEMO_MODE':True, 'APP_ENV':'synthetic_dev',
        'SECRET_KEY':'phase01a-tests', 'DB_PATH':str(tmp_path/'d01.sqlite')})


def test_d01_http_persistence_csrf_acl(app):
    patient = app.test_client()
    payload = {'display_name':'Новый синтетический D01', 'email':'phase01a@demo.test',
               'password':'Synthetic-D01-test-pass-42','terms_consent':True}
    assert patient.post(OB+'/register', json=payload).status_code == 403
    registered = mutate(patient, 'POST', OB+'/register', payload)
    assert registered.status_code == 201
    uid = registered.json['user']['id']
    assert mutate(patient, 'PUT', OB+'/state', {'introduction_seen':True,'status':'completed'}).status_code == 200
    intake = {'doctor_id':'doc_psy','text':'Синтетический D01: хочу обсудить сон.', 'case_consent':True}
    assert mutate(patient,'POST','/api/v1/previsit-cases', {**intake,'case_consent':False}).status_code == 422
    submitted = mutate(patient,'POST','/api/v1/previsit-cases',intake)
    assert submitted.status_code == 201
    cid = submitted.json['id']; path = '/api/v1/previsit-cases/'+cid
    doctor = app.test_client(); login_response(doctor,'doc_psy')
    assert cid in [c['id'] for c in doctor.get('/api/v1/previsit-cases').json['items']]
    assert doctor.get(path).json['intake']['text'] == intake['text']
    assert doctor.post(path+'/review',json={'confirmation':True}).status_code == 403
    assert mutate(patient,'POST',path+'/review',{'confirmation':True}).status_code == 403
    assert mutate(doctor,'POST',path+'/review',{'confirmation':False}).status_code == 422
    for other_id in ('doc_ther','doc_other','pat_02','clinic_01','researcher_01'):
        other = app.test_client(); login_response(other,other_id)
        assert other.get(path).status_code == 403
        assert mutate(other,'POST',path+'/review',{'confirmation':True}).status_code == 403
    assert mutate(doctor,'POST',path+'/review',{'confirmation':True}).json['status'] == 'reviewed'
    assert mutate(doctor,'POST',path+'/review',{'confirmation':True}).status_code == 200
    assert patient.get(path).json['status'] == 'reviewed'
    with app.extensions['cc_session_factory']() as db:
        row = db.get(PrevisitCase,cid)
        assert row.patient_user_id == uid and json.loads(row.intake_json)['text'] == intake['text'] and row.status == 'reviewed'
        assert not db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.patient_id==db.get(User,uid).patient_id))
        assert len(db.scalars(select(Audit).where(Audit.action=='previsit_reviewed',Audit.object_id==cid)).all()) == 1
    assert mutate(patient,'POST',path+'/withdraw',{}).status_code == 200
    assert mutate(doctor,'POST',path+'/review',{'confirmation':True}).status_code == 403
