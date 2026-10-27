#!/usr/bin/env python3
"""Actual isolated Keycloak26 browser/password/OTP + HTTPS application evidence.

Requires running official Keycloak on loopback58080 and task-specific admin
password in CC_PHASE5_KC_PASSWORD or /tmp/clinical_compass_phase5_infra.env.
Creates a NEW uniquely named test realm (never mutates an existing realm),
preprovisioned synthetic users and temporary SQLite application database. This
proves real IdP acceptance independently of PostgreSQL concurrency acceptance.
No tokens/passwords/OTP secrets are emitted into the report.
"""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import ssl
import struct
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
KC='http://127.0.0.1:58080'
BASE='https://127.0.0.1:58865'
PREFIX='/api/v1/auth/oidc'


def http(method,url,payload=None,token=None,form=False):
    headers={}
    data=None
    if payload is not None:
        data=urlencode(payload).encode() if form else json.dumps(payload).encode()
        headers['Content-Type']='application/x-www-form-urlencoded' if form else 'application/json'
    if token:headers['Authorization']='Bearer '+token
    req=Request(url,data=data,method=method,headers=headers)
    with urlopen(req,timeout=20) as response:
        raw=response.read()
        return json.loads(raw) if raw else None


def totp(secret, offset=0):
    data=hmac.new(secret.encode(),struct.pack('>Q',int(time.time())//30+offset),hashlib.sha1).digest()
    offset=data[-1]&15
    return str((struct.unpack('>I',data[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report-dir',required=True)
    args=parser.parse_args();out=Path(args.report_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    envfile=Path('/tmp/clinical_compass_phase5_infra.env')
    password=os.environ.get('CC_PHASE5_KC_PASSWORD')
    if not password and envfile.exists():
        password=next((line.split('=',1)[1] for line in envfile.read_text().splitlines() if line.startswith('CC_PHASE5_KC_PASSWORD=')),None)
    if not password:raise RuntimeError('Isolated Keycloak administrator credential unavailable')
    admin=http('POST',KC+'/realms/master/protocol/openid-connect/token',
        {'grant_type':'password','client_id':'admin-cli','username':'phase5admin','password':password},form=True)['access_token']
    realm=json.loads((ROOT/'infrastructure/keycloak/clinical-compass-phase5-realm.json').read_text())
    realm['realm']='clinical-compass-phase5-e2e-'+secrets.token_hex(5)
    realm_name=realm['realm'];issuer=KC+'/realms/'+realm_name
    client_id=realm['clients'][0]['clientId']
    user_password=secrets.token_urlsafe(28)
    otp_secrets={}
    users=[]
    for username,otp in [('phase5-patient',False),('phase5-doctor',True),('phase5-staff-nootp',False),('phase5-unknown',False),
            ('phase5-clinic',True),('phase5-invited-doctor',True),('phase5-invited-nootp',False),('phase5-demo-invited',True)]:
        credential=[{'type':'password','value':user_password,'temporary':False}]
        if otp:
            otp_secret=secrets.token_hex(16);otp_secrets[username]=otp_secret
            credential.append({'type':'otp','userLabel':'isolated synthetic TOTP',
                'secretData':json.dumps({'value':otp_secret}),
                'credentialData':json.dumps({'subType':'totp','digits':6,'counter':0,'period':30,'algorithm':'HmacSHA1'})})
        users.append({'username':username,'email':username+'@synthetic.invalid','enabled':True,'emailVerified':False,
            'firstName':'Synthetic','lastName':'Acceptance','credentials':credential})
    otp_secret=otp_secrets['phase5-doctor']
    realm['users']=users
    http('POST',KC+'/admin/realms',realm,admin)
    idp_users=http('GET',KC+'/admin/realms/'+realm_name+'/users',token=admin)
    subjects={user['username']:user['id'] for user in idp_users}
    jwks=http('GET',issuer+'/protocol/openid-connect/certs')
    # Temporary non-demo HTTPS application uses actual OIDC. SQLite is explicitly
    # recorded and never presented as PostgreSQL acceptance.
    with tempfile.TemporaryDirectory(prefix='cc_phase5_keycloak_') as work:
        work=Path(work);cert=work/'cert.pem';key=work/'key.pem';dbfile=work/'acceptance.sqlite'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
            '-keyout',str(key),'-out',str(cert),'-subj','/CN=127.0.0.1',
            '-addext','subjectAltName=IP:127.0.0.1'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        config={'CC_DEMO_MODE':'0','CC_APP_ENV':'synthetic_dev','CC_HTTPS':'1',
            'CC_SECRET_KEY':secrets.token_urlsafe(40),'CC_DB_PATH':str(dbfile),
            'CC_OIDC_BROWSER_ENABLED':'1','CC_OIDC_ISSUER':issuer,'CC_OIDC_CLIENT_ID':client_id,
            'CC_OIDC_AUDIENCE':'clinical-compass-api','CC_OIDC_REDIRECT_URI':BASE+PREFIX+'/callback',
            'CC_OIDC_JWKS_JSON':json.dumps(jwks),'CC_OIDC_ALLOW_LOOPBACK_HTTP':'1'}
        for name,value in config.items():os.environ[name]=value
        os.environ.pop('CC_DATABASE_URL',None)
        from cc_api import create_app
        from cc_api.models import User,Patient
        from cc_api.oidc_models import OidcLoginAttempt,OidcBrowserSession
        from sqlalchemy import select
        app=create_app();factory=app.extensions['cc_session_factory']
        with factory.begin() as db:
            db.add(Patient(id='oidc-patient',display_name='Синтетический пациент проверки',diagnosis_label='',medication_label='',severity_label='',trend='insufficient_data'))
            db.flush()
            for name,role in [('phase5-patient','patient'),('phase5-doctor','doctor'),('phase5-staff-nootp','clinic_admin'),('phase5-clinic','clinic_admin')]:
                db.add(User(id=name,display_name='Синтетическая проверка',role=role,organization_id='oidc-test',
                    patient_id='oidc-patient' if role=='patient' else None,external_subject=subjects[name]))
        runner=work/'serve.py'
        runner.write_text('from cc_api import create_app\ncreate_app().run(host="127.0.0.1",port=58865,ssl_context=('+repr(str(cert))+','+repr(str(key))+'),use_reloader=False)\n')
        process_env=os.environ.copy();process_env['PYTHONPATH']=str(ROOT/'backend')
        log=open(work/'server.log','w')
        def launch():
            proc=subprocess.Popen([sys.executable,str(runner)],env=process_env,stdout=log,stderr=log)
            context=ssl._create_unverified_context()
            for _ in range(100):
                try:
                    with urlopen(BASE+'/api/v1/health',context=context,timeout=1):return proc
                except Exception:
                    if proc.poll() is not None:raise RuntimeError('Isolated HTTPS application failed; inspect wiring/migrations')
                    time.sleep(.1)
            raise RuntimeError('Isolated HTTPS app did not start')
        proc=launch();checks=[]
        def passed(name):checks.append({'name':name,'status':'PASS'})
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True)
                def context():return browser.new_context(ignore_https_errors=True)
                def credentials(page,user):
                    page.goto(BASE+PREFIX+'/login')
                    auth_params={key:value[0] for key,value in parse_qs(urlsplit(page.url).query).items()}
                    page.locator('#username').fill(user)
                    page.locator('#password').fill(user_password);page.locator('#kc-login').click()
                    return auth_params
                wrong_password_context=context();wrong_page=wrong_password_context.new_page()
                wrong_page.goto(BASE+PREFIX+'/login');wrong_page.locator('#username').fill('phase5-patient')
                wrong_page.locator('#password').fill(user_password+'-incorrect');wrong_page.locator('#kc-login').click()
                wrong_page.locator('#username').wait_for(state='visible')
                assert wrong_password_context.request.get(BASE+'/api/v1/auth/me').status==401
                passed('actual_keycloak_wrong_password_rejected')
                wrong_password_context.close()
                # Password-only patient succeeds, without granting IdP roles.
                patient=context();page=patient.new_page();credentials(page,'phase5-patient')
                try:
                    page.wait_for_url(BASE+'/**',timeout=20000)
                except Exception:
                    print('PATIENT_NAVIGATION_DEBUG',page.locator('body').inner_text()[:2000])
                    page.screenshot(path=str(out/'patient_login_failure.png'))
                    raise
                result=patient.request.get(BASE+'/api/v1/auth/me');assert result.status==200,result.text()
                assert result.json()['context']['role']=='patient';passed('actual_patient_authorization_code_s256_without_staff_mfa')
                assert patient.request.get(BASE+'/api/v1/doctors/me/patients').status==403
                passed('cross_role_doctor_records_denied')
                assert patient.request.get(BASE+'/api/v1/auth/me',headers={'Authorization':'Bearer invalid-explicit-token'}).status==401
                assert patient.request.get(BASE+'/api/v1/auth/me').status==200
                passed('explicit_invalid_bearer_never_falls_back_to_cookie')
                checkin_payload={'mood_score':3,'comparison':'same','note':'Синтетическая проверка реального входа'}
                assert patient.request.post(BASE+'/api/v1/patients/me/check-ins',data=checkin_payload).status==403
                csrf=patient.request.get(BASE+'/api/v1/auth/me').json()['csrf_token']
                assert patient.request.post(BASE+'/api/v1/patients/me/check-ins',data=checkin_payload,
                    headers={'X-CSRF-Token':csrf,'Authorization':'Bearer invalid-explicit-token'}).status==401
                saved=patient.request.post(BASE+'/api/v1/patients/me/check-ins',data=checkin_payload,headers={'X-CSRF-Token':csrf})
                assert saved.status==201,saved.text()
                checkin_id=saved.json()['id']
                passed('ordinary_non_demo_mutation_requires_csrf_and_real_authorized_session')
                # Capture a NEW unredeemed code at the IdP form response, before
                # allowing any callback. A wrong S256 verifier must fail at the
                # actual Keycloak token endpoint, independently of replay checks.
                pkce_context=context();pkce_page=pkce_context.new_page()
                pkce_page.goto(BASE+PREFIX+'/login');pkce_capture={}
                def capture_unredeemed(route):
                    if route.request.method!='POST':
                        route.continue_();return
                    response=route.fetch(max_redirects=0)
                    location=response.headers.get('location','')
                    if urlsplit(location).path==PREFIX+'/callback':
                        pkce_capture.update({key:value[0] for key,value in parse_qs(urlsplit(location).query).items()})
                        route.fulfill(status=200,body='Synthetic acceptance: callback intentionally held')
                    else:
                        route.fulfill(response=response)
                pkce_page.route('**/login-actions/authenticate**',capture_unredeemed)
                pkce_page.locator('#username').fill('phase5-patient');pkce_page.locator('#password').fill(user_password)
                pkce_page.locator('#kc-login').click()
                assert pkce_capture.get('code')
                try:
                    http('POST',issuer+'/protocol/openid-connect/token',{'grant_type':'authorization_code',
                        'client_id':client_id,'redirect_uri':BASE+PREFIX+'/callback',
                        'code':pkce_capture['code'],'code_verifier':'incorrect-s256-verifier-value-01234567890123456789'},form=True)
                    raise AssertionError('Actual Keycloak accepted wrong S256 verifier')
                except HTTPError as error:
                    detail=json.loads(error.read());assert error.code==400 and 'PKCE' in detail.get('error_description','').upper()
                assert pkce_context.request.get(BASE+'/api/v1/auth/me').status==401
                passed('actual_keycloak_unredeemed_code_wrong_s256_verifier_rejected')
                pkce_context.close()
                # Password-only staff is rejected by application, even though IdP
                # authentication succeeds. No app privilege follows a password.
                nootp=context();p=nootp.new_page();credentials(p,'phase5-staff-nootp')
                p.wait_for_url(BASE+'/**');assert nootp.request.get(BASE+'/api/v1/auth/me').status==401
                passed('staff_without_actual_second_factor_rejected')
                unknown=context();p=unknown.new_page();credentials(p,'phase5-unknown')
                p.wait_for_url(BASE+'/**');assert unknown.request.get(BASE+'/api/v1/auth/me').status==401
                passed('unprovisioned_subject_not_auto_registered')
                doctor=context();p=doctor.new_page();captured={}
                def capture(req):
                    if urlsplit(req.url).path != PREFIX+'/callback':
                        return
                    query=parse_qs(urlsplit(req.url).query)
                    if 'code' in query:
                        captured.update(code=query['code'][0],state=query['state'][0])
                p.on('request',capture)
                auth_params=credentials(p,'phase5-doctor');p.locator('#otp').wait_for()
                from cc_api.oidc_browser import digest
                with factory() as db:
                    attempt=db.scalar(select(OidcLoginAttempt).where(OidcLoginAttempt.state_hash==digest(auth_params['state'])))
                    captured['verifier']=attempt.verifier
                valid_window={totp(otp_secret,offset) for offset in range(-2,3)}
                wrong_otp=next(str(value).zfill(6) for value in range(10) if str(value).zfill(6) not in valid_window)
                p.locator('#otp').fill(wrong_otp);p.locator('#kc-login').click()
                p.locator('#otp').wait_for(state='visible',timeout=15000)
                assert doctor.request.get(BASE+'/api/v1/auth/me').status==401
                passed('wrong_totp_rejected_before_app_session')
                p.locator('#otp').fill(totp(otp_secret));p.locator('#kc-login').click()
                p.wait_for_url(BASE+'/**',timeout=20000)
                result=doctor.request.get(BASE+'/api/v1/auth/me');assert result.status==200,result.text()
                assert result.json()['context']['role']=='doctor'
                with factory() as db:
                    record=db.scalar(select(OidcBrowserSession).where(OidcBrowserSession.user_id=='phase5-doctor'))
                    assert {'pwd','otp'}.issubset(json.loads(record.amr_json))
                passed('actual_staff_password_and_totp_verified_amr')
                # Clinic invitation is the sole role authority. Candidates have
                # real IdP subjects but no User until an authorized invitation.
                enrollment=BASE+'/api/v1/staff-enrollment'
                clinic=context();clinic_page=clinic.new_page();credentials(clinic_page,'phase5-clinic')
                clinic_page.locator('#otp').wait_for();clinic_page.locator('#otp').fill(totp(otp_secrets['phase5-clinic']))
                clinic_page.locator('#kc-login').click();clinic_page.wait_for_url(BASE+'/**')
                clinic_me=clinic.request.get(BASE+'/api/v1/auth/me');assert clinic_me.status==200
                assert clinic_me.json()['context']['role']=='clinic_admin'
                clinic_headers={'X-CSRF-Token':clinic_me.json()['csrf_token']}
                existing=clinic.request.post(enrollment+'/invitations',headers=clinic_headers,data={
                    'recipient_email':'existing@reserved.test','display_name':'Синтетический кандидат',
                    'external_subject':subjects['phase5-patient'],'specialty':'psychiatry'})
                assert existing.status==409
                passed('actual_invited_staff_existing_patient_never_promoted')
                def issue_staff(username):
                    response=clinic.request.post(enrollment+'/invitations',headers=clinic_headers,data={
                        'recipient_email':username+'@reserved.test','display_name':'Синтетический приглашённый врач',
                        'external_subject':subjects[username],'specialty':'psychotherapy'})
                    assert response.status==201,response.text()
                    return response.json()
                unassured_invite=issue_staff('phase5-invited-nootp')
                unassured=context();unassured_page=unassured.new_page();credentials(unassured_page,'phase5-invited-nootp')
                unassured_page.wait_for_url(BASE+'/**');assert unassured.request.get(BASE+'/api/v1/auth/me').status==401
                assert unassured.request.post(enrollment+'/accept',data={'token':unassured_invite['token'],'accept':True}).status in (401,403)
                passed('actual_password_only_staff_candidate_cannot_login_or_accept')
                invitation=issue_staff('phase5-invited-doctor')
                invited=context();invited_page=invited.new_page();credentials(invited_page,'phase5-invited-doctor')
                invited_page.locator('#otp').wait_for();invited_page.locator('#otp').fill(totp(otp_secrets['phase5-invited-doctor']))
                invited_page.locator('#kc-login').click();invited_page.wait_for_url(BASE+'/**')
                invited_me=invited.request.get(BASE+'/api/v1/auth/me');assert invited_me.status==200
                assert invited_me.json()['context']['role']=='staff_candidate'
                assert invited.request.get(BASE+'/api/v1/doctors/me/patients').status==403
                preview=invited.request.post(enrollment+'/preview',headers={'X-CSRF-Token':invited_me.json()['csrf_token']},data={'token':invitation['token']})
                assert preview.status==200 and preview.json()['requires_explicit_acceptance']
                invited_headers={'X-CSRF-Token':invited_me.json()['csrf_token']}
                rejected=invited.request.post(enrollment+'/accept',headers=invited_headers,data={'token':invitation['token'],'accept':False})
                assert rejected.status==422
                enrolled=invited.request.post(enrollment+'/accept',headers=invited_headers,data={'token':invitation['token'],'accept':True})
                assert enrolled.status==200,enrolled.text()
                result=enrolled.json();assert result['role_authority']=='clinic_admin_invitation'
                assert not result['professional_verification']['grants_roles']
                assert not result['professional_verification']['real_credentials_verified']
                assert result['context']['specialty']=='psychotherapy'
                assert invited.request.get(BASE+'/api/v1/auth/me').json()['context']['role']=='doctor'
                assert invited.request.post(enrollment+'/accept',headers=invited_headers,data={'token':invitation['token'],'accept':True}).status==409
                from cc_api.onboarding_models import LocalIdentity,StaffVerification
                from cc_api.models import DoctorPatientLink
                with factory() as db:
                    assert db.get(LocalIdentity,invitation['recipient']['id']) is None
                    assert db.get(StaffVerification,invitation['recipient']['id']).status=='verified_synthetic'
                    assert not db.scalar(select(DoctorPatientLink.id).where(DoctorPatientLink.doctor_id==invitation['recipient']['id']))
                passed('actual_mfa_candidate_explicit_invitation_acceptance_and_no_patient_links')
                p.screenshot(path=str(out/'actual_keycloak_staff_authenticated.png'),full_page=True)
                # Actual IdP rejects reuse of the already exchanged code.
                try:
                    http('POST',issuer+'/protocol/openid-connect/token',{'grant_type':'authorization_code',
                        'client_id':client_id,'redirect_uri':BASE+PREFIX+'/callback',
                        'code':captured['code'],'code_verifier':captured['verifier']},form=True)
                    raise AssertionError('Keycloak accepted authorization-code replay')
                except HTTPError as error:assert error.code==400
                passed('actual_keycloak_authorization_code_replay_rejected')
                assert doctor.request.get(BASE+PREFIX+'/callback?'+urlencode({'state':captured['state'],'code':captured['code']})).status==400
                passed('application_state_replay_rejected')
                # No anti-CSRF exemption for authenticated browser cookies.
                assert doctor.request.post(BASE+PREFIX+'/logout',data={}).status==403
                passed('non_demo_browser_cookie_csrf_enforced')
                proc.terminate();proc.wait(timeout=10);proc=launch()
                assert doctor.request.get(BASE+'/api/v1/auth/me').status==200
                assert patient.request.get(BASE+'/api/v1/auth/me').status==200
                assert any(item['id']==checkin_id for item in patient.request.get(BASE+'/api/v1/patients/me/check-ins').json()['items'])
                passed('opaque_session_and_authorized_observation_persist_actual_server_restart')
                copied=context();copied.add_cookies(doctor.cookies())
                csrf=doctor.request.get(BASE+'/api/v1/auth/me').json()['csrf_token'];assert csrf
                response=doctor.request.post(BASE+PREFIX+'/logout',headers={'X-CSRF-Token':csrf},data={})
                assert response.status==200,response.text()
                assert copied.request.get(BASE+'/api/v1/auth/me').status==401
                passed('logout_revokes_copied_opaque_session_server_side')
                # The ordinary synthetic UX profile must honor actual OIDC
                # sessions too; an invalid OIDC cookie never falls back to uid.
                proc.terminate();proc.wait(timeout=10);process_env['CC_DEMO_MODE']='1';proc=launch()
                assert patient.request.get(BASE+'/api/v1/auth/me').status==200
                # Real application forms create the invite and accept it after
                # the ordinary IdP redirect, rather than emulating API success.
                from playwright.sync_api import expect
                clinic_page.goto(BASE+'/#/clinic/staff?view=enrollment')
                create_form=clinic_page.locator('form[data-form="se-create"]')
                expect(create_form).to_be_visible()
                create_form.locator('[name=recipient_email]').fill('phase5-demo-invited@reserved.test')
                create_form.locator('[name=display_name]').fill('Синтетический приглашённый врач')
                create_form.locator('[name=external_subject]').fill(subjects['phase5-demo-invited'])
                create_form.locator('[name=specialty]').select_option('psychotherapy')
                with clinic_page.expect_response(lambda r:r.url==enrollment+'/invitations' and r.request.method=='POST') as created_response:
                    create_form.locator('button[type=submit]').click()
                assert created_response.value.status==201,created_response.value.text()
                demo_invitation=created_response.value.json()
                expect(clinic_page.locator('#se-issued-link')).to_be_visible()
                passed('actual_clinic_staff_invitation_form_persisted_by_server')
                demo_invited=context();demo_page=demo_invited.new_page()
                demo_page.goto(BASE+demo_invitation['url'])
                demo_page.locator('[data-action="se-login"]').click()
                demo_page.locator('#username').fill('phase5-demo-invited')
                demo_page.locator('#password').fill(user_password);demo_page.locator('#kc-login').click()
                demo_page.locator('#otp').wait_for();demo_page.locator('#otp').fill(totp(otp_secrets['phase5-demo-invited']))
                demo_page.locator('#kc-login').click();demo_page.wait_for_url(BASE+'/**')
                demo_me=demo_invited.request.get(BASE+'/api/v1/auth/me');assert demo_me.status==200,demo_me.text()
                assert demo_me.json()['context']['role']=='staff_candidate'
                acceptance=demo_page.locator('form[data-form="se-accept"]')
                expect(acceptance).to_be_visible()
                for width in (360,768,1280):
                    demo_page.set_viewport_size({'width':width,'height':900})
                    for theme in ('light','dark'):
                        demo_page.evaluate('(t)=>localStorage.setItem("cc-theme",t)',theme)
                        demo_page.reload();expect(demo_page.locator('form[data-form="se-accept"]')).to_be_visible()
                        assert demo_page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                        demo_page.screenshot(path=str(out/f'staff_invitation_{width}_{theme}.png'),full_page=True,animations='disabled')
                acceptance=demo_page.locator('form[data-form="se-accept"]')
                acceptance.locator('[name=accept]').check()
                with demo_page.expect_response(lambda r:r.url==enrollment+'/accept' and r.request.method=='POST') as accepted_response:
                    acceptance.locator('button[type=submit]').click()
                assert accepted_response.value.status==200,accepted_response.value.text()
                expect(demo_page).to_have_url(BASE+'/#/doctor')
                assert demo_invited.request.get(BASE+'/api/v1/auth/me').json()['context']['role']=='doctor'
                passed('actual_oidc_mfa_candidate_explicit_UI_enrollment_in_demo_true_profile')
                invalid_cookie=app.session_interface.get_signing_serializer(app).dumps({'uid':'doc_psy','oidc_session':'invalid-server-token'})
                fallback=context();fallback.add_cookies([{'name':'session','value':invalid_cookie,'url':BASE,'secure':True,'httpOnly':True}])
                assert fallback.request.get(BASE+'/api/v1/auth/me').status==401
                passed('demo_fixture_uid_never_bypasses_invalid_oidc_session')
                browser.close()
        finally:
            proc.terminate();proc.wait(timeout=10);log.close()
        report={'status':'PASS','service':'actual Keycloak26 password+TOTP browser authorization-code/S256',
            'database':'temporary SQLite (PostgreSQL acceptance separate)','realm':realm_name,
            'application_transport':'loopback HTTPS, self-signed test certificate',
            'keycloak_transport':'isolated loopback HTTP, not production TLS evidence',
            'email_and_professional_verification':'NOT_TESTED; explicitly synthetic accounts',
            'checks':checks,'passed':len(checks),'production_readiness':False}
        (out/'keycloak_browser_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        (out/'patient_login_failure.png').unlink(missing_ok=True)
        print(json.dumps({'status':'PASS','checks':len(checks),'report':str(out/'keycloak_browser_report.json')}))


if __name__=='__main__':main()
