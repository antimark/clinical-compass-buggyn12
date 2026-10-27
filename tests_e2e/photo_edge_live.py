"""Actual persisted-photo read and rejected uploads; no test-client API substitute."""
import binascii,json,os,struct,zlib
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from tests_e2e.test_jury_live import BASE,login,show,csrf
from tests_e2e.evidence import scenario
WS=Path(os.environ['CC_QA_WORKSPACE'])
def png(width,height):
 def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',binascii.crc32(kind+data)&0xffffffff)
 return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',width,height,8,2,0,0,0))+chunk(b'tEXt',b'Comment\0PRIVATE_SYNTHETIC_METADATA')+chunk(b'IDAT',zlib.compress(b'\0'+b'\0\0\0'))+chunk(b'IEND',b'')
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True);c=b.new_context();p=c.new_page();actor=json.loads((WS/'jury-actors.json').read_text())['doctor'];login(p,actor['email'],actor['password']);expect(p).to_have_url(BASE+'/#/doctor')
 if os.environ.get('CC_PHOTO_UPLOAD_FIRST')=='1':
  with scenario('native_real_photo_upload_and_normalization',role='doctor',method='actual browser multipart + macOS sips'):
   show(p,'/doctor/profile/edit');f=p.locator('[data-form=photo]');f.locator('input[type=file]').set_input_files({'name':'synthetic.png','mimeType':'image/png','buffer':png(1,1)})
   with p.expect_response(lambda r:r.url.endswith('/profiles/me/photo') and r.request.method=='POST') as saved:f.locator('button').click()
   assert saved.value.status==201
 with scenario('photo_persisted_readback_and_reload',role='doctor',method='authenticated persisted photo GET + Chromium reload'):
  profile=p.request.get(BASE+'/api/v1/profiles/me').json();url=profile['photo_url'];r=p.request.get(BASE+url);assert r.ok and r.body().startswith(b'\x89PNG') and b'PRIVATE_SYNTHETIC_METADATA' not in r.body()
  show(p,'/doctor/profile/edit');expect(p.locator('img.doctor-photo').first).to_be_visible()
 before=profile['revision']
 for name,mime,data in ([] if os.environ.get('CC_PHOTO_READBACK_ONLY')=='1' else [('malformed','image/png',b'not an image'),('mime_mismatch','image/jpeg',png(1,1)),('pixel_bomb','image/png',png(50000,50000)),('too_many_bytes','image/png',b'x'*(2*1024*1024+1))]):
  with scenario('photo_reject_'+name,role='doctor',method='real multipart upload to running app; old image retained'):
   r=p.request.post(BASE+'/api/v1/profiles/me/photo',headers={'X-CSRF-Token':csrf(p)},multipart={'revision':str(before),'file':{'name':'synthetic.png','mimeType':mime,'buffer':data}})
   assert r.status==422,(name,r.status)
   after=p.request.get(BASE+'/api/v1/profiles/me').json();assert after['revision']==before and after['photo_url']==url
 c.close();b.close()
