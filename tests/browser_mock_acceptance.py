"""Optional browser/API-mock acceptance test for the rebuilt frontend.

Run: python tests/browser_mock_acceptance.py
This deliberately does NOT claim live Flask/auth/CSRF/database acceptance.
"""
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from threading import Thread
from urllib.parse import urlparse,parse_qs
from importlib.util import spec_from_file_location,module_from_spec
from playwright.sync_api import sync_playwright
import json,runpy,os

ROOT=Path(__file__).resolve().parents[1]
FRONTEND=ROOT/'frontend/dist'
spec=spec_from_file_location('demo_questionnaires',ROOT/'backend/cc_api/demo_questionnaires.py')
questions=module_from_spec(spec);spec.loader.exec_module(questions)
definitions=questions.DEFINITIONS+questions.evaluation_definitions()
byid={d['id']:d for d in definitions}
catalog=runpy.run_path(str(ROOT/'backend/cc_api/clinical_catalog_v3.py'))

class StaticHandler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(FRONTEND),**kwargs)
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path.startswith('/api/'):
            self.send_error(503);return
        return super().do_GET()

server=ThreadingHTTPServer(('127.0.0.1',0),StaticHandler)
thread=Thread(target=server.serve_forever,daemon=True)
thread.start()
url=f'http://127.0.0.1:{server.server_port}'
assignments={};submissions={};nextid=0;errors=[];requests=[]

def payload(assignment):
    return {k:v for k,v in assignment.items() if k not in ('answers','revision')}

def mock(route):
    global nextid
    req=route.request;parsed=urlparse(req.url);path=parsed.path;method=req.method
    body=req.post_data_json if method in ('POST','PUT') else None
    status=200;data={}
    requests.append((method,path))
    try:
        if path=='/api/v1/onboarding/bootstrap':
            data={'enabled':True,'environment':'evaluation_sandbox'}
        elif path=='/api/v1/auth/me':
            data={'context':{'role':'patient'},'user':{'id':'p1','display_name':'Test User'},'features':{}}
        elif path=='/api/v1/auth/oidc/capabilities':data={'enabled':False}
        elif path=='/api/v1/p0/auth/capabilities':data={}
        elif path=='/api/v1/patient-experience/questionnaires/definitions':data={'items':definitions}
        elif path=='/api/v1/patient-experience/questionnaires/assignments':data={'items':list(map(payload,assignments.values()))}
        elif path=='/api/v1/patient-experience/questionnaires/self-assign' and method=='POST':
            key=body['definition_id'];assert key in byid and key.startswith('eval_')
            nextid+=1;aid='test_'+str(nextid);assignment={'id':aid,'definition_id':key,'definition_version':byid[key]['version'],'status':'assigned','answers':{},'revision':0,'created_at':'2026-10-27T10:00:00Z'}
            assignments[aid]=assignment;data=payload(assignment);status=201
        elif path.startswith('/api/v1/patient-experience/questionnaires/assignments/'):
            suffix=path.split('/assignments/')[1];aid=suffix.split('/')[0];assignment=assignments[aid];d=byid[assignment['definition_id']]
            if suffix.endswith('/draft') and method=='PUT':
                assert body['revision']==assignment['revision']
                questions.validate_answers(d,body['answers']);assignment['answers'].update(body['answers']);assignment['revision']+=1
                data={'draft':{'revision':assignment['revision']}}
            elif suffix.endswith('/submit') and method=='POST':
                assert body['revision']==assignment['revision']
                score=questions.score_answers(d,assignment['answers']);assignment['status']='submitted'
                submissions[aid]={'title':d['title'],'score':score,'min_score':d['min_score'],'max_score':d['max_score'],'disclaimer':d['disclaimer'],'evaluation_draft':True,'technical_note':d['technical_note'],'submitted_at':'2026-10-27T11:00:00Z','answers':[{'question_id':q['id'],'label':q['label'],'value':assignment['answers'][q['id']],'answer_label':next(o['label'] for o in q['options'] if o['value']==assignment['answers'][q['id']])} for q in d['questions']]}
                data=submissions[aid];status=201
            elif suffix.endswith('/result'):data=submissions[aid]
            else:data={'assignment':payload(assignment),'definition':d,'draft':{'answers':assignment['answers'],'revision':assignment['revision'],'last_page':0}}
        elif path=='/api/v1/clinical-catalog/search':
            q=parse_qs(parsed.query)
            data=catalog['search'](q=q.get('q',[''])[0],kind=q.get('type',[''])[0],page=int(q.get('page',[1])[0]),per_page=int(q.get('per_page',[20])[0]))
        elif path.startswith('/api/v1/clinical-catalog/'):
            kind,identifier=path.removeprefix('/api/v1/clinical-catalog/').split('/',1)
            data=catalog['get_item'](kind,identifier)
            if not data:status=404;data={'error':{'message':'not found'}}
        else:status=404;data={'error':{'message':'not mocked'}}
    except Exception as exc:
        status=500;data={'error':{'message':repr(exc)}};errors.append((method,path,repr(exc)))
    route.fulfill(status=status,content_type='application/json',body=json.dumps(data,ensure_ascii=False,default=str))

try:
 with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=os.getenv('CC_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page=browser.new_page(viewport={'width':1280,'height':900})
    page.route('**/api/v1/**',mock)
    page.on('pageerror',lambda e:errors.append(('JS',str(e))))
    page.goto(url+'/#/patient/tasks',wait_until='domcontentloaded')
    page.get_by_role('heading',name='Мои задания').wait_for()
    for code in ('phq_9','phq_2','gad_7','gad_2'):
        did='eval_'+code+'_v1';d=byid[did]
        page.locator('button[data-command="start-assessment"][data-id="'+did+'"]').click()
        page.get_by_role('heading',name=d['title'],exact=False).first.wait_for()
        labels=page.locator('form[data-form="questionnaire"] legend').all_text_contents()
        assert len(labels)==len(d['questions']),(code,len(labels))
        # Answer minimum score for first three and maximum for the fourth.
        for q in d['questions']:
            chosen=q['options'][-1]['value'] if code=='gad_2' else q['options'][0]['value']
            page.locator('form[data-form="questionnaire"] input[name="'+q['id']+'"][value="'+str(chosen)+'"]').check()
        page.locator('form[data-form="questionnaire"] button[type="button"][data-command="save-questionnaire"]').click()
        page.get_by_text('Черновик сохранён сервером').wait_for()
        page.locator('form[data-form="questionnaire"] button.btn-primary').click()
        page.get_by_role('heading',name='Результат опросника').wait_for()
        expected=d['max_score'] if code=='gad_2' else d['min_score']
        page.get_by_role('heading',name=str(expected)+' из '+str(d['max_score'])+' баллов').wait_for()
        page.goto(url+'/#/patient/tasks')
        page.get_by_role('heading',name='Мои задания').wait_for()
        assert page.get_by_role('link',name='Посмотреть результат').count()>=1
        print('BROWSER PASS',did,len(d['questions']),expected)
    page.goto(url+'/#/clinical-library?type=medicine')
    page.get_by_text('Найдено: 77').wait_for()
    assert page.get_by_role('link',name='Следующая').count()==1
    page.get_by_role('link',name='Следующая').click()
    page.get_by_text('Страница 2 из 2').wait_for()
    page.goto(url+'/#/clinical-library?type=medicine&item=medicine%3Aproduct%3Alamictal_lamotrigine_25mg')
    # Request confirms that an actual product record can be rendered and source details expanded.
    page.get_by_text('Исходные данные полностью',exact=False).first.wait_for()
    assert page.locator('.reference-section').count()>8
    print('BROWSER PASS catalog pagination and source-product full sections')
    if errors:raise AssertionError(errors)
    browser.close()
finally:
 server.shutdown();server.server_close()
print('PASS — browser/API-mock acceptance; no live Flask tested')
