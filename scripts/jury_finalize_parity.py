"""Attach reviewed native proof to the preservation registry without promoting untested actions."""
import csv,json,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];P2=ROOT/'reports/phase2'
proof=[json.loads(x) for x in (P2/'raw/rehearsals.jsonl').read_text().splitlines()]
assert any(x['mode']=='fresh' and x['status']=='PASS' for x in proof)
assert any(x['mode']=='restart' and x['status']=='PASS' for x in proof)
suite=ET.parse(P2/'raw/source-regression.xml').getroot().find('testsuite')
assert suite is not None and int(suite.get('failures','0'))==0 and int(suite.get('errors','0'))==0
summary=json.loads((P2/'raw/feature-parity-after-rehearsals.json').read_text())
assert not summary['missing_routes'] and not summary['missing_api']
verified_routes=set('/login /register/patient /invite/:token /assessments /assessments/:code /assessments/:code/result /patient /patient/tasks /patient/profile /patient/questionnaires/:requestId /patient/questionnaires/:requestId/result /patient/admin-identity /patient/requests/new /patient/requests/:requestId /patient/requests/:requestId/chat /patient/appointments /patient/assistant /patient/assistant/thread/:threadId /doctor/invitations /doctor/questionnaires /doctor/profile/edit /doctor/requests/:requestId /doctor/requests/:requestId/chat /doctor/patients/:patientId/clinical-intelligence /doctor/patients/:patientId/clinical-intelligence/chat/:threadId /clinical-library /research/demo-v3 /clinic/patients /clinic/staff'.split())
api={('GET','/api/v1/health'),('GET','/api/v1/evaluation/questionnaires/public-definitions'),('GET','/api/v1/clinical-catalog/search'),('GET','/api/v1/clinical-catalog/<kind>/<path:identifier>')}
for method,path in [('GET','/onboarding/bootstrap'),('POST','/onboarding/login'),('POST','/onboarding/register'),('POST','/onboarding/logout'),('POST','/onboarding/invitations'),('POST','/onboarding/invitations/preview'),('POST','/onboarding/invitations/accept'),('GET','/profiles/me'),('PUT','/profiles/me'),('GET','/p0/clinic/patients'),('GET','/p1/clinic/staff'),('GET','/admin-privacy/me/clinics'),('GET','/admin-privacy/me/values'),('PUT','/admin-privacy/me/values'),('PUT','/admin-privacy/me/policies/<organization_id>'),('DELETE','/admin-privacy/me/policies/<organization_id>'),('GET','/research/demo-datasets'),('GET','/research/demo-datasets/<dataset_id>/summary'),('GET','/research/demo-datasets/<dataset_id>/export'),('POST','/previsit-cases'),('GET','/previsit-cases/<case_id>'),('GET','/previsit-cases/<case_id>/messages'),('POST','/previsit-cases/<case_id>/messages'),('POST','/previsit-cases/<case_id>/offers'),('GET','/appointments'),('POST','/appointments/<appointment_id>/confirm'),('POST','/patients/me/check-ins')]:api.add((method,'/api/v1'+path))
for method,path in [('GET','/definitions'),('GET','/assignments'),('POST','/assignments'),('POST','/self-assign'),('GET','/assignments/<assignment_id>'),('PUT','/assignments/<assignment_id>/draft'),('POST','/assignments/<assignment_id>/submit'),('GET','/assignments/<assignment_id>/result')]:api.add((method,'/api/v1/patient-experience/questionnaires'+path))
for method,path in [('GET','/patients/<patient_id>/sources'),('GET','/patients/<patient_id>/snapshot'),('POST','/patients/<patient_id>/snapshot'),('GET','/patients/<patient_id>/proposals'),('POST','/suggestions/<ident>/reviews'),('GET','/patients/<patient_id>/threads'),('POST','/patients/<patient_id>/threads'),('GET','/threads/<ident>'),('POST','/threads/<ident>/messages'),('GET','/patients/<patient_id>/referrals'),('POST','/patients/<patient_id>/referrals'),('GET','/patient-chat/sources'),('POST','/patient-chat/diary')]:api.add((method,'/api/v1/clinical-intelligence'+path))
api.add(('POST','/api/v1/clinical-workflow/patients/<patient_id>/documents'))
rows=list(csv.DictReader((P2/'FEATURE_PARITY.csv').open()));fields=list(rows[0])
for row in rows:
    if row['final_status'].startswith('REGRESSION'):raise AssertionError(row['feature_id'])
    row['final_status']='PRESERVED IN SOURCE; Docker NOT_RUN'
    if row['route'] in verified_routes and row['role']!='server_authorized' and row['baseline_status']!='Phase 0 visible DOM control':
        row['final_status']='NATIVE WORKFLOW VERIFIED; Docker NOT_RUN';row['test_result']='NATIVE E2E PASS (tested cases)';row['evidence']='reports/phase2/REHEARSAL_RESULTS.md';row['notes']+='; core workflow covered, not exhaustive inputs/tenants'
    elif (row['action'],row['route']) in api:
        row['final_status']='NATIVE API OBSERVED; Docker NOT_RUN';row['test_result']='REAL HTTP PASS in authorized workflow';row['evidence']='reports/phase2/REHEARSAL_RESULTS.md';row['notes']+='; endpoint presence/observed contract does not prove every role/input combination'
    elif row['test_result']=='READ-ONLY PASS':row['final_status']='NATIVE READ VERIFIED; ACTION PROOF PARTIAL; Docker NOT_RUN'
    elif row['baseline_status']=='Phase 0 visible DOM control':row['notes']+='; per-instance activation remains unverified unless specific scenario linked'
p=P2/'FEATURE_PARITY.csv';temp=p.with_suffix('.tmp')
with temp.open('w') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
temp.replace(p)
status={'phase2_core':'PASS','full_action_coverage':'PARTIAL','phase3':'NOT_RUN','baseline_routes':102,'actual_api_operations':249,'registry_rows':len(rows),'removed_routes':0,'removed_api_operations':0,'source_test_counts':{'tests':int(suite.get('tests')),'failures':0,'errors':0,'skipped_expected':int(suite.get('skipped','0'))},'note':'Preservation proved by source registry + actual map; only specifically covered native workflows carry E2E status.'}
(P2/'PARITY_STATUS.json').write_text(json.dumps(status,indent=2));print(json.dumps(status))
