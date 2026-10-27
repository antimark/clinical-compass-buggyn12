"""Coherent, explicitly synthetic operator fixture through ordinary authorized APIs.
No model result, grant, consent, diagnosis or clinical dose is fabricated.
"""
import json,os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from tests_e2e.test_jury_live import BASE,login,mutate,show
from tests_e2e.evidence import scenario
WS=Path(os.environ['CC_QA_WORKSPACE'])

def private(path,value):
 fd=os.open(path,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
 with os.fdopen(fd,'w') as f:json.dump(value,f)

with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True);accounts=json.loads((WS/'jury-actors.json').read_text());accounts['patient']=json.loads((WS/'jury-linked-patient.json').read_text());pages={};contexts=[]
 for role in ('doctor','patient'):
  c=b.new_context();contexts.append(c);p=c.new_page();login(p,accounts[role]['email'],accounts[role]['password']);expect(p).not_to_have_url(BASE+'/#/login');pages[role]=p
 d,p=pages['doctor'],pages['patient'];pid=accounts['patient']['patient_id'];prefix='/api/v1/clinical-workflow';title='Учебный план показа — без клинического применения'
 with scenario('coherent_demo_manual_plan_fixture',role='operator',method='explicit synthetic fixture, ordinary physician-authorized API; not a new E2E gate'):
  documents=d.request.get(BASE+prefix+'/patients/'+pid+'/documents').json()['items'];doc=next((x for x in documents if x['kind']=='treatment' and any(i['title']==title for i in x['content']['items'])),None)
  if not doc:
   created=mutate(d,'POST',prefix+'/patients/'+pid+'/documents',{'kind':'treatment','mode':'quick','content':{'narrative':'Учебный авторский план для демонстрации состояний приложения.','assessment':'','follow_up':'','diagnoses':[],'items':[{'item_type':'medication','title':title,'dose':'Учебный текст врача; не инструкция по применению','frequency':'Учебная периодичность','route':'Учебная запись','duration':'Период демонстрации','notes':'Никакой действующей дозы, выбора препарата или клинической рекомендации здесь нет.'}]}});assert created.status==201;doc=created.json()
  for prior,action in [('draft','sign'),('signed','publish')]:
   if doc['status']==prior:
    changed=mutate(d,'POST',prefix+'/documents/'+doc['id']+'/'+action,{'revision':doc['revision']});assert changed.ok;doc=changed.json()
  assert doc['status']=='published';show(p,'/patient/treatment');expect(p.locator('#main')).to_contain_text(title)
 marker=WS/'jury-demo-state.json';old=json.loads(marker.read_text()) if marker.exists() else {}
 if old.get('patient_id')!=pid:
  with scenario('coherent_demo_observation_and_pair_messages_fixture',role='operator',method='explicit synthetic authored observations/messages; real consent-scoped API'):
   for value in (5,2):assert mutate(p,'POST','/api/v1/patients/me/check-ins',{'mood_score':value,'comparison':'same','note':'Вымышленное наблюдение для демонстрации динамики.'}).status==201
   text='Учебный диалог по действующей связи, только вымышленные данные.'
   assert mutate(p,'POST','/api/v1/threads/patient_doctor/'+accounts['doctor']['id']+'/messages',{'text':text}).status==201
   assert mutate(d,'POST','/api/v1/threads/patient_doctor/'+accounts['patient']['id']+'/messages',{'text':'Учебный ответ врача сохранён.'}).status==201
 private(WS/'jury-demo-patient.json',accounts['patient']);private(marker,{'patient_id':pid,'document_id':doc['id'],'plan_title':title,'doctor_id':accounts['doctor']['id'],'patient_user_id':accounts['patient']['id']})
 for c in contexts:c.close()
 b.close()
