"""Phase01B real HTTP persistence, publication and private-photo boundaries."""
import io
import struct
import zlib
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from cc_api import create_app
from cc_api.models import User
from auth_support import login_response

BASE = '/api/v1/profiles/me'


def png(width=2, height=2):
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width,height,8,2,0,0,0)) + chunk(b'IDAT',zlib.compress((b'\0'+b'\x33\x88\xaa'*width)*height)) + chunk(b'IEND',b'')


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv('CC_DATABASE_URL', raising=False)
    return create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev',
        'SECRET_KEY':'phase01b-disposable-tests','DB_PATH':str(tmp_path/'profiles.sqlite')})


def actor(app, uid):
    client=app.test_client();login_response(client,uid);return client


def mutate(client, method, path, data):
    csrf=client.get('/api/v1/onboarding/bootstrap').json['csrf_token']
    return client.open(path,method=method,json=data,headers={'X-CSRF-Token':csrf})


def save(client, **fields):
    revision=client.get(BASE).json['revision']
    return mutate(client,'PUT',BASE,{'revision':revision,**fields})


def upload(client, data=None, filename='synthetic.png', mime='image/png', revision=None):
    if revision is None:revision=client.get(BASE).json['revision']
    csrf=client.get('/api/v1/onboarding/bootstrap').json['csrf_token']
    return client.post(BASE+'/photo',data={'revision':str(revision),'file':(io.BytesIO(png() if data is None else data),filename,mime)},headers={'X-CSRF-Token':csrf})


def test_patient_saved_reload_relogin_and_untrusted_fields(app):
    patient=actor(app,'pat_01')
    assert patient.put(BASE,json={'revision':0,'display_name':'Нет CSRF'}).status_code==403
    saved=save(patient,display_name='Синтетический профиль',bio='Только демонстрация',contact_preference='none')
    assert saved.status_code==200,saved.json
    for client in (patient,actor(app,'pat_01')):
        state=client.get(BASE).json
        assert state['display_name']=='Синтетический профиль' and state['bio']=='Только демонстрация'
        assert state['contact_preference']=='none' and state['revision']==saved.json['revision']
    for fields in ({'role':'doctor'},{'user_id':'pat_02'},{'public_visibility':True},{'education':[]},{'contact_preference':'sms'}):
        assert save(patient,**fields).status_code==422
    assert app.test_client().get(BASE).status_code==401
    with app.extensions['cc_session_factory']() as db:assert db.get(User,'pat_01').role=='patient'
    # No arbitrary resource update endpoint; client-supplied owner is forbidden.
    assert mutate(actor(app,'pat_02'),'PUT',BASE,{'revision':0,'user_id':'pat_01','display_name':'чужое'}).status_code==422


def doctor_fields():
    return {'display_name':'Синтетический врач 01B','bio':'Описание врача', 'public_visibility':True,'photo_visible':True,
      'specialty_label':'Психиатрия','public_contact':'reception@reserved.test',
      'education':[{'type':'specialist','institution':'Синтетический университет','specialization':'Психиатрия','year_to':2015,'document':'PRIVATE-DEMO-DOCUMENT'},
                   {'type':'advanced','institution':'Демо институт','specialization':'Другое','year_to':2025}],
      'certificates':[{'title':'Демо аккредитация','issuer':'Демо центр','issued_at':'2025-01-01','expires_at':'2030-01-01','kind':'accreditation'}],
      'publications':[{'title':'Синтетическая публикация','journal':'Демо журнал','published_at':'2025','doi':'https://doi.org/10.1234/DEMO.01','authors':'Демо Автор','link':'https://reserved.test/article'}]}


def test_doctor_lists_atomic_revision_and_relogin(app):
    doctor=actor(app,'doc_psy');saved=save(doctor,**doctor_fields())
    assert saved.status_code==200,saved.json
    state=saved.json
    assert len(state['education'])==2 and state['certificates'][0]['status']=='self_reported'
    assert state['publications'][0]['doi']=='10.1234/demo.01'
    stale=mutate(doctor,'PUT',BASE,{'revision':state['revision']-1,'display_name':'stale'})
    assert stale.status_code==409
    for change in ({'education':[{'type':'nonsense'}]}, {'publications':[{'title':'bad','doi':'not doi'}]}, {'certificates':[{'title':'bad','issued_at':'2025-22-45'}]}):
        assert save(doctor,display_name='must roll back',**change).status_code==422
        assert doctor.get(BASE).json==state
    assert actor(app,'doc_psy').get(BASE).json==state
    state['education'][0]['institution']='Синтетический университет после правки'
    state['certificates'][0]['title']='Обновлённый синтетический сертификат'
    state['publications'][0]['title']='Обновлённая синтетическая публикация'
    edited=save(doctor,education=state['education'],certificates=state['certificates'],publications=state['publications'])
    assert edited.status_code==200
    state=edited.json
    assert actor(app,'doc_psy').get(BASE).json==state
    assert state['education'][0]['institution'].endswith('после правки')
    assert state['certificates'][0]['title'].startswith('Обновлённый')
    assert state['publications'][0]['title'].startswith('Обновлённая')
    assert save(doctor,education=[state['education'][0]],certificates=[],publications=[]).status_code==200
    reloaded=actor(app,'doc_psy').get(BASE).json
    assert len(reloaded['education'])==1 and not reloaded['certificates'] and not reloaded['publications']
    assert mutate(actor(app,'doc_ther'),'PUT',BASE,{'revision':0,'user_id':'doc_psy','bio':'foreign'}).status_code==422


@pytest.mark.parametrize('data,filename,mime',[(b'', 'empty.png','image/png'),(b'broken','broken.png','image/png'),
    (b'<svg xmlns="http://www.w3.org/2000/svg"/>','photo.svg','image/svg+xml'),
    (png(),'fake.jpg','image/jpeg'),(b'a'*(2*1024*1024+1),'huge.png','image/png'),
    (png(4097,1),'wide.png','image/png'),(png(),'../../outside.png','image/png')], ids=['empty','corrupt','svg','mime-mismatch','byte-limit','axis-limit','traversal'])
def test_photo_rejects_invalid_and_traversal(app,data,filename,mime):
    client=actor(app,'pat_01');before=client.get(BASE).json
    response=upload(client,data,filename,mime)
    assert response.status_code in (413,422),response.json
    assert client.get(BASE).json==before


def test_photo_private_acl_replace_delete_and_revision(app):
    client=actor(app,'pat_01');initial=client.get(BASE).json['revision']
    assert client.post(BASE+'/photo',data={'revision':str(initial),'file':(io.BytesIO(png()),'x.png','image/png')}).status_code==403
    uploaded=upload(client);assert uploaded.status_code==201,uploaded.json
    url=uploaded.json['photo_url'];assert url and client.get(url).status_code==200
    image=client.get(url);assert image.mimetype=='image/png' and image.data.startswith(b'\x89PNG')
    for other in (app.test_client(),actor(app,'pat_02'),actor(app,'doc_psy'),actor(app,'clinic_01')):
        assert other.get(url).status_code in (403,404)
    assert upload(client,revision=initial).status_code==409
    assert mutate(client,'DELETE',BASE+'/photo',{'revision':initial}).status_code==409
    assert actor(app,'pat_01').get(url).status_code==200
    replacement=upload(client);assert replacement.status_code==201
    assert replacement.json['photo_url']!=url and client.get(url).status_code in (403,404)
    assert mutate(client,'DELETE',BASE+'/photo',{'revision':replacement.json['revision']}).status_code==200
    assert not actor(app,'pat_01').get(BASE).json['photo_url']
    assert client.get(replacement.json['photo_url']).status_code in (403,404)


def test_publication_explicit_tenant_approval_whitelist_and_invalidation(app):
    doctor=actor(app,'doc_psy');state=save(doctor,**doctor_fields());assert state.status_code==200,state.json
    uploaded=upload(doctor);assert uploaded.status_code==201
    path='/api/v1/profiles/doc_psy/publication';admin=actor(app,'clinic_01')
    revision=uploaded.json['revision'];photo=uploaded.json['photo_url']
    assert app.test_client().get(photo).status_code in (403,404)
    assert admin.post(path,json={'revision':revision,'confirmation':True}).status_code==403
    assert mutate(doctor,'POST',path,{'revision':revision,'confirmation':True}).status_code==403
    assert mutate(admin,'POST',path,{'revision':revision,'confirmation':False}).status_code==422
    with app.extensions['cc_session_factory'].begin() as db:db.get(User,'clinic_01').organization_id='different-tenant'
    assert mutate(admin,'POST',path,{'revision':revision,'confirmation':True}).status_code in (403,404)
    with app.extensions['cc_session_factory'].begin() as db:db.get(User,'clinic_01').organization_id=db.get(User,'doc_psy').organization_id
    published=mutate(admin,'POST',path,{'revision':revision,'confirmation':True});assert published.status_code==200,published.json
    assert app.test_client().get(photo).status_code==200
    # Published directory serializer must never include private document/contact preference.
    public=app.test_client().get('/api/v1/public/doctors/doc_psy')
    assert public.status_code==200
    assert 'PRIVATE-DEMO-DOCUMENT' not in public.get_data(as_text=True)
    assert 'contact_preference' not in public.get_data(as_text=True)
    assert save(doctor,bio='Изменение требует нового разрешения').status_code==200
    assert app.test_client().get(photo).status_code in (403,404)


def test_profile_migration_disposable_upgrade_downgrade_reupgrade(tmp_path,monkeypatch):
    monkeypatch.delenv('CC_DATABASE_URL',raising=False)
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    path=tmp_path/'migration.sqlite';config.set_main_option('sqlalchemy.url','sqlite:///'+str(path))
    command.upgrade(config,'head')
    from sqlalchemy import create_engine,inspect
    engine=create_engine('sqlite:///'+str(path))
    with engine.begin() as connection:
        before=set(inspect(connection).get_table_names())
        connection.execute(text("INSERT INTO users (id,display_name,role,organization_id) VALUES ('retained','Synthetic','patient','org')"))
    command.downgrade(config,'0014_staff_enrollment')
    command.upgrade(config,'head')
    with engine.connect() as connection:
        assert set(inspect(connection).get_table_names())==before
        assert connection.execute(text("SELECT display_name FROM users WHERE id='retained'")).scalar()=='Synthetic'
        assert not connection.execute(text('PRAGMA foreign_key_check')).all()
    engine.dispose()


def test_profile_parallel_revision_atomicity(app):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    first=actor(app,'doc_psy');cookie=first.get_cookie('session').value
    csrf=first.get('/api/v1/onboarding/bootstrap').json['csrf_token'];revision=first.get(BASE).json['revision']
    barrier=Barrier(2)
    def write(name):
        client=app.test_client();client.set_cookie('session',cookie);barrier.wait()
        response=client.put(BASE,json={'revision':revision,'display_name':name,'education':[
          {'type':'other','institution':name,'year_to':2020}]},headers={'X-CSRF-Token':csrf})
        return response.status_code,name
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(write,['Параллель А','Параллель Б']))
    assert sorted(code for code,_ in results)==[200,409]
    winner=next(name for code,name in results if code==200)
    state=first.get(BASE).json
    assert state['display_name']==winner and state['education'][0]['institution']==winner
    assert state['revision']==revision+1


def test_photo_pixel_bomb_and_attempt_rate(app):
    client=actor(app,'pat_01')
    # Header claims >12 megapixels while each axis remains within 4096.
    data=png();data=data[:16]+struct.pack('!II',4000,4000)+data[24:]
    assert upload(client,data).status_code==422
    for _ in range(19):assert upload(client,b'bad').status_code==422
    assert upload(client,b'bad').status_code==429
    assert not client.get(BASE).json['photo_url']


def test_photo_jpeg_and_metadata_stripping(app,tmp_path):
    import subprocess
    source=tmp_path/'source.png';target=tmp_path/'source.jpg';source.write_bytes(png())
    subprocess.run(['/usr/bin/sips','-s','format','jpeg',str(source),'--out',str(target)],check=True,capture_output=True)
    client=actor(app,'pat_01');uploaded=upload(client,target.read_bytes(),'synthetic.jpg','image/jpeg')
    assert uploaded.status_code==201,uploaded.json
    # Server stores only normalized raster PNG critical chunks, never upload bytes.
    data=client.get(uploaded.json['photo_url']).data;pos=8;kinds=[]
    while pos+12<=len(data):
        size=int.from_bytes(data[pos:pos+4],'big');kinds.append(data[pos+4:pos+8]);pos+=size+12
    assert set(kinds)<=set((b'IHDR',b'PLTE',b'IDAT',b'IEND',b'tRNS'))


def test_publication_requires_optin_and_server_role(app):
    doctor=actor(app,'doc_psy');state=save(doctor,bio='Private doctor')
    assert state.status_code==200
    path='/api/v1/profiles/doc_psy/publication';body={'revision':state.json['revision'],'confirmation':True}
    assert mutate(actor(app,'clinic_01'),'POST',path,body).status_code==409
    for uid in ('pat_01','doc_ther','researcher_01'):
        assert mutate(actor(app,uid),'POST',path,body).status_code==403
    assert doctor.get(BASE).json['publication_status']=='private'


def test_photo_webp_positive_and_png_metadata_removed(app):
    import base64
    client=actor(app,'pat_01')
    # Synthetic single-pixel VP8L image, no human subject or downloaded media.
    webp=base64.b64decode('UklGRh4AAABXRUJQVlA4TBEAAAAvAAAAAAfQ//73v/+BiOh/AAA=')
    assert upload(client,webp,'synthetic.webp','image/webp').status_code==201
    data=png();payload=b'Comment\0SYNTHETIC_PRIVATE_METADATA'
    chunk=struct.pack('!I',len(payload))+b'tEXt'+payload+struct.pack('!I',zlib.crc32(b'tEXt'+payload)&0xffffffff)
    uploaded=upload(client,data[:-12]+chunk+data[-12:])
    assert uploaded.status_code==201
    assert b'SYNTHETIC_PRIVATE_METADATA' not in client.get(uploaded.json['photo_url']).data


def test_profiles_closed_outside_synthetic(app):
    client=actor(app,'pat_01');app.config['APP_ENV']='production'
    assert client.get(BASE).status_code==403
    assert mutate(client,'PUT',BASE,{'revision':0,'display_name':'Synthetic'}).status_code==403


# Existing staff rig models OIDC assurance only for domain concurrency testing;
# full browser callback/authentication is tested separately in run_d07.py.
from test_staff_enrollment import rig as staff_rig


def test_invitation_two_acceptors_race(staff_rig):
    from test_staff_enrollment import invite, candidate, accept
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    invitation=invite(staff_rig[2]());assert invitation.status_code==201
    authenticated=candidate(staff_rig,invitation)
    cookie=authenticated.get_cookie('session').value
    barrier=Barrier(2)
    def run(_):
        client=staff_rig[0].test_client();client.set_cookie('session',cookie)
        barrier.wait();return accept(client,invitation).status_code
    with ThreadPoolExecutor(2) as pool:statuses=list(pool.map(run,range(2)))
    assert sorted(statuses)==[200,409]
    from cc_api.staff_enrollment_models import StaffEnrollmentInvitation
    with staff_rig[1]() as db:
        assert db.get(StaffEnrollmentInvitation,invitation.json['id']).accepted_at
        assert db.get(User,invitation.json['recipient']['id']).role=='doctor'
