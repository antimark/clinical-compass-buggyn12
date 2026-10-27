"""Disposable real HTTP/process restart proof for integrated Phase 4 workflows.

Patient authentication uses persisted synthetic password/session providers. The
physician uses the existing explicit synthetic-dev fixture switch, not real MFA.
Never targets a pre-existing database or running user server.
"""
import http.cookiejar
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime,timedelta,timezone

ROOT=Path(__file__).resolve().parents[1]
OB='/api/v1/onboarding'
PX='/api/v1/patient-experience'
DX='/api/v1/doctor-experience'
CW='/api/v1/clinical-workflow'
BK='/api/v1/booking'

class Client:
    def __init__(self,base):
        self.base=base
        self.jar=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def request(self,path,method='GET',payload=None,expected=200):
        headers={'Content-Type':'application/json'}
        if method!='GET':headers['X-CSRF-Token']=self.request(OB+'/bootstrap')['csrf_token']
        data=json.dumps(payload).encode() if payload is not None else None
        request=urllib.request.Request(self.base+path,data=data,headers=headers,method=method)
        try:
            with self.opener.open(request,timeout=15) as response:status,body=response.status,json.load(response)
        except urllib.error.HTTPError as error:status,body=error.code,json.load(error)
        assert status==expected,(method,path,status,body)
        return body


def main():
    with tempfile.TemporaryDirectory(prefix='cc_phase4_restart_') as folder:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        env=dict(os.environ,CC_DEMO_MODE='1',CC_APP_ENV='synthetic_dev',CC_SEED_PATIENT_PERSONAS='1',
            CC_AI_MODE='disabled',CC_PORT=str(port),CC_PUBLIC_BASE_URL=base,
            CC_SECRET_KEY='DISPOSABLE_PHASE4_HTTP_RESTART_ONLY',CC_DB_PATH=str(Path(folder)/'restart.sqlite'))
        env.pop('CC_DATABASE_URL',None)
        patient,doctor,other,admin=[Client(base) for _ in range(4)]
        process=None
        def stop():
            if process is not None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        def start():
            proc=subprocess.Popen([sys.executable,'backend/run.py'],cwd=ROOT,env=env,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                for _ in range(150):
                    if proc.poll() is not None:raise RuntimeError('Disposable Flask startup failed')
                    try:patient.request('/api/v1/health');return proc
                    except (urllib.error.URLError,TimeoutError):time.sleep(.1)
                raise RuntimeError('Disposable Flask startup timed out')
            except BaseException:
                proc.terminate();proc.wait(timeout=5);raise
        try:
            process=start()
            email='phase4-process@demo.test';password='Synthetic-process-restart-pass-42'
            patient.request(OB+'/register','POST',{'display_name':'Синтетический HTTP пациент',
                'email':email,'password':password,'terms_consent':True},201)
            pid=patient.request('/api/v1/auth/me')['user']['patient_id']
            assert patient.request(PX+'/dashboard')['series']==[]
            doctor.request('/api/v1/dev/switch-user','POST',{'user_id':'doc_psy'})
            invitation=doctor.request(OB+'/invitations','POST',{'recipient_email':email,
                'categories':['symptoms','diagnosis','medications'],'ttl_hours':24},201)
            patient.request(OB+'/invitations/accept','POST',{'token':invitation['token'],
                'consent':True,'consent_version':'clinical-link-v1'})
            ids=[]
            for index,value in enumerate((5,1)):
                created=patient.request(PX+'/observations','POST',{'metric_key':'wellbeing','unit':'points',
                    'scale_version':'mood_1_5_v1','value':value,'event_key':'restart-warning-'+str(index),
                    'observed_at':f'2026-04-0{index+1}T10:00:00Z'},201)
                ids.append(created['id'])
            signal=next(s for s in doctor.request(DX+'/dashboard')['warnings'] if
                {p['id'] for p in s['evidence'].get('observations',[])}==set(ids))
            doctor.request(DX+'/patients/'+pid+'/priority','PUT',{'priority':3,'revision':0,'note':'Synthetic independent priority'})
            doctor.request(DX+'/signals/'+signal['id']+'/review','POST',{'status':'acknowledged','assessment':'Synthetic source review'})
            assignment=doctor.request(PX+'/questionnaires/assignments','POST',{'patient_id':pid,'definition_id':'demo_10_v1'},201)
            endpoint=PX+'/questionnaires/assignments/'+assignment['id']
            draft=patient.request(endpoint)['draft']
            saved=patient.request(endpoint+'/draft','PUT',{'definition_version':'1','revision':draft['revision'],
                'answers':{f'q{i}':2 for i in range(1,11)},'last_page':0})
            result=patient.request(endpoint+'/submit','POST',{'definition_version':'1',
                'revision':saved['draft']['revision'],'idempotency_key':'process-completion'},201)
            assert result['score']==20
            version=doctor.request(CW+'/icd10?q=F32')['version']
            match=doctor.request('/api/v1/references/matches?code=F32&version='+version)['items'][0]
            reference=match['reference']
            content={'narrative':'Synthetic released process proof','diagnoses':[{'code':'F32','version':version,'status':'preliminary'}],
                'items':[{'item_type':'medication','title':reference['title'],
                    'reference_id':reference['id'],'reference_version':reference['version']}]}
            doc=doctor.request(CW+'/patients/'+pid+'/documents','POST',{'kind':'treatment','mode':'quick','content':content},201)
            patient.request(CW+'/documents/'+doc['id'],expected=404)
            signed=doctor.request(CW+'/documents/'+doc['id']+'/sign','POST',{'revision':doc['revision']})
            patient.request(CW+'/documents/'+doc['id'],expected=404)
            published=doctor.request(CW+'/documents/'+doc['id']+'/publish','POST',{'revision':signed['revision']})
            oid=published['orders'][0]['id']
            patient.request(CW+'/medication-orders/'+oid+'/report','POST',{'outcome':'partial','note':'Synthetic HTTP report'},201)
            case=patient.request('/api/v1/previsit-cases','POST',{'doctor_id':'doc_psy','text':'Synthetic booking case','case_consent':True},201)
            origin=datetime.now(timezone.utc).replace(microsecond=0)+timedelta(days=12)
            slots=[]
            for index in range(2):
                begins=origin+timedelta(hours=index)
                slots.append(doctor.request(BK+'/slots','POST',{'starts_at':begins.isoformat(),
                    'ends_at':(begins+timedelta(minutes=30)).isoformat()},201)['id'])
            proposal=doctor.request(BK+'/cases/'+case['id']+'/proposals','POST',{'slot_ids':slots},201)
            appointment=proposal['candidates'][0]['appointment_id']
            assert patient.request(BK+'/appointments/'+appointment+'/accept','POST',{})['status']=='confirmed'
            snapshot=patient.request(CW+'/documents/'+doc['id'])
            stop();process=start()
            # Cookies are retained across an actual process replacement. Patient
            # cookie resolves through persisted LocalAuthSession, not injected auth.
            assert patient.request(CW+'/documents/'+doc['id'])==snapshot
            assert patient.request(endpoint+'/result')==result
            detail=doctor.request(DX+'/signals/'+signal['id'])
            assert detail['evidence']==signal['evidence'] and len(detail['reviews'])==1
            row=next(p for p in doctor.request(DX+'/dashboard')['patients'] if p['id']==pid)
            assert row['physician_priority']==3
            assert patient.request(BK+'/cases/'+case['id']+'/proposals')['items'][0]['status']=='accepted'
            patient.request(OB+'/logout','POST',{})
            patient.request(CW+'/documents/'+doc['id'],expected=401)
            patient.request(OB+'/login','POST',{'email':email,'password':password})
            assert patient.request(CW+'/documents/'+doc['id'])==snapshot
            assert patient.request(endpoint+'/result')['score']==20
            other.request('/api/v1/dev/switch-user','POST',{'user_id':'doc_other'})
            other.request(CW+'/documents/'+doc['id'],expected=404)
            admin.request('/api/v1/dev/switch-user','POST',{'user_id':'platform_01'})
            admin.request(CW+'/documents/'+doc['id'],expected=403)
            patient.request('/api/v1/patients/me/clinical-links/doc_psy','DELETE',{})
            patient.request(CW+'/documents/'+doc['id'],expected=404)
            doctor.request(CW+'/documents/'+doc['id'],expected=404)
            doctor.request(DX+'/signals/'+signal['id'],expected=404)
            assert patient.request(CW+'/patients/'+pid+'/medication-orders')['items']==[]
            patient.request('/api/v1/p0/plan-items/'+oid+'/report','POST',{'outcome':'completed'},404)
            # Case consent is independent of revoked permanent clinical linking.
            assert patient.request(BK+'/cases/'+case['id']+'/proposals')['items'][0]['status']=='accepted'
            print('PASS: actual HTTP Flask restart and persisted patient session; physician evidence/review/priority;')
            print('server-scored questionnaire; draft/sign/release with pinned reference order/adherence; persisted booking;')
            print('logout/login, role/tenant denial and revocation-sensitive document/plan/report reads.')
            print('Synthetic SQLite and explicit demo physician switch only. PostgreSQL/Keycloak/real PKCE/staff MFA NOT_RUN.')
        finally:stop()

if __name__=='__main__':main()
