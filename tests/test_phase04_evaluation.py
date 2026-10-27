"""Current-state names and evaluation feature availability preserve server authority."""
from test_phase03c_safety import app,source,signal,patient
from test_phase02a import doctor,consent
from test_onboarding import mutate
from cc_api.models import User
from cc_api.evaluation_workspace import provision_account
from cc_api import create_app
from sqlalchemy import select

def test_safety_patient_name_only_after_current_grant(app):
    source(app);c,item=signal(app)
    with app.extensions['cc_session_factory']() as db:
        person=db.scalar(select(User).where(User.patient_id==item['patient_ref'],User.role=='patient'))
        assert item['patient_name']==person.display_name
    with app.extensions['cc_session_factory'].begin() as db:consent(db).revoked_at='2026-10-26T00:00:00+00:00'
    assert c.get('/api/v1/safety-signals').json['items']==[]
    denied=c.get('/api/v1/safety-signals/'+item['id']);assert denied.status_code==404
    assert item['patient_name'] not in denied.get_data(as_text=True)
    assert patient(app).get('/api/v1/safety-signals').status_code==403

def test_evaluation_lab_and_research_fixture_do_not_depend_on_clinical_approval(tmp_path):
    cfg=dict(TESTING=True,DEMO_MODE=True,APP_ENV='evaluation_sandbox',EVALUATION_ACKNOWLEDGED=True,EVALUATION_TENANT='evaluation_sandbox',SECRET_KEY='Disposable-evaluation-test-secret-42',DB_PATH=str(tmp_path/'isolated.sqlite'))
    a=create_app(cfg)
    for role in ('doctor','researcher','clinic_admin'):provision_account(a,role+'@evaluation.test','Disposable-evaluation-test-42',role=role)
    from auth_support import login_response
    def account(role):
        from sqlalchemy import select
        with a.extensions['cc_session_factory']() as db:
            from cc_api.onboarding_models import LocalIdentity
            uid=db.scalar(select(LocalIdentity.user_id).where(LocalIdentity.email==role+'@evaluation.test'))
        c=a.test_client();assert login_response(c,uid).status_code==200;return c
    d=account('doctor');r=account('researcher');admin=account('clinic_admin')
    response=mutate(d,'POST','/api/v1/nlp-v3/synthetic-extract',dict(text='Синтетическое описание тревоги.',synthetic=True))
    assert response.status_code==200 and response.json['persisted'] is False
    assert mutate(admin,'POST','/api/v1/nlp-v3/synthetic-extract',dict(text='Синтетическое описание.',synthetic=True)).status_code==403
    assert r.get('/api/v1/research/demo-datasets').status_code==200
    assert d.get('/api/v1/research/demo-datasets').status_code==403
    a.extensions['safety_runtime'].close();a.extensions['cc_session_factory'].kw['bind'].dispose()
