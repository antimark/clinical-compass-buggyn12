"""Live container parity checks: photo codec, tenant isolation and consent revocation."""
import binascii,json,os,struct,zlib
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from tests_e2e.test_jury_live import BASE,login,show,mutate
from tests_e2e.evidence import scenario
WS=Path(os.environ['CC_QA_WORKSPACE'])

def png():
    def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',binascii.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',2,2,8,2,0,0,0))+chunk(b'tEXt',b'Comment\0PRIVATE_SYNTHETIC_METADATA')+chunk(b'IDAT',zlib.compress((b'\0'+b'\x10\x40\x90'*2)*2))+chunk(b'IEND',b'')

with sync_playwright() as pw:
    b=pw.chromium.launch(headless=True);actors=json.loads((WS/'jury-actors.json').read_text());actors['patient']=json.loads((WS/'jury-linked-patient.json').read_text());foreign=json.loads((WS/'jury-isolation-actors.json').read_text());contexts=[];pages={}
    for name,actor in list(actors.items())+[('foreign_'+k,v) for k,v in foreign.items()]:
        c=b.new_context();contexts.append(c);page=c.new_page();login(page,actor['email'],actor['password']);expect(page).not_to_have_url(BASE+'/#/login');pages[name]=page
    with scenario('container_real_photo_upload_metadata_strip_reload_and_acl',role='doctor',method='real multipart + isolated Linux codec + browser readback'):
        page=pages['doctor'];show(page,'/doctor/profile/edit');form=page.locator('form[data-form=photo]')
        form.locator('input[type=file]').set_input_files({'name':'synthetic.png','mimeType':'image/png','buffer':png()})
        with page.expect_response(lambda r:r.url.endswith('/profiles/me/photo') and r.request.method=='POST') as saved:form.locator('button').click()
        assert saved.value.status==201;url=saved.value.json()['photo_url']
        response=page.request.get(BASE+url);assert response.ok and response.headers['content-type'].startswith('image/png')
        assert b'PRIVATE_SYNTHETIC_METADATA' not in response.body()
        assert pages['patient'].request.get(BASE+url).status==404
        page.reload();expect(page.locator('img.doctor-photo').first).to_be_visible()
    with scenario('container_live_foreign_tenant_rejected_before_data_and_consent_revoke',role='clinic_admin',method='real foreign local identities; Evaluation tenant authentication boundary; explicit current-patient consent + revoke'):
        p=pages['patient'];admin=pages['clinic_admin'];show(p,'/patient/admin-identity')
        values=p.locator('form[data-form=admin-identity-values]')
        for field,value in {'first_name':'Учебный','last_name':'Вымышленный','middle_name':'Примерович'}.items():
            values.locator('[name='+field+']').fill(value)
        with p.expect_response(lambda r:r.url.endswith('/me/values') and r.request.method=='PUT') as saved:
            values.locator('button').click()
        assert saved.value.ok
        show(p,'/patient/admin-identity')
        form=p.locator('form[data-form=admin-identity-consent]');form.locator('[name=confirmed]').check()
        with p.expect_response(lambda r:'/me/policies/' in r.url and r.request.method=='PUT') as granted:form.locator('button').click()
        assert granted.value.ok
        try:
            allowed=admin.request.get(BASE+'/api/v1/p0/clinic/patients').json()['items']
            named=next(x for x in allowed if x.get('fields',{}).get('middle_name')=='Примерович')
            denied=pages['foreign_clinic_admin'].request.get(BASE+'/api/v1/p0/clinic/patients')
            # The isolated Evaluation Sandbox intentionally rejects a foreign
            # organization before role or projection authorization (401).
            # Do not relax that guard merely to manufacture a multi-tenant UI.
            assert denied.status==401
            assert pages['foreign_clinic_admin'].request.get(BASE+'/api/v1/p0/clinic/patients/'+named['patient_ref']).status==401
            staff_response=pages['foreign_clinic_admin'].request.get(BASE+'/api/v1/p1/clinic/staff')
            assert staff_response.status==401
            staff=staff_response.json()
            assert 'Врач Учебный Примерович' not in json.dumps(staff,ensure_ascii=False)
            assignments=p.request.get(BASE+'/api/v1/patient-experience/questionnaires/assignments').json()['items'];aid=next(x['id'] for x in assignments if x['status']=='submitted')
            assert pages['foreign_doctor'].request.get(BASE+'/api/v1/patient-experience/questionnaires/assignments/'+aid+'/result').status==401
        finally:
            assert mutate(p,'DELETE','/api/v1/admin-privacy/me/policies/evaluation_sandbox').ok
        assert 'Примерович' not in json.dumps(admin.request.get(BASE+'/api/v1/p0/clinic/patients').json(),ensure_ascii=False)
    for c in contexts:c.close()
    b.close()
