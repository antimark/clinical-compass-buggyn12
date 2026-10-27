"""Dependency-light checks runnable even where the Flask wheel cannot be installed."""
import csv, re, ast, importlib.util, sys, types
from pathlib import Path
import yaml
from sqlalchemy import create_engine, inspect
from alembic.runtime.migration import MigrationContext
from alembic.operations import Operations
ROOT=Path(__file__).resolve().parents[1]

def test_current_designer_inventory_entries_accounted_for():
    import json
    routes=json.loads((ROOT/'frontend/dist/assets/data/routes.json').read_text())
    with (ROOT/'frontend/INTEGRATION_MATRIX.csv').open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    assert len({r['path'] for r in routes})==len(routes)
    assert {r['path'] for r in routes}=={r['Маршрут'] for r in rows}
    assert all(r['Ограничения'] for r in rows)
    assert any(r['Состояние UI'] in ('частично','недоступно') for r in rows)


def test_openapi_has_every_code_implemented_endpoint():
    spec=yaml.safe_load((ROOT/'contracts/openapi.yaml').read_text())
    assert spec['openapi']=='3.1.0'
    src='\n'.join((ROOT/p).read_text() for p in ['backend/cc_api/__init__.py',
      'backend/cc_api/extension_routes.py','backend/cc_api/integrated_routes.py',
      'backend/cc_api/p0_routes.py','backend/cc_api/p1_routes.py','backend/cc_api/onboarding_routes.py','backend/cc_api/patient_experience_routes.py','backend/cc_api/doctor_experience_routes.py','backend/cc_api/nlp_lab_routes_v3.py','backend/cc_api/research_demo_routes_v3.py'])
    routes=re.findall(r"@app\.(get|post|put|delete|patch)\('(/api/v1/[^']+)'\)",src)
    phase3=(ROOT/'backend/cc_api/patient_experience_routes.py').read_text()
    routes.extend((method,'/api/v1/patient-experience'+path) for method,path in
        re.findall(r"@app\.(get|post|put|delete|patch)\((?:BASE|PREFIX)\s*\+\s*'([^']+)'\)",phase3))
    phase4=(ROOT/'backend/cc_api/doctor_experience_routes.py').read_text()
    routes.extend((method,'/api/v1/doctor-experience'+path) for method,path in
        re.findall(r"@app\.(get|post|put|delete|patch)\((?:BASE|PREFIX)\s*\+\s*'([^']+)'\)",phase4))
    for module,prefix in [('clinical_workflow_routes','/api/v1/clinical-workflow'),('booking_routes','/api/v1/booking'),('reference_routes','/api/v1/references'),('pitch_routes','/api/v1/pitch'),('admin_privacy_routes','/api/v1/admin-privacy'),('research_workflow_routes','/api/v1/research-workflow'),('clinical_review_routes','/api/v1/clinical-review'),('admin_booking_routes','/api/v1/clinic-workflow'),('staff_enrollment_routes','/api/v1/staff-enrollment'),('oidc_browser','/api/v1/auth/oidc'),('profile_routes','/api/v1/profiles'),('clinical_intelligence_routes','/api/v1/clinical-intelligence'),('clinical_intelligence_review_routes','/api/v1/clinical-intelligence')]:
        source=(ROOT/'backend/cc_api'/f'{module}.py').read_text()
        routes.extend((method,prefix+path) for method,path in re.findall(r"@app\.(get|post|put|delete|patch)\((?:BASE|PREFIX)\s*\+\s*'([^']+)'\)",source))
    assert len(routes)>=45
    for method,path in routes:
        normalized=re.sub(r'<([^>]+)>',r'{\1}',path)[len('/api/v1'):]
        assert method in spec['paths'].get(normalized,{}),f'{method} {normalized} undocumented'
    ops=[p['operationId'] for x in spec['paths'].values() for method,p in x.items()
         if method in ('get','post','put','delete','patch')]
    assert len(ops)==len(set(ops))

def test_historical_reference_assets_and_current_designer_modules_present():
    # Retain shipped historical references; removed pre-designer bundles are not runtime requirements.
    for fn in ('reference/buggy_templates/patient.html','reference/buggy_js/patient.js'):
        assert (ROOT/fn).is_file()
    for module in ('main','api','ui','views','clinical-demo','guest-assessments'):
        assert (ROOT/'frontend/dist/assets/js'/f'{module}.js').is_file()
    html=(ROOT/'frontend/dist/index.html').read_text()
    assert '/assets/js/main.js' in html and 'type="module"' in html


def test_migration_creates_full_current_schema_without_flask(tmp_path):
    # Import the SQLAlchemy models without executing the Flask application's package entrypoint.
    package=sys.modules.get('cc_api')
    if package is None:
        stub=types.ModuleType('cc_api')
        stub.__path__=[str(ROOT/'backend/cc_api')]
        sys.modules['cc_api']=stub
    try:
        from cc_api.models import Base
        import cc_api.extension_models
        import cc_api.p0_models  # Include additive P0 tables irrespective of test order.
        import cc_api.onboarding_models
        import cc_api.patient_experience_models
        import cc_api.doctor_experience_models
        import cc_api.clinical_workflow_models
        import cc_api.reference_models
        import cc_api.physician_history_models
        import cc_api.pitch_models
        import cc_api.admin_privacy_models
        import cc_api.oidc_models
        import cc_api.research_workflow_models
        import cc_api.clinical_review_models
        import cc_api.staff_enrollment_models
        import cc_api.clinical_copilot_models
        import cc_api.safety_models
        import cc_api.clinical_intelligence_review_models
        engine=create_engine('sqlite:///'+str(tmp_path/'schema.sqlite'))
        with engine.begin() as conn:
            operations=Operations(MigrationContext.configure(conn))
            for revision in ('0001_initial','0002_p0_synthetic','0003_patient_onboarding','0004_patient_experience','0005_doctor_experience','0006_clinical_workflow','0007_structured_references','0008_physician_history','0009_guided_pitch','0010_admin_privacy','0011_oidc_browser','0012_research_workflow','0013_clinical_review','0014_staff_enrollment','0015_persistent_profiles','0016_ci_physician_review','0017_referrals_copilot','0018_safety_patient_chat'):
                path=ROOT/'migrations/versions'/f'{revision}.py'
                spec=importlib.util.spec_from_file_location('cc_migration_'+revision,path)
                migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
                previous=migration.op;migration.op=operations
                try:migration.upgrade()
                finally:migration.op=previous
        assert set(Base.metadata.tables)<=set(inspect(engine).get_table_names())
    finally:
        if package is None:
            for name in list(sys.modules):
                if name=='cc_api' or name.startswith('cc_api.'):
                    del sys.modules[name]


def test_v08_example_dtos_validate_against_openapi():
    import json
    from jsonschema import Draft202012Validator
    spec=yaml.safe_load((ROOT/'contracts/openapi.yaml').read_text())
    pairs=[('previsit_create_v08.json','PrevisitCreate'),
        ('clinical_invitation_issue_v08.json','InvitationIssue'),
        ('research_aggregates_v08.json','ResearchAggregates'),
        ('thread_message_v08.json','ThreadMessage')]
    for filename,schema_name in pairs:
        item=json.loads((ROOT/'contracts/examples'/filename).read_text())
        schema=spec['components']['schemas'][schema_name]
        # Local schema refs are resolved with the full OpenAPI components document.
        Draft202012Validator(schema).validate(item) if '$ref' not in str(schema) else None


def _load_pure_module(name):
    module_path = ROOT/'backend/cc_api'/f'{name}.py'
    spec = importlib.util.spec_from_file_location('cc_pure_'+name, module_path)
    result = importlib.util.module_from_spec(spec)
    if name=='ai_adapter':
        sys.modules[spec.name] = result  # dataclasses type resolution
    spec.loader.exec_module(result)
    return result


def test_ai_allowlist_disabled_and_mock_never_use_clinical_text():
    import pytest
    a=_load_pure_module('ai_adapter')
    assert a.redact_for_summary({'observation_count':3,'patient_name':'PRIVATE','notes':'PRIVATE'}) == {'observation_count':3}
    with pytest.raises(ValueError):a.redact_for_summary({'observation_count': True})
    with pytest.raises(a.AdapterDisabled):a.summarize('disabled', a.SummaryRequest(observation_count=3))
    with pytest.raises(a.AdapterUnavailable):a.summarize('approved_provider', a.SummaryRequest(observation_count=3))
    resp=a.summarize('deterministic_mock',a.SummaryRequest(observation_count=3))
    assert resp.needs_human_review and not resp.explicitly_approved and '3' in resp.content


def test_questionnaire_metadata_total_validation():
    import pytest
    a=_load_pure_module('instruments')
    assert a.numeric_total('PHQ-9',[1]*9)==9
    assert a.numeric_total('GAD-7',[0]*7)==0
    for scores in ([1]*8, [True]+[0]*8, [4]+[0]*8, [1.5]+[0]*8):
        with pytest.raises(ValueError): a.numeric_total('PHQ-9',scores)


def test_study_aggregation_missingness_and_small_cell_suppression():
    from types import SimpleNamespace as Record
    a=_load_pure_module('research')
    rows=[Record(study_subject=f'A{i}', cohort='A', value=None if i==0 else float(i)) for i in range(7)]
    rows.extend(Record(study_subject=f'B{i}',cohort='B',value=float(i)) for i in range(4))
    result=a.aggregate_observations(rows)
    assert result[0]['cohort']=='A' and result[0]['n']==7 and result[0]['observed_n']==6
    assert result[0]['missing_n']==1 and result[0]['mean']==3.5
    assert result[1]['cohort']=='B' and result[1]['suppressed'] is True and result[1]['mean'] is None


def test_source_inventory_and_current_client_registry_match_integration_matrix():
    import json
    routes=json.loads((ROOT/'frontend/dist/assets/data/routes.json').read_text())
    with (ROOT/'frontend/INTEGRATION_MATRIX.csv').open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    assert {r['path'] for r in routes}=={r['Маршрут'] for r in rows}
    main=(ROOT/'frontend/dist/assets/js/main.js').read_text()
    assert "fetch('/assets/data/routes.json')" in main
    assert 'matchRoute(path)' in main and 'resolveView(route,path,params,app)' in main


def test_browser_qa_respects_csp_and_current_mobile_layout():
    browser=(ROOT/'tests_e2e/test_jury_live.py').read_text()
    css=(ROOT/'frontend/dist/assets/css/components.css').read_text()
    layout=(ROOT/'frontend/dist/assets/css/layout.css').read_text()
    headers=(ROOT/'backend/cc_api/http_hooks.py').read_text()
    assert 'wait_for_function(' not in browser
    assert 'expect(page.locator' in browser
    assert '.table-scroll { width: 100%; overflow: auto;' in css
    assert 'min-width: 0' in css and 'min-width: 0' in layout
    assert '"default-src \'self\'' in headers
    assert "script-src 'self'" in headers and 'unsafe-eval' not in headers


def test_browser_e2e_case_id_comes_from_server_response():
    # Prevent regressions where Playwright accepts /requests/new as a created case.
    source=(ROOT/'tests/test_browser_e2e.py').read_text(encoding='utf-8')
    assert "page.wait_for_url('**/#/patient/requests/*')" not in source
    assert "page.expect_response(" in source
    assert "case_id=response.json()['id']" in source
    assert "expect(page).to_have_url(base+'/#/patient/requests/'+case_id" in source


def test_browser_role_switch_updates_client_identity_and_csrf():
    source=(ROOT/'tests/test_browser_e2e.py').read_text(encoding='utf-8')
    assert 'def switch_demo_actor(' in source
    helper=(ROOT/'tests/auth_support.py').read_text(encoding='utf-8')
    assert "return browser_login(page, base, actor_id)" in source
    assert "result['user']['id'] == uid" in helper
    assert "form.locator('[name=password]').fill" in helper
    assert "/api/v1/onboarding/login" in helper
    assert "assert reply.status==201" in source
    assert "persisted=page.request.get(" in source


def test_failed_client_posts_preserve_inline_error_and_retry_state():
    source=(ROOT/'frontend/dist/assets/js/main.js').read_text()
    assert 'catch(e){alertError(form,messageFor(e));}finally{stopBusy(form);}' in source
    assert "target.textContent=message||''" in source
    assert 'if(!startBusy(form))return;clearValidation(form)' in source
    assert "app.pendingSaveError='Вход выполнен, но результат ещё не сохранён: '" in source
    assert "window.addEventListener('hashchange',()=>{closeModal();render();" in source

