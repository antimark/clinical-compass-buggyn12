"""Real localhost browser proof with existing private synthetic demo credentials.
Creates one physician encounter draft, never signs/publishes or prescribes.
"""
import argparse,json,os,time,datetime
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect

def main():
 p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--base',default='http://127.0.0.1:8769');p.add_argument('--resume-edit',action='store_true');a=p.parse_args();assert urlsplit(a.base).hostname in ('127.0.0.1','localhost')
 os.environ['CC_E2E_BASE_URL']=a.base
 from tests_e2e.test_jury_live import login,show
 root=Path(__file__).resolve().parents[1];out=root/'reports/phase2/raw';out.mkdir(parents=True,exist_ok=True);shots=root/'docs/final_demo/screenshots/diagnosis_medication_20261028';shots=shots if urlsplit(a.base).port==8769 else shots/'docker';shots.mkdir(parents=True,exist_ok=True)
 ws=Path(a.workspace);actor=json.loads((ws/'jury-actors.json').read_text())['doctor'];patient=json.loads((ws/'jury-demo-patient.json').read_text());pid=patient['patient_id'];base='/doctor/patients/'+pid
 count=[0]
 def record(name,**extra):
  with (out/'diagnosis_medicine_20261028.jsonl').open('a') as f:f.write(json.dumps({'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scenario':name,'base':a.base,'status':'PASS',**extra},ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
  count[0]+=1
  if count[0]%5==0:
   note=f'\nDiagnosis→medication browser {a.base}: {count[0]} scenarios PASS; last={name}; raw reports/phase2/raw/diagnosis_medicine_20261028.jsonl flushed. Resume with saved raw document ID; no repeat of successful batches.\n'
   for path in [root/'.agent/CHECKPOINT.md',root/'.agent/EXECPLAN_ACTIVE.md',root/'reports/phase2/PROGRESS.md']:
    with path.open('a') as checkpoint:checkpoint.write(note)
 def screenshot(page,name,target):
  target.evaluate("e=>e.scrollIntoView({block:'start',behavior:'instant'})");page.evaluate('window.scrollBy(0,-110)');page.wait_for_timeout(500);page.screenshot(path=str(shots/name))
 with sync_playwright() as pw:
  b=pw.chromium.launch();context=b.new_context(viewport={'width':1440,'height':1100},locale='ru-RU');page=context.new_page();page.set_default_timeout(20000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)));login(page,actor['email'],actor['password']);expect(page).to_have_url(a.base+'/#/doctor')
  if not a.resume_edit:
   show(page,base+'/visits');f=page.locator('[data-form=create-encounter]');code=f.locator('[name=diagnosis_code]');code.fill('f41.1');cards=f.locator('[data-diagnosis-matches]');expect(cards.get_by_role('heading',name='Авиандр',exact=True)).to_be_visible();expect(cards).to_contain_text('F41.1');record('lowercase_F411_exact_reference_visible')
   screenshot(page,'01_visit_f411_aviandr.png',f.locator('[data-diagnosis-row]'))
   code.fill('F32');expect(cards.get_by_role('heading',name='Препараты по диагнозу F32',exact=True)).to_be_visible();expect(cards.get_by_role('heading',name='Авиандр',exact=True)).to_have_count(0);record('different_diagnosis_no_aviandr')
   code.fill('NOT_A_CODE');expect(cards).to_contain_text('Код не найден');record('unknown_code_error_visible')
   code.fill('');expect(cards).to_be_empty();record('clear_removes_suggestions')
   code.fill('F41.1');expect(cards.get_by_role('heading',name='Авиандр',exact=True)).to_be_visible();f.locator('[name=narrative]').fill('Синтетическая демонстрация: врач ввёл структурированный F41.1. Не заключение о реальном пациенте.');f.locator('[name=diagnosis_status]').select_option('confirmed');f.locator('[name=confirmed]').check()
   with page.expect_response(lambda r:r.url.endswith('/documents') and r.request.method=='POST') as rr:f.locator('button[type=submit],button:not([type])').last.click()
   assert rr.value.status==201,rr.value.status;doc=rr.value.json();assert doc['status']=='draft' and doc['content']['diagnoses'][0]['code']=='F41.1' and doc['content']['diagnoses'][0]['status']=='confirmed';record('physician_diagnosis_persisted_draft',document_id=doc['id'])
  else:
   records=[json.loads(x) for x in (out/'diagnosis_medicine_20261028.jsonl').read_text().splitlines()]
   doc={'id':next(x['document_id'] for x in reversed(records) if x['scenario']=='physician_diagnosis_persisted_draft' and x.get('base',a.base)==a.base)}
   show(page,base+'/visits')
  page.reload();expect(page.locator('[data-form=edit-clinical-document][data-id="'+doc['id']+'"] [name=diagnosis_code]').first).to_have_value('F41.1');record('diagnosis_survives_reload_editable')
  for new_code in ('F32','F41.1'):
   editor=page.locator('[data-form=edit-clinical-document][data-id="'+doc['id']+'"]');editor.locator('xpath=..').locator('summary').click();editor.locator('[name=diagnosis_code]').first.fill(new_code);editor.locator('[name=confirmed]').check()
   with page.expect_response(lambda r:r.url.endswith('/documents/'+doc['id']) and r.request.method=='PUT') as updated:editor.locator('button').click()
   assert updated.value.status==200;assert updated.value.json()['content']['diagnoses'][0]['code']==new_code;record('edit_diagnosis_'+new_code+'_persisted')
  show(page,base+'/treatment');heading=page.get_by_role('heading',name='Препараты по диагнозу F41.1',exact=True);expect(heading).to_be_visible();screenshot(page,'02_treatment_f411_aviandr.png',heading)
  before=page.request.get(a.base+'/api/v1/clinical-workflow/patients/'+pid+'/documents').json()['items'];page.get_by_role('button',name='Выбрать Авиандр для черновика',exact=True).click();plan=page.locator('[data-form=create-treatment]');expect(plan.locator('[name=title]')).to_have_value('Авиандр');expect(plan.locator('[name=dose]')).to_have_value('');expect(plan.locator('[name=frequency]')).to_have_value('');expect(plan.locator('[name=reference_id]')).to_have_value('aviandr_maritupirdine_instruction');after=page.request.get(a.base+'/api/v1/clinical-workflow/patients/'+pid+'/documents').json()['items'];assert before==after;record('choose_fills_name_pinned_reference_only_no_document_or_dose')
  plan.locator('[name=title]').fill('Другое название врача');expect(plan.locator('[name=reference_id]')).to_have_value('');expect(plan.locator('[name=reference_version]')).to_have_value('');record('manual_title_clears_reference_binding')
  # No order is created; the populated plan has deliberately never been submitted.
  assert not errors,errors;record('no_browser_exceptions',n=0);b.close()
 print('PASS:'+str(count[0])+' real browser scenarios; encounter draft only; no plan/order created',flush=True)
if __name__=='__main__':main()
