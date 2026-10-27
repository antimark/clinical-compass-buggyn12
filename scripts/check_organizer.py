"""Owned clean-room ZIP extraction/start/restart, ordinary accounts/invites/consent/cases.
No runtime credentials or raw clinical/model text are written into the report.
"""
import argparse,http.cookiejar,json,os,secrets,socket,subprocess,sys,tempfile,time,zipfile
from pathlib import Path
from urllib.request import build_opener,HTTPCookieProcessor,Request
from urllib.error import HTTPError,URLError
from uuid import uuid4
from build_organizer import validate_archive

def run(archive,report):
    result=dict(status='FAIL',scope='extracted organizer source with new isolated evaluation database',postgresql='NOT_RUN',keycloak='NOT_RUN',checks=[])
    process=None
    try:
        result['archive']=validate_archive(archive)
        with tempfile.TemporaryDirectory(prefix='cc04-cleanroom-') as tmp:
            source=Path(tmp)/'Clean Organizer Source';source.mkdir();workspace=Path(tmp)/'private-workspace'
            with zipfile.ZipFile(archive) as zipped:zipped.extractall(source)
            launcher=source/'scripts/evaluation.sh'
            env={k:v for k,v in os.environ.items() if not k.startswith('CC_') and k!='PYTHONPATH'};env['CC_PYTHON']=sys.executable
            basecmd=['bash',str(launcher)]
            checked=subprocess.run(basecmd+['check','--workspace',str(workspace)],cwd=source,env=env,capture_output=True,text=True,timeout=30)
            assert checked.returncode==0,'Extracted launcher runtime check failed'
            health=json.loads(checked.stdout.strip().splitlines()[-1]);assert health['local_ollama']=='available' and health['model_installed'] is True
            result['local_runtime']=health;result['checks'].append('extracted launcher imports and existing loopback Ollama/model health')
            password=secrets.token_urlsafe(28);email='operator@evaluation.test'
            made=subprocess.run(basecmd+['doctor','--workspace',str(workspace),'--email',email],cwd=source,env=env,input=password+'\n'+password+'\n',capture_output=True,text=True,timeout=45)
            assert made.returncode==0,'Ordinary operator doctor provisioning failed'
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            base='http://127.0.0.1:'+str(port)
            def launch():
                p=subprocess.Popen(basecmd+['serve','--workspace',str(workspace),'--port',str(port)],cwd=source,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                deadline=time.time()+40
                while time.time()<deadline:
                    try:
                        with build_opener().open(base+'/api/v1/health',timeout=2) as r:
                            if r.status==200:return p
                    except (URLError,TimeoutError):pass
                    if p.poll() is not None:raise AssertionError('Extracted evaluation server exited')
                    time.sleep(.2)
                p.terminate();p.wait(10);raise AssertionError('Extracted evaluation server unavailable')
            process=launch()
            def actor():return build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            def req(client,method,path,data=None,csrf=True):
                headers={}
                if data is not None:headers['Content-Type']='application/json'
                if method not in ('GET','HEAD') and csrf:headers['X-CSRF-Token']=req(client,'GET','/api/v1/onboarding/bootstrap')[1]['csrf_token']
                request=Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
                try:
                    with client.open(request,timeout=30) as response:return response.status,json.loads(response.read())
                except HTTPError as e:
                    try:return e.code,json.loads(e.read())
                    except ValueError:return e.code,{}
            doctor=actor();status,login=req(doctor,'POST','/api/v1/onboarding/login',dict(email=email,password=password));assert status==200
            doctor_id=login['user']['id'];patients=[];cases=[]
            texts=['Несколько недель тревога перед совещаниями. Хочу обсудить F41.1 и КПТ.','Тревога мешает работать. Не могу работать. Хочу плановую консультацию.','Сейчас хочу навредить себе. Тревога перед разговором.','В прошлом друг сказал: сейчас хочу навредить себе. Нет тревоги.']
            for n,text in enumerate(texts):
                client=actor();patient_email='new-'+uuid4().hex[:12]+'@evaluation.test'
                status,registered=req(client,'POST','/api/v1/onboarding/register',dict(display_name='Синтетический участник оценки',email=patient_email,password=password,terms_consent=True));assert status==201
                status,inv=req(doctor,'POST','/api/v1/onboarding/invitations',dict(recipient_email=patient_email,categories=['symptoms'],ttl_hours=24));assert status==201
                status,_=req(client,'POST','/api/v1/onboarding/invitations/accept',dict(token=inv['token'],consent=True,consent_version='clinical-link-v1'));assert status==200
                status,case=req(client,'POST','/api/v1/previsit-cases',dict(doctor_id=doctor_id,text=text,symptoms=[],conditions=[],case_consent=True));assert status==201
                patients.append(client);cases.append(dict(id=case['id'],patient_ref=registered['user']['patient_id']))
            result['checks'].append('four new ordinary patient registrations, invitations, explicit scopes/consent and unknown cases including negative')
            signals=[];deadline=time.time()+15
            while time.time()<deadline:
                status,signal_list=req(doctor,'GET','/api/v1/safety-signals');assert status==200;signals=signal_list['items']
                if len(signals)==2 and all(x['transport']['status']=='delivered' for x in signals):break
                time.sleep(.2)
            assert len(signals)==2 and {x['critical'] for x in signals}=={True,False} and all(x['transport']['receipt'] for x in signals)
            assert cases[-1]['id'] not in {s['case_ref'] for s in signals}
            status,inbox=req(doctor,'GET','/api/v1/safety-inbox');assert status==200 and len(inbox['items'])==2
            for signal in signals:
                path='/api/v1/safety-signals/'+signal['id'];status,seen=req(doctor,'POST',path+'/seen',dict(revision=signal['revision']));assert status==200
                status,acked=req(doctor,'POST',path+'/ack',dict(revision=seen['revision'],confirmed=True,idempotency_key=str(uuid4())));assert status==200 and acked['workflow_status']=='acknowledged'
            result['checks'].append('independent real test inbox receipts, negative no-signal, explicit physician seen/ACK and readback')
            case=cases[0];url='/api/v1/clinical-intelligence/patients/'+case['patient_ref']+'/referrals?encounter_id='+case['id']
            status,versions=req(doctor,'GET',url);assert status==200
            body=dict(source_version=versions['source_version'],grant_version=versions['grant_version'],authority='manual_physician',confirmed=True,decision='create',target_specialty='psychiatrist',category='mandatory',urgency='planned',clinical_reason='Ручное решение врача при независимом тестировании.',idempotency_key=str(uuid4()))
            assert req(doctor,'POST',url,body,csrf=False)[0]==403
            status,ref=req(doctor,'POST',url,body);assert status==201
            status,replay=req(doctor,'POST',url,body);assert status in (200,201) and replay['id']==ref['id']
            before=process.pid;process.terminate();process.wait(timeout=15);process=launch();assert process.pid!=before
            doctor=actor();assert req(doctor,'POST','/api/v1/onboarding/login',dict(email=email,password=password))[0]==200
            status,persisted=req(doctor,'GET','/api/v1/clinical-intelligence/referrals/'+ref['id']);assert status==200 and persisted['category']=='mandatory' and persisted['urgency']=='planned'
            status,saved=req(doctor,'GET','/api/v1/safety-signals');assert status==200 and all(x['workflow_status']=='acknowledged' for x in saved['items'])
            assert req(patients[0],'GET','/api/v1/safety-signals')[0]==403
            result.update(status='PASS',new_cases=4,actual_process_restart=True,ordinary_password_relogin=True,manual_referral_readback=True,csrf_denied=True,transport_receipts=2,clinical_review_status='experimental_needs_validation')
            result['checks'].append('CSRF denial, idempotent manual referral, actual extracted server restart/password relogin and persistent referral/ACK; patient role denied')
    except Exception as exc:result['error_type']=type(exc).__name__;raise
    finally:
        if process and process.poll() is None:process.terminate();process.wait(timeout=15)
        Path(report).parent.mkdir(parents=True,exist_ok=True);Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'status':result['status'],'new_cases':result['new_cases'],'checks':len(result['checks'])}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--report',required=True);a=p.parse_args();run(a.archive,a.report)
