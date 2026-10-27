"""Read-only live route/control inventory; rendering is never classified as E2E action proof."""
import argparse,csv,json,os,re,time,datetime as dt
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
from tests_e2e.evidence import ROOT,OUT,record,snapshot
BASE=os.environ.get('CC_E2E_BASE_URL','http://127.0.0.1:8766');WS=Path(os.environ.get('CC_QA_WORKSPACE','/private/tmp/clinical-compass-jury-20261027'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--retry-incomplete',action='store_true');args=parser.parse_args()
    routes=json.loads((ROOT/'frontend/dist/assets/data/routes.json').read_text())
    actors=json.loads((WS/'jury-actors.json').read_text());actors['patient']=json.loads((WS/'jury-linked-patient.json').read_text())
    matrix=ROOT/'reports/phase0/ROUTE_CONTROL_MATRIX.csv';controls=OUT/'controls.jsonl'
    fields=['route','role','status','controls','page_errors','unexpected_http','reason','evidence']
    previous=list(csv.DictReader(matrix.open())) if matrix.exists() else []
    if previous:
        archive=OUT/('route-matrix-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.csv');archive.write_bytes(matrix.read_bytes())
    if not args.retry_incomplete:
        with matrix.open('w') as f:csv.DictWriter(f,fieldnames=fields).writeheader()
    pending={r['route'] for r in previous if r['status']!='READ-ONLY PASS'}
    updates={}
    with sync_playwright() as pw:
        b=pw.chromium.launch(headless=True)
        for role in ('guest','patient','doctor','researcher','clinic_admin'):
            ctx=b.new_context(viewport={'width':1280,'height':900},locale='ru-RU');page=ctx.new_page();page.set_default_timeout(10000)
            if role!='guest':
                token=ctx.request.get(BASE+'/api/v1/onboarding/bootstrap').json()['csrf_token']
                r=ctx.request.post(BASE+'/api/v1/onboarding/login',data={k:actors[role][k] for k in ('email','password')},headers={'X-CSRF-Token':token});assert r.ok
            values={'patientId':actors['patient']['patient_id'],'doctorId':actors['doctor']['id'],'code':'phq_2'}
            if role=='patient':
                assigned=ctx.request.get(BASE+'/api/v1/patient-experience/questionnaires/assignments').json().get('items',[])
                submitted=[r for r in assigned if r['status']=='submitted']
                if submitted:values['requestId']=submitted[0]['id']
                cases=ctx.request.get(BASE+'/api/v1/previsit-cases').json().get('items',[])
                if cases:values['caseId']=cases[0]['id']
            if role=='doctor':
                cases=ctx.request.get(BASE+'/api/v1/previsit-cases').json().get('items',[])
                if cases:values['caseId']=cases[0]['id']
            if role=='clinic_admin':
                rows=ctx.request.get(BASE+'/api/v1/p0/clinic/patients').json().get('items',[])
                if rows:values['patientRef']=rows[-1]['patient_ref']
            if role in ('patient','doctor'):
                visits=ctx.request.get(BASE+'/api/v1/appointments').json().get('items',[])
                if visits:values['appointmentId']=visits[-1]['id']
            if role=='doctor':values.pop('doctorId',None)
            selected=[r for r in routes if (not args.retry_incomplete or r['path'] in pending) and r['role']=={'guest':'shared','clinic_admin':'clinic','researcher':'research'}.get(role,role)]
            errors=[];http=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('response',lambda r:http.append(r.status) if r.status>=400 and '/api/v1/auth/me' not in r.url else None)
            for route in selected:
                start=time.monotonic();template=route['path'];path=template
                substitutions=dict(values)
                if '/requests/' in template and values.get('caseId'):substitutions['requestId']=values['caseId']
                if role=='researcher':substitutions.pop('caseId',None)
                for key,val in substitutions.items():path=path.replace(':'+key,val)
                row=dict(route=template,role=role,status='NOT RUN',controls=0,page_errors=0,unexpected_http='',reason='',evidence='reports/phase0/raw/controls.jsonl')
                errors.clear();http.clear()
                if re.search(r':\w+',path):row['reason']='No authorized existing object for dynamic parameter; not a render proof'
                else:
                    try:
                        page.goto(BASE+'/#'+path);expect(page.locator('#main h1')).to_be_visible();expect(page.locator('#main [aria-busy=true]')).to_have_count(0)
                        text=page.locator('#main').inner_text()
                        items=page.locator('a,button,input[type=submit],select,textarea').evaluate_all('els=>els.filter(e=>e.getClientRects().length).map((e,i)=>({index:i,tag:e.tagName,label:(e.innerText||e.getAttribute("aria-label")||e.getAttribute("name")||"").trim().slice(0,130),href:e.getAttribute("href"),command:e.dataset.command||null,form:e.closest("form")?.dataset.form||null,disabled:e.disabled||false,title:e.title||null}))')
                        for item in items:
                            # Runtime object IDs and invitation tokens never enter shared evidence.
                            if item['href']:
                                for key,val in values.items():item['href']=item['href'].replace(val,':'+key)
                                item['href']=re.sub(r'dq_[a-f0-9]{32}',':requestId',item['href'])
                        with controls.open('a') as f:f.write(json.dumps({'route':template,'role':role,'controls':items},ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
                        row.update(controls=len(items),page_errors=len(errors),unexpected_http=','.join(map(str,http)))
                        if errors or any(x>=500 for x in http):row['status']='DEAD END/FAIL';row['reason']='Browser exception or server 5xx'
                        elif any(t in text for t in ('Действие пока недоступно','не подключён','не подтверждён','не реализован')):row['status']='PARTIAL';row['reason']='Explicit unavailable/preview wording; action not completed'
                        elif http and role=='guest' and all(status==401 for status in http):row['status']='READ-ONLY PASS';row['reason']='Expected authentication guard; no private data shown'
                        elif http:row['status']='PARTIAL';row['reason']='API access/data error; inspect route-specific contract'
                        else:row['status']='READ-ONLY PASS';row['reason']='Rendered and controls inventoried; writes not inferred'
                    except Exception as e:row['status']='DEAD END/FAIL';row['reason']=type(e).__name__
                updates[template]=row
                if not args.retry_incomplete:
                    with matrix.open('a') as f:csv.DictWriter(f,fieldnames=fields).writerow(row);f.flush();os.fsync(f.fileno())
                record('inventory '+template,'PASS' if row['status']=='READ-ONLY PASS' else 'BLOCKED' if row['status']=='NOT RUN' else 'FAIL' if row['status']=='DEAD END/FAIL' else 'PARTIAL',time.monotonic()-start,role=role,method='live read-only route inventory',detail=row['reason'])
            if args.retry_incomplete:ctx.close();continue
            home={'guest':'/assessments','patient':'/patient/tasks','doctor':'/doctor','clinic_admin':'/clinic','researcher':'/research/demo-v3'}[role]
            for width in (360,768,1280):
                for theme in ('light','dark'):
                    start=time.monotonic();page.set_viewport_size({'width':width,'height':900});page.goto(BASE+'/#'+home)
                    expect(page.locator('#main h1')).to_be_visible()
                    page.evaluate('(theme)=>{localStorage.setItem("cc.theme",theme);document.documentElement.dataset.theme=theme}',theme)
                    size=page.evaluate('({scroll:document.documentElement.scrollWidth,view:innerWidth})')
                    record(f'responsive {role} {width} {theme}','PASS' if size['scroll']<=width+1 else 'FAIL',time.monotonic()-start,role=role,method='Chromium layout overflow; not full accessibility audit',detail=json.dumps(size))
                    if width==360:
                        dest=ROOT/'reports/phase0/screenshots';dest.mkdir(exist_ok=True)
                        page.screenshot(path=str(dest/f'{role}-{width}-{theme}.png'),full_page=True)
            ctx.close()
        b.close()
    if args.retry_incomplete:
        temp=matrix.with_suffix('.tmp')
        with temp.open('w') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(updates.get(row['route'],row) for row in previous)
        temp.replace(matrix)
    snapshot()
    print('Inventory persisted:',matrix)
if __name__=='__main__':main()
