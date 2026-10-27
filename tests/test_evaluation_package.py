"""Packaging boundary and private persistent evaluation launcher checks."""
import importlib.util,json,stat
from pathlib import Path
import pytest
from cc_api.evaluation_launcher import workspace_config
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('organizer_builder',ROOT/'scripts/build_organizer.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

@pytest.mark.parametrize('name',['backend/data/dev.sqlite','BACKEND/data/DEV.SQLITE','backend/cc_api/__pycache__/x.pyc','frontend/.DS_Store','backend/.ENV','backend/token.secret','tests/a.zip','tests/a.ZIP','tests/.env.example','frontend/x.sqlite-WAL','/backend/x.py','backend/../private.py','backend/a\\b.py','tests_e2e/jury-actors.json','tests_e2e/restart-session.json','frontend/jury-demo-patient.json','backend/jury-linked-patient.json','tests_e2e/workspace-key-hashes.json','tests_e2e/jury-second-doctor.json'])
def test_forbidden_package_members(name):assert not builder.allowed(name)

def test_source_allowlist_and_stable_private_workspace(tmp_path):
    assert builder.allowed('backend/cc_api/app.py') and builder.allowed('clinical_catalog_data/v5/diagnoses/by_code/f41_1.json')
    assert builder.allowed('evaluation.config.example') and not builder.allowed('Clinical_Compass_Demo_Accounts.txt')
    folder=tmp_path/'private';a=workspace_config(folder);b=workspace_config(folder)
    assert a['SECRET_KEY']==b['SECRET_KEY'] and a['DB_PATH']==b['DB_PATH']
    assert a['APP_ENV']=='evaluation_sandbox' and a['SEED_PATIENT_PERSONAS'] is False
    assert stat.S_IMODE((folder/'session.secret').stat().st_mode)==0o600
    assert not Path(a['DB_PATH']).exists()  # Configuration does not seed/reset.
    (folder/'session.secret').chmod(0o644)
    with pytest.raises(ValueError):workspace_config(folder)

def test_workspace_rejects_repository_and_external_database(tmp_path,monkeypatch):
    with pytest.raises(ValueError):workspace_config(ROOT/'forbidden-test-workspace')
    monkeypatch.setenv('CC_DATABASE_URL','postgresql+psycopg://unused')
    with pytest.raises(ValueError):workspace_config(tmp_path/'private')

def test_operator_roles_no_grants_or_overwrite(tmp_path):
    from cc_api import create_app
    from cc_api.evaluation_workspace import provision_account
    from cc_api.models import DoctorPatientLink
    from sqlalchemy import select,func
    cfg=workspace_config(tmp_path/'operator');cfg['TESTING']=True
    app=create_app(cfg)
    for role in ['doctor','clinic_admin','researcher']:
        provision_account(app,role+'@evaluation.test','Disposable-operator-account-42',role=role)
    with app.extensions['cc_session_factory']() as db:assert db.scalar(select(func.count()).select_from(DoctorPatientLink))==0
    with pytest.raises(ValueError):provision_account(app,'doctor@evaluation.test','Disposable-operator-account-42')
    with pytest.raises(ValueError):provision_account(app,'root@evaluation.test','Disposable-operator-account-42',role='platform_admin')
    app.extensions['safety_runtime'].close();app.extensions['cc_session_factory'].kw['bind'].dispose()
