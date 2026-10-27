"""Real Chromium recording only. Private auth/raw recordings stay outside deliverables.
Run with cc-m1 and PYTHONPATH=/private/tmp/cc-video-tools/python:backend:.
No app source, ACL, model response, clinical rule or DB direct write is modified.
"""
import os,sys,json,time,csv,subprocess,hashlib,shutil,re,secrets,datetime,traceback
from pathlib import Path
os.environ['CC_E2E_BASE_URL']='http://127.0.0.1:8769'
from playwright.sync_api import sync_playwright,expect
from tests_e2e.test_jury_live import login,show,BASE
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'deliverables/jury_screencast'; PRIVATE=Path('/private/tmp/cc-jury-screencast-20261028'); WS=Path('/private/tmp/clinical-compass-jury-handoff-20261027')
FF='/private/tmp/cc-video-tools/python/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1'; FP='/private/tmp/cc-video-tools/ffprobe'
FONT='/Users/mark/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/fonts/DejaVuSans.ttf'
OUT.mkdir(parents=True,exist_ok=True); (OUT/'chapters').mkdir(exist_ok=True); PRIVATE.mkdir(mode=0o700,exist_ok=True)
STATE=PRIVATE/'state.json'; state=json.loads(STATE.read_text()) if STATE.exists() else {}
actors=json.loads((WS/'jury-actors.json').read_text());actors['patient']=json.loads((WS/'jury-demo-patient.json').read_text())
PID=actors['patient']['patient_id']; DID=actors['doctor']['id']; UID=actors['patient']['id']
LEDGER=OUT/'SCENES.jsonl'; RAW=ROOT/'reports/phase3/raw/screencast-recording-20261028.jsonl';RAW.parent.mkdir(parents=True,exist_ok=True)

def save_private():
 fd=os.open(STATE,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f:json.dump(state,f)
def append(path,item):
 with path.open('a') as f:f.write(json.dumps(item,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
def probe(path):return json.loads(subprocess.check_output([FP,'-v','error','-show_format','-show_streams','-of','json',str(path)]))
def duration(path):return float(probe(path)['format']['duration'])
def stamp(s):
 s=int(s);return f'{s//60:02d}:{s%60:02d}'
def caption(path,title,desc,status):
 status={'LIVE_VERIFIED':'Работает в учебной среде','DEMO_WITH_LIMITATION':'Экспериментальный / частичный прототип','PLANNED':'Планируется'}.get(status,status)
 im=Image.new('RGB',(1920,90),'#101e2b');d=ImageDraw.Draw(im)
 d.text((28,6),title+' · '+status,font=ImageFont.truetype(FONT,25),fill='#7ee6ce')
 # Limit each line to the frame. Long detailed claims stay in report.
 while d.textlength(desc,font=ImageFont.truetype(FONT,24))>1860:desc=desc[:-5]+'…'
 d.text((28,45),desc,font=ImageFont.truetype(FONT,24),fill='white');im.save(path)
def encode(raw,target,title,desc,status,masks=()):
 cap=PRIVATE/(target.stem+'-caption.png');caption(cap,title,desc,status)
 filters='[0:v]fps=30,scale=1584:990,pad=1920:1080:168:0:color=0x101e2b[v];[v][1:v]overlay=0:990'
 if masks:
  filters='[0:v]'+','.join(f'drawbox=x={int(x)}:y={int(y)}:w={int(w)}:h={int(h)}:color=0x142a3e:t=fill' for x,y,w,h in masks)+',fps=30,scale=1584:990,pad=1920:1080:168:0:color=0x101e2b[v];[v][1:v]overlay=0:990'
 cmd=[FF,'-y','-hide_banner','-loglevel','error','-i',str(raw),'-i',str(cap),'-filter_complex',filters,'-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-an','-movflags','+faststart',str(target)]
 subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=open(PRIVATE/'encode.log','a'))

def records():return [json.loads(x) for x in LEDGER.read_text().splitlines()] if LEDGER.exists() else []
def checkpoint(message):
 extra=f'\n\n## Screencast 2026-10-28 — {message}\nBaseline 080e9a8, existing native8769/Docker8768 retained. Real Chromium recordings; metadata deliverables/jury_screencast/SCENES.jsonl; append-only raw reports/phase3/raw/screencast-recording-20261028.jsonl. Private raw/auth /private/tmp/cc-jury-screencast-20261028 (never distribute). Resume: PYTHONPATH=/private/tmp/cc-video-tools/python:backend:. /Users/mark/miniforge3/envs/cc-m1/bin/python scripts/record_jury_screencast.py <chapter|assemble>. No push/Drive upload. Subagents still1/4.\n'
 for name in ['.agent/CHECKPOINT.md','.agent/EXECPLAN_ACTIVE.md']:
  p=ROOT/name;txt=p.read_text(); marker='\n\n## Screencast 2026-10-28';txt=txt.split(marker)[0];p.write_text(txt+extra)
 update_docs()
def update_docs():
 rs=records(); lines=['# Запись для жюри — промежуточный отчёт','', 'Реальные Chromium/Flask/SQLite, native 8769, исходный HEAD 080e9a8. Отдельные контексты ролей. 1440×900, zoom100%; монтаж 1920×1080 с сохранением пропорций, H.264/30fps, русские титры, без звука/музыки. Пароли скрыты штатным полем; приглашения закрыты при монтаже. Сырые видео и авторизация только в приватной локальной папке.','']
 for r in rs:lines.append(f"- {r['id']}: {r['result']}, {r['seconds']:.2f}s, `{r['file']}` — {r['description']}")
 (OUT/'RECORDING_REPORT.md').write_text('\n'.join(lines)+'\n')
 storyboard=['# Сцены: фактические действия и результаты','', 'Предусловия: существующий частный synthetic sandbox, действительные обычные сессии/согласия. Видео не доказывает все1883 действия.','']
 for r in rs:storyboard.append(f"## {r['id']}\nРоль: {r['role']}. Вопрос/действие: {r['description']}\nСтатус: {r['status']}. Факт: {r['result']}. Файл: {r['file']}. Длительность: {r['seconds']:.2f}s. Источник: реальная запись Chromium; SCENES.jsonl.\n")
 (OUT/'STORYBOARD.md').write_text('\n'.join(storyboard))
 routes=json.loads((ROOT/'frontend/dist/assets/data/routes.json').read_text());fields=['role','scenario_id','route','action','implementation_status','verification_status','video_file','start_time','end_time','evidence','limitations'];rows=[]
 # One row per original route, plus actual scene intervals below. No fabricated coverage.
 for route in routes:
  match=next(((r,e) for r in rs for e in r['events'] if e['route']==route['path']),None)
  if match:
   r,e=match;rows.append([route['role'],r['id'],route['path'],route['action'],r['status'],r['result'],r['file'],stamp(e['start']),stamp(e['end']),'SCENES.jsonl','Интервал отдельного исходного MP4; основной монтаж имеет отдельные строки'])
  else:rows.append([route['role'],'route_inventory',route['path'],route['action'],'NOT_CAPTURED','NOT_CAPTURED','','','','frontend/dist/assets/data/routes.json; reports/phase2/FEATURE_PARITY.csv','Не снимался: ограниченный монтаж; прежние тесты не выдаются за видео. Условные/grant/OIDC маршруты сохраняют ограничения.'])
 for r in rs:
  for e in r['events']:rows.append([r['role'],r['id'],e['route'],e['action'],r['status'],r['result'],r['file'],stamp(e['start']),stamp(e['end']),'SCENES.jsonl',r.get('limitations','')])
 with (OUT/'VIDEO_INDEX.csv').open('w') as f:w=csv.writer(f);w.writerow(fields);w.writerows(rows)

CURSOR="""(()=>{document.addEventListener('DOMContentLoaded',()=>{const e=document.createElement('div');e.id='recording-pointer';e.style.cssText='position:fixed;z-index:2147483647;width:18px;height:18px;border:3px solid #ef8b22;border-radius:50%;pointer-events:none;left:-40px;top:-40px;box-shadow:0 0 0 2px white;';document.body.appendChild(e);document.addEventListener('mousemove',v=>{e.style.left=(v.clientX-9)+'px';e.style.top=(v.clientY-9)+'px'});});})();"""
class Scene:
 def __init__(self,b,id,role,title,description,status='LIVE_VERIFIED',account=None):self.b=b;self.id=id;self.role=role;self.title=title;self.description=description;self.status=status;self.events=[];self.masks=[];self.account=account or role
 def __enter__(self):
  storage=PRIVATE/(self.account+'-storage.json');args={'viewport':{'width':1440,'height':900},'record_video_dir':str(PRIVATE/'raw'),'record_video_size':{'width':1440,'height':900},'locale':'ru-RU','device_scale_factor':1,'accept_downloads':True}
  if storage.exists():args['storage_state']=str(storage)
  self.c=self.b.new_context(**args);self.c.add_init_script(CURSOR);self.t=time.monotonic();self.p=self.c.new_page();self.p.set_default_timeout(15000);self.video=self.p.video;self.current=None;return self
 def route(self,path,key=None,action=None):
  self.end_event();show(self.p,path);self.current={'route':key or path,'action':action or self.description,'start':round(time.monotonic()-self.t,2)};self.pause(2)
 def end_event(self):
  if self.current:self.current['end']=round(time.monotonic()-self.t,2);self.events.append(self.current);self.current=None
 def pause(self,n=2):self.p.wait_for_timeout(int(n*1000))
 def focus(self,loc):
  loc.scroll_into_view_if_needed();self.p.evaluate('window.scrollBy({top:-100,behavior:"instant"})');self.pause(.6)
 def fill(self,form,values):
  for key,val in values.items():form.locator('[name='+key+']').fill(val);self.pause(.25)
 def submit(self,form,ends,status=201,method='POST'):
  button=form.locator('button[type=submit],button.btn-primary').first
  if button.count()==0:button=form.locator('button').first
  self.focus(button)
  with self.p.expect_response(lambda r:r.url.endswith(ends) and r.request.method==method,timeout=65000) as x:button.click()
  assert x.value.status==status,(ends,x.value.status);self.pause(2);return x.value.json()
 def __exit__(self,typ,error,tb):
  self.end_event();self.c.storage_state(path=str(PRIVATE/(self.account+'-storage.json')));os.chmod(PRIVATE/(self.account+'-storage.json'),0o600);self.c.close();raw=Path(self.video.path());target=OUT/'chapters'/(self.id+'.mp4');result='PASS' if not error else 'FAIL'
  if target.exists():
   archive=PRIVATE/'previous-mp4';archive.mkdir(exist_ok=True);shutil.copy2(target,archive/(self.id+'-'+str(time.time_ns())+'.mp4'))
  encode(raw,target,self.title,self.description,self.status,self.masks)
  r={'id':self.id,'role':self.role,'description':self.description,'status':self.status,'result':result,'file':str(target.relative_to(OUT)),'seconds':duration(target),'events':self.events,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'raw_file':raw.name,'masks':self.masks}
  append(LEDGER,r);append(RAW,{**r,'n':1,'method':'real Chromium record_video_dir; Flask+SQLite'});save_private();checkpoint(self.id+' '+result);print(self.id,result,round(r['seconds'],1),flush=True)
  if error:print('Recording action failed:',type(error).__name__,flush=True)
  return False

def prepare(b):
 for role,actor in actors.items():
  file=PRIVATE/(role+'-storage.json')
  if file.exists():continue
  c=b.new_context();p=c.new_page();login(p,actor['email'],actor['password']);expect(p).not_to_have_url(BASE+'/#/login');c.storage_state(path=str(file));os.chmod(file,0o600);c.close()
 state.setdefault('new_email','video-'+secrets.token_hex(4)+'@evaluation.test');state.setdefault('new_password',secrets.token_urlsafe(24));save_private()

# Each function persists a usable chapter immediately. Later editing keeps raw files.
def catalog(b):
 with Scene(b,'06_catalog_and_assessments','shared','Справочник и шкалы','Как проверить источник? Полные разделы и связи; шкалы — неутверждённые учебные версии.') as s:
  s.route('/clinical-library?type=medicine','/clinical-library');p=s.p
  # Open a genuine original source instruction; all data is served by catalog API.
  a=p.locator('a[href*="item="]').first;s.focus(a);a.click();s.pause(3)
  detail=p.locator('#catalog-detail');s.focus(detail);s.pause(3)
  for _ in range(3):p.mouse.wheel(0,530);s.pause(2)
  s.route('/clinical-library?type=diagnosis','/clinical-library');s.pause(2)
  s.route('/clinical-library?type=therapy','/clinical-library');s.pause(2)
  s.route('/assessments','/assessments');s.pause(3)
  for code in ('phq_2','gad_7','gad_2'):
   s.route('/assessments/'+code,'/assessments/:code');f=p.locator('[data-form=guest-questionnaire]');f.locator('fieldset').first.locator('input[value="1"]').check();s.pause(2)

def guest(b):
 # Invitation is created before the new patient's registration. All secrets masked in output.
 with Scene(b,'00a_invitation','doctor','Приглашение нового пациента','Врач задаёт категории. Ссылка, ключ и QR закрыты; связь требует отдельного согласия.') as s:
  s.route('/doctor/invitations');f=s.p.locator('[data-form=create-invitation]');s.fill(f,{'recipient_email':state['new_email']})
  for x in f.locator('[name=category]').all():x.check()
  state['invite']=s.submit(f,'/onboarding/invitations');s.p.locator('#created-invitation').scroll_into_view_if_needed();s.pause(3)
  # Hide all possible positions of the invitation secret block in the entire clip.
  # Entire lower 2/3 remains masked; header/form interaction and outcome title remain identifiable.
  s.masks=[(0,390,1440,510)];save_private()
 with Scene(b,'00b_guest_registration','new_patient','Гость → новый пациент','PHQ-9: сумма 9 без интерпретации. Регистрация → серверное сохранение → повторное открытие.',account='new_patient') as s:
  s.route('/');s.pause(3);s.route('/demo/journeys');s.pause(3);s.route('/assessments/phq_9','/assessments/:code');p=s.p;f=p.locator('[data-form=guest-questionnaire]')
  for field in f.locator('fieldset').all():s.focus(field);field.locator('input[value="1"]').check();s.pause(.6)
  s.focus(f.locator('button[type=submit]'));f.locator('button[type=submit]').click();s.pause(4)
  s.end_event();s.current={'route':'/assessments/:code/result','action':'Механический результат, ещё не сохранён','start':round(time.monotonic()-s.t,2)}
  p.get_by_role('link',name='Зарегистрироваться и сохранить',exact=True).click();s.pause(2)
  s.end_event();s.current={'route':'/register/patient','action':'Настоящая регистрация с продолжением сохранения','start':round(time.monotonic()-s.t,2)}
  p.locator('#reg-name').fill('Новый Вымышленный Пациент');p.locator('#reg-email').fill(state['new_email']);p.locator('[data-command=next-registration]').click();s.pause(1)
  p.locator('#reg-pass').fill(state['new_password']);p.locator('#reg-pass2').fill(state['new_password']);p.locator('[name=terms_consent]').check()
  with p.expect_response(lambda r:r.url.endswith('/onboarding/register') and r.request.method=='POST') as created:p.get_by_role('button',name='Создать аккаунт',exact=True).click()
  assert created.value.status==201;state['new_user']=created.value.json()['user'];save_private();expect(p).to_have_url(re.compile(r'/#/patient/questionnaires/dq_[^/]+/result$'));s.pause(4);p.reload();s.pause(3)
  s.end_event();s.current={'route':'/patient/questionnaires/:requestId/result','action':'Сохранённый результат после reload','start':round(time.monotonic()-s.t,2)};s.pause(3)
  s.route('/patient/tasks');s.pause(3)
 with Scene(b,'00c_invite_consent','new_patient','Новый пациент: явное согласие','Проверка приглашения и объёма доступа. Только после согласия появляется действительная связь.',account='new_patient') as s:
  s.route(state['invite']['url'],'/invite/:token');p=s.p
  # Token input position is stable at this viewport; opaque mask is applied in final encode.
  box=p.locator('#invite-token').bounding_box();s.masks=[(int(box['x'])-2,int(box['y'])-2,int(box['width'])+4,int(box['height'])+4)]
  p.locator('[data-form=invite-preview] button').click();s.pause(4);f=p.locator('[data-form=invite-accept]');s.focus(f);f.locator('[name=consent]').check();s.submit(f,'/invitations/accept',200)
  s.route('/patient/access');s.pause(4)
 with Scene(b,'00d_doctor_new_link','doctor','Врач: связь подтверждена','Новый пациент появился после регистрации и явного согласия, а не после создания QR.') as s:
  s.route('/doctor/patients');s.pause(4)
 combine_chapter('00_guest_new_patient',['00b_guest_registration','00a_invitation','00c_invite_consent','00d_doctor_new_link'],180)

def patient(b):
 with Scene(b,'01a_existing_today','patient','Существующий пациент · Сегодня','Обычный вход; самочувствие сохраняется сервером. Динамика — наблюдения, без автоматического диагноза.') as s:
  # Show real login action without password reveal. No cookies/network panel is recorded.
  s.route('/login');p=s.p;p.locator('#login-email').fill(actors['patient']['email']);p.locator('#login-pass').fill(actors['patient']['password']);s.pause(1);p.locator('form[data-form=login] button').click();s.pause(3)
  s.route('/patient');f=p.locator('[data-form=checkin]');f.locator('input[value="3"]').check();f.locator('[name=comparison]').select_option('same');s.fill(f,{'note':'Вымышленная запись для жюри: сегодня отмечаю самочувствие.'});s.submit(f,'/check-ins');p.mouse.wheel(0,600);s.pause(3)
  s.route('/patient/trends');s.pause(4)
 with Scene(b,'01b_existing_questionnaires','patient','Опросники: сохранение и история','GAD-2: два ответа по 1 → сумма 2. PHQ/GAD — неутверждённые русские учебные формы.') as s:
  s.route('/patient/tasks');p=s.p;p.locator('[data-command=start-assessment][data-id=eval_gad_2_v1]').click();s.pause(2);f=p.locator('[data-form=questionnaire]')
  for field in f.locator('fieldset').all():s.focus(field);field.locator('input[value="1"]').check();s.pause(1)
  s.focus(f.get_by_role('button',name='Отправить ответы',exact=True));f.get_by_role('button',name='Отправить ответы',exact=True).click();s.pause(4);p.reload();s.pause(3)
  s.end_event();s.current={'route':'/patient/questionnaires/:requestId/result','action':'Сумма 2 и серверная история после reload','start':round(time.monotonic()-s.t,2)};s.pause(3)
  s.route('/patient/tasks');s.pause(2)
 with Scene(b,'01c_existing_plan_message','patient','Пациент: план и сообщение врачу','Вижу опубликованные авторские поля. Пишу связанному врачу; ответ появится в этой же переписке.') as s:
  s.route('/patient/treatment');s.pause(4);s.p.mouse.wheel(0,400);s.pause(2)
  s.route('/patient/messages/'+DID,'/patient/messages/:threadId');f=s.p.locator('[data-form=clinical-message]');s.fill(f,{'text':'Вымышленное сообщение для жюри: вижу план и готов отметить выполнение.'});s.submit(f,'/messages');s.pause(3)
  s.route('/patient/profile');s.pause(3)
  # Synthetic geometric PNG, no real person's image or secret filesystem picker captured.
  im=Image.new('RGB',(160,160),'#d5f3ed');d=ImageDraw.Draw(im);d.ellipse((35,35,125,125),fill='#147c72');photo=PRIVATE/'synthetic-avatar.png';im.save(photo)
  f=s.p.locator('[data-form=photo]');s.focus(f);f.locator('[name=photo]').set_input_files(str(photo));s.submit(f,'/photo',201);s.p.reload();s.pause(3)
 combine_chapter('01_existing_patient',['01a_existing_today','01b_existing_questionnaires','01c_existing_plan_message'],300)

def combine_chapter(name,ids,limit):
 files=[OUT/'chapters'/(x+'.mp4') for x in ids];target=OUT/'chapters'/(name+'.mp4');concat(files,target)
 assert duration(target)<=limit,(name,duration(target));checkpoint(name+' assembled PASS')
 print('CHAPTER',name,round(duration(target),1),flush=True)
def concat(files,target):
 text=PRIVATE/(target.stem+'-concat.txt');text.write_text('\n'.join("file '"+str(f)+"'" for f in files))
 subprocess.run([FF,'-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(text),'-c','copy','-movflags','+faststart',str(target)],check=True)

def doctor(b):
 done={r['id'] for r in records() if r['result']=='PASS'}
 if '02a_doctor_overview' not in done:
  with Scene(b,'02a_doctor_overview','doctor','Врач: активный пациент','Что уже известно? Анамнез, динамика, результаты шкал и история — только в рамках согласий.') as s:
   s.route('/doctor');s.pause(2);s.route('/doctor/patients/'+PID,'/doctor/patients/:patientId');s.pause(3)
   s.route('/doctor/patients/'+PID+'/history','/doctor/patients/:patientId/history');s.pause(3)
   s.route('/doctor/patients/'+PID+'/trends','/doctor/patients/:patientId/trends');s.pause(3)
   s.route('/doctor/questionnaires');s.pause(3)
 if '02b_visit_lifecycle' not in done:
  with Scene(b,'02b_visit_lifecycle','doctor','Врач: настоящий приём','Создаю и редактирую черновик. Подпись и публикация — разные явные действия врача.') as s:
   s.route('/doctor/patients/'+PID+'/visits','/doctor/patients/:patientId/visits');p=s.p;f=p.locator('[data-form=create-encounter]')
   if state.get('visit_doc'):
    doc=p.request.get(BASE+'/api/v1/clinical-workflow/documents/'+state['visit_doc']).json()
   else:
    s.fill(f,{'narrative':'Учебный приём для жюри. Пациент описывает нарушение сна; требуется самостоятельная оценка врача.'});f.locator('[name=confirmed]').check();doc=s.submit(f,'/documents');state['visit_doc']=doc['id'];save_private()
   f=p.locator('[data-form=edit-clinical-document][data-id="'+doc['id']+'"]');f.locator('xpath=..').locator('summary').click();s.focus(f)
   s.fill(f,{'narrative':'Учебный приём: врач лично уточнил жалобы и отредактировал запись. Не медицинское заключение.','assessment':'Вымышленные данные; клиническая оценка требует полноценного осмотра.','follow_up':'Учебное продолжение наблюдений.'});f.locator('[name=confirmed]').check();s.submit(f,'/documents/'+doc['id'],200,'PUT')
   for action in ('sign','publish'):
    button=p.locator('[data-command='+action+'-document][data-id="'+doc['id']+'"]');s.focus(button);s.pause(2);p.once('dialog',lambda x:x.accept())
    with p.expect_response(lambda r:r.url.endswith('/'+action) and r.request.method=='POST') as changed:button.click()
    assert changed.value.ok;s.pause(3)
 if '02c_plan_lifecycle' not in done:
  with Scene(b,'02c_plan_lifecycle','doctor','Врач: авторское учебное назначение','Авиандр — только введённое врачом учебное название. Доза не подбирается. Отдельно подписываю и публикую.') as s:
   s.route('/doctor/patients/'+PID+'/treatment','/doctor/patients/:patientId/treatment');p=s.p;f=p.locator('[data-form=create-treatment]')
   s.fill(f,{'title':'Авиандр — учебная запись, не применять','dose':'Доза не задана: учебная демонстрация','frequency':'Учебная периодичность без лечебной схемы','route':'Не для применения','duration':'Период демонстрации','notes':'Ввод врача вручную. Не рекомендация и не назначение для реального пациента.'});f.locator('[name=confirmed]').check();doc=s.submit(f,'/documents');state['video_plan']=doc['id'];save_private()
   for action in ('sign','publish'):
    button=p.locator('[data-command='+action+'-document][data-id="'+doc['id']+'"]');s.focus(button);p.once('dialog',lambda x:x.accept())
    with p.expect_response(lambda r:r.url.endswith('/'+action) and r.request.method=='POST') as changed:button.click()
    assert changed.value.ok;s.pause(3)
 if '02d_patient_receives' not in done:
  with Scene(b,'02d_patient_receives','patient','Пациент: опубликованный план появился','После публикации вижу авторские поля. Отмечаю выполнение; это самоотчёт, а не календарь пропущенных доз.') as s:
   s.route('/patient/treatment');p=s.p;loc=p.get_by_text('Авиандр — учебная запись, не применять',exact=False).first;s.focus(loc);s.pause(4)
   s.route('/patient');button=p.locator('[data-command=report-plan]').first;s.focus(button);button.click();s.pause(2)
   with p.expect_response(lambda r:'/plan-items/' in r.url and r.url.endswith('/report') and r.request.method=='POST') as sent:p.locator('[data-command=report-outcome][data-outcome=completed]').click()
   assert sent.value.status==201;s.pause(3);p.reload();s.pause(2)
 if '02e_behavioral' not in done:
  with Scene(b,'02e_behavioral','doctor','Врач: поведенческий план','Дневник наблюдений: поля вводит врач. Черновик не опубликован пациенту автоматически.') as s:
   s.route('/doctor/patients/'+PID+'/psychotherapy','/doctor/patients/:patientId/psychotherapy');f=s.p.locator('[data-form=create-treatment]');s.fill(f,{'title':'Учебный дневник наблюдений','frequency':'Фиксировать наблюдения по согласованию с врачом','duration':'Период демонстрации','notes':'Учебный пример; не схема лечения.'});f.locator('[name=confirmed]').check();s.submit(f,'/documents');s.pause(3)
 if '02f_patient_intake' not in done:
  with Scene(b,'02f_patient_intake','patient','Пациент: исходный текст для врача','Отправляю вымышленное обращение с отдельным согласием. Qwen будет работать с этим источником.') as s:
   s.route('/patient/requests/new');p=s.p;f=p.locator('[data-form=new-request]');f.locator('[name=doctor_id]').select_option(DID);s.fill(f,{'text':'Вымышленный пациент: плохо сплю. Тревожусь из-за работы.'});f.locator('[name=case_consent]').check();case=s.submit(f,'/previsit-cases');state['video_case']=case['id'];save_private();s.pause(3)
 # Benign real one-token warmup, never presented as the clinical analysis.
 subprocess.run([sys.executable,str(ROOT/'docker/warm_native_model.py')],stdout=open(PRIVATE/'warmup.log','a'),stderr=subprocess.STDOUT,check=True)
 if '02g_qwen_nlp' not in done:
  with Scene(b,'02g_qwen_nlp','doctor','Clinical Intelligence · настоящий Qwen','Экспериментальный прототип: реальный запрос, точные цитаты и ручной выбор врача. Ожидание сохранено.',status='DEMO_WITH_LIMITATION') as s:
   s.route('/doctor/patients/'+PID+'/clinical-intelligence?case='+state['video_case'],'/doctor/patients/:patientId/clinical-intelligence');p=s.p;button=p.locator('[data-command=ci-analyze]');s.focus(button);t=time.monotonic()
   with p.expect_response(lambda r:'/snapshot?' in r.url and r.request.method=='POST',timeout=65000) as analyzed:button.click()
   elapsed=time.monotonic()-t;data=analyzed.value.json();assert analyzed.value.ok and data['mode']=='local_llm' and data['analysis_status']=='ready'
   state['nlp_seconds']=elapsed;save_private();append(OUT/'AI_TIMINGS.jsonl',{'action':'fresh_real_nlp','seconds':elapsed,'mode':data['mode'],'model':data.get('model_version'),'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat()})
   button=p.locator('[data-command=ci-review]').first;s.focus(button);s.pause(4)
   with p.expect_response(lambda r:'/reviews' in r.url and r.request.method=='POST') as reviewed:button.click()
   assert reviewed.value.ok;s.pause(3)
   f=p.locator('[data-form=ci-document]');s.focus(f);s.fill(f,{'narrative':'Учебный черновик. Врач проверил точные цитаты и самостоятельно отредактировал текст.'});f.locator('[name=confirmed]').check();s.submit(f,'/documents');s.pause(2)
   f=p.locator('[data-form=ci-referral]');s.focus(f);s.fill(f,{'clinical_reason':'Учебное самостоятельное решение врача после просмотра исходного обращения.'});f.locator('[name=confirmed]').check()
   with p.expect_response(lambda r:'/referrals?' in r.url and r.request.method=='POST') as referred:f.locator('button').click()
   assert referred.value.status==201;s.pause(3)
   button=p.locator('[data-command=ci-create-thread]');s.focus(button)
   with p.expect_response(lambda r:r.url.endswith('/threads') and r.request.method=='POST') as made:button.click()
   assert made.value.status==201;state['video_thread']=made.value.json()['id'];save_private();s.pause(2)
 if '02h_qwen_chat' not in done:
  with Scene(b,'02h_qwen_chat','doctor','Врачебный AI-чат · Qwen локально','Отправляю новый справочный вопрос; показываю действительный ответ и источники. Не автономное назначение.',status='DEMO_WITH_LIMITATION') as s:
   s.route('/doctor/patients/'+PID+'/clinical-intelligence/chat/'+state['video_thread'],'/doctor/patients/:patientId/clinical-intelligence/chat/:threadId');p=s.p;f=p.locator('[data-form=ci-message]');s.fill(f,{'content':'Какие справочные материалы о сне есть в выбранной записи?'});t=time.monotonic();s.submit(f,'/messages',202)
   deadline=time.monotonic()+100
   while True:
    data=p.request.get(BASE+'/api/v1/clinical-intelligence/threads/'+state['video_thread']).json();job=data['jobs'][-1]
    if job['status'] not in ('queued','running'):break
    assert time.monotonic()<deadline;s.pause(1)
   assert job['status']=='completed';assistant=[m for m in data['messages'] if m['role']=='assistant'][-1];assert assistant['mode']=='local_llm' and assistant['model']=='qwen3:4b-instruct'
   state['chat_seconds']=time.monotonic()-t;save_private();append(OUT/'AI_TIMINGS.jsonl',{'action':'fresh_real_doctor_chat','seconds':state['chat_seconds'],'mode':assistant['mode'],'model':assistant['model'],'timings':job['timings']})
   p.get_by_role('button',name='Обновить ответы').click();s.pause(3);p.mouse.wheel(0,520);s.pause(5)
 if '02i_signals_message' not in done:
  with Scene(b,'02i_signals_message','doctor','Врач: сигнал и ответ пациенту','Реальное правило по наблюдениям: врач сохраняет оценку. Затем отвечает на сообщение пациента.') as s:
   s.route('/doctor/alerts');p=s.p;items=p.request.get(BASE+'/api/v1/doctor-experience/signals').json()['items'];signal=next(x for x in items if x['source']=='wellbeing_observation')
   s.route('/doctor/alerts/'+signal['id'],'/doctor/alerts/:alertId');f=p.locator('[data-form=signal-review]');s.fill(f,{'assessment':'Учебная врачебная оценка: проверены исходные наблюдения. Автоматический клинический риск не установлен.'});f.locator('[name=status]').select_option('acknowledged');s.submit(f,'/review',200);p.reload();s.pause(3)
   s.route('/doctor/messages/'+UID,'/doctor/messages/:threadId');f=p.locator('[data-form=clinical-message]');s.fill(f,{'text':'Учебный ответ врача для жюри: сообщение получено, опубликованный план доступен.'});s.submit(f,'/messages');s.pause(3)
 if '02j_patient_answer' not in done:
  with Scene(b,'02j_patient_answer','patient','Пациент: ответ получен','Перезагрузка переписки показывает фактический ответ того же связанного врача.') as s:
   s.route('/patient/messages/'+DID,'/patient/messages/:threadId');expect(s.p.locator('#main')).to_contain_text('Учебный ответ врача для жюри');s.pause(5)
 combine_chapter('02_doctor',['02a_doctor_overview','02b_visit_lifecycle','02c_plan_lifecycle','02d_patient_receives','02e_behavioral','02f_patient_intake','02g_qwen_nlp','02h_qwen_chat','02i_signals_message','02j_patient_answer'],360)

def admin(b):
 with Scene(b,'03a_admin_hidden','clinic_admin','Администратор клиники: отдельная роль','Сотрудники с ФИО; клинические данные закрыты. ФИО пациента скрыто без отдельного разрешения.') as s:
  s.route('/clinic/staff');s.pause(4);s.route('/clinic/appointments');s.pause(3);s.route('/clinic/patients');s.pause(4)
 with Scene(b,'03b_patient_name_optin','patient','Пациент: отдельное согласие на ФИО','Сохранение имени ещё не раскрывает его. Явно разрешаю только перечисленные поля внутри своей клиники.') as s:
  s.route('/patient/admin-identity');p=s.p;f=p.locator('[data-form=admin-identity-values]');s.fill(f,{'first_name':'Учебный','last_name':'Вымышленный','middle_name':'Примерович'});s.submit(f,'/me/values',200,'PUT')
  f=p.locator('[data-form=admin-identity-consent]');s.focus(f);f.locator('[name=confirmed]').check()
  with p.expect_response(lambda r:'/me/policies/' in r.url and r.request.method=='PUT') as granted:f.locator('button').click()
  assert granted.value.ok;s.pause(3)
 with Scene(b,'03c_admin_name_visible','clinic_admin','Клиника: имя теперь разрешено','ФИО видно только после отдельного согласия. Диагнозы и личный дневник сюда не передаются.') as s:
  s.route('/clinic/patients');expect(s.p.locator('#main')).to_contain_text('Вымышленный Учебный Примерович');s.pause(5)
 with Scene(b,'03d_patient_revoke_name','patient','Пациент: отзыв разрешения','Отзываю отдельное разрешение на ФИО; клиническая связь с врачом сохраняется.') as s:
  s.route('/patient/admin-identity');p=s.p;p.once('dialog',lambda d:d.accept())
  with p.expect_response(lambda r:'/me/policies/' in r.url and r.request.method=='DELETE') as revoked:p.locator('[data-command=admin-identity-revoke]').click()
  assert revoked.value.ok;s.pause(4)
 with Scene(b,'03e_admin_revoked','clinic_admin','Клиника: отзыв действительно применён','Повторный запрос: ФИО больше нет. OIDC/MFA и часть организационных операций требуют развития.',status='DEMO_WITH_LIMITATION') as s:
  s.route('/clinic/patients');expect(s.p.locator('#main')).not_to_contain_text('Вымышленный Учебный Примерович');s.pause(5)
 combine_chapter('03_clinic_admin',['03a_admin_hidden','03b_patient_name_optin','03c_admin_name_visible','03d_patient_revoke_name','03e_admin_revoked'],180)

def research(b):
 with Scene(b,'04_researcher','researcher','Исследователь: синтетический набор','Как получено среднее? Реальные A/B-запросы, пропуски и методика. График в этом потоке пока отсутствует.',status='DEMO_WITH_LIMITATION') as s:
  s.route('/research');s.pause(2);s.route('/research/demo-v3');p=s.p;s.pause(4)
  for cohort in ('A','B'):
   f=p.locator('[data-form=research-synthetic-filter]');s.focus(f);p.locator('#research-cohort').select_option(cohort);p.get_by_role('button',name='Рассчитать',exact=True).click();s.pause(3);p.mouse.wheel(0,420);s.pause(4)
  s.focus(p.get_by_role('link',name='Скачать CSV всех агрегатов'))
  with p.expect_download() as dl:p.get_by_role('link',name='Скачать CSV всех агрегатов').click()
  path=OUT/'synthetic_research_aggregate.csv';dl.value.save_as(str(path));s.pause(2)
  # Chromium's real downloaded plain-text file, never an invented table.
  s.end_event();p.goto(path.as_uri());s.current={'route':'download:synthetic_research_aggregate.csv','action':'Открыт реально выгруженный CSV без строк пациентов','start':round(time.monotonic()-s.t,2)};s.pause(6)
 checkpoint('04_researcher ready PASS')

def roadmap(b):
 with Scene(b,'05_experimental_and_roadmap','shared','Что уже работает — что требует развития','Работают: формы, согласия, публикация, переписка и синтетические агрегаты. AI остаётся экспериментальным.',status='DEMO_WITH_LIMITATION') as s:
  s.route('/demo/journeys');s.pause(6);s.p.mouse.wheel(0,600);s.pause(6);s.p.mouse.wheel(0,500);s.pause(6)
 checkpoint('05_experimental_and_roadmap ready PASS')

def patient_finish(b):
 done={r['id'] for r in records() if r['result']=='PASS'}
 recover_new_user(b)
 if '01d_profile_photo' not in done:
  with Scene(b,'01d_profile_photo','patient','Профиль: синтетический аватар','Загружаю геометрический PNG; сервер проверяет формат. После перезагрузки фото остаётся.') as s:
   s.route('/patient/profile');p=s.p;f=p.locator('[data-form=photo]');s.focus(f);f.locator('[name=photo]').set_input_files(str(PRIVATE/'synthetic-avatar.png'))
   s.submit(f,'/photo',201);p.reload();s.pause(4);assert p.locator('img[src*="photo"]').count()>0
 # Add a second doctor with a narrower scope through ordinary UI, no backend grants.
 if not state.get('second_linked'):
  second=json.loads((WS/'jury-second-doctor.json').read_text());c=b.new_context();p=c.new_page();login(p,second['email'],second['password']);expect(p).to_have_url(BASE+'/#/doctor');show(p,'/doctor/invitations');f=p.locator('[data-form=create-invitation]');f.locator('[name=recipient_email]').fill(state['new_email']);f.locator('[name=category][value=symptoms]').check()
  with p.expect_response(lambda r:r.url.endswith('/invitations') and r.request.method=='POST') as made:f.locator('button').click()
  assert made.value.status==201;inv=made.value.json();c.close()
  c=b.new_context(storage_state=str(PRIVATE/'new_patient-storage.json'));p=c.new_page();show(p,inv['url']);p.locator('[data-form=invite-preview] button').click();f=p.locator('[data-form=invite-accept]');f.locator('[name=consent]').check()
  with p.expect_response(lambda r:r.url.endswith('/invitations/accept') and r.request.method=='POST') as accepted:f.locator('button').first.click()
  assert accepted.value.ok;c.storage_state(path=str(PRIVATE/'new_patient-storage.json'));c.close();state['second_linked']=True;save_private()
 if '01e_access_revoke' not in done:
  with Scene(b,'01e_access_revoke','new_patient','Новый пациент: разные объёмы доступа','У двух врачей разные категории. Отзываю широкую связь; узкое разрешение другого врача остаётся.',account='new_patient') as s:
   s.route('/patient/access');s.pause(4);p=s.p;button=p.locator('[data-command=revoke-doctor-link][data-id="'+DID+'"]');s.focus(button);p.once('dialog',lambda d:d.accept())
   with p.expect_response(lambda r:'/clinical-links/' in r.url and r.request.method=='DELETE') as revoked:button.click()
   assert revoked.value.ok;s.pause(4);p.reload();s.pause(3)
 if '01f_doctor_access_denied' not in done:
  with Scene(b,'01f_doctor_access_denied','doctor','Врач: отзыв доступа сработал','Новый запрос к карточке нового пациента после отзыва связи: данные больше не доступны.') as s:
   s.route('/doctor/patients/'+state['new_user']['patient_id'],'/doctor/patients/:patientId');s.pause(5)
   assert s.p.request.get(BASE+'/api/v1/clinical-workflow/patients/'+state['new_user']['patient_id']+'/documents').status==404
 # Completed plan/message steps from first attempt are retained; trim only the recording-selector wait.
 r=next(r for r in records() if r['id']=='01c_existing_plan_message');source=OUT/r['file'];target=OUT/'chapters/01c_plan_message_completed.mp4'
 subprocess.run([FF,'-y','-v','error','-i',str(source),'-t','25','-c:v','libx264','-preset','veryfast','-crf','20','-an',str(target)],check=True)
 combine_chapter('01_existing_patient',['01a_existing_today','01b_existing_questionnaires','01c_plan_message_completed','01d_profile_photo','01e_access_revoke','01f_doctor_access_denied'],300)

def research_finish(b):
 with Scene(b,'04b_csv_readback','researcher','Исследователь: настоящий CSV открыт как текст','Выгружен общий агрегат: synthetic=True, n=12. Фильтр A/B к CSV не применяется; строк пациентов нет.') as s:
  path=OUT/'synthetic_research_aggregate.csv';data=path.read_text();assert 'True' in data and 'subject' not in data
  actual=PRIVATE/'synthetic_research_aggregate.csv.txt';actual.write_bytes(path.read_bytes());p=s.p;p.goto(actual.as_uri());p.locator('pre').evaluate("e=>e.style.cssText='font-size:25px;white-space:pre-wrap;word-break:break-word;line-height:1.8'")
  s.current={'route':'download:synthetic_research_aggregate.csv','action':'Реальный CSV открыт как текст, без строк пациентов','start':round(time.monotonic()-s.t,2)};s.pause(8)
 combine_chapter('04_researcher_complete',['04_researcher','04b_csv_readback'],180)

def roadmap_final(b):
 with Scene(b,'05a_experimental','doctor','Экспериментальный прототип','Clinical Copilot / NLP: иллюстрации и гипотезы не равны подтверждённому диагнозу. Врач сохраняет контроль.',status='DEMO_WITH_LIMITATION') as s:
  s.route('/doctor/clinical-copilot');s.pause(5);s.route('/doctor/nlp-lab');s.pause(5)
 with Scene(b,'05b_planned','shared','Планируется','Календарь пропусков, валидация AI и шкал, OIDC/MFA, импорт исследований, автономный Docker-LLM.',status='PLANNED') as s:
  s.route('/demo/journeys');s.pause(9);s.p.mouse.wheel(0,600);s.pause(6)
 combine_chapter('05_experimental_and_roadmap',['05a_experimental','05b_planned'],120)

def recover_new_user(b):
 if not state.get('new_user'):
  c=b.new_context(storage_state=str(PRIVATE/'new_patient-storage.json'));p=c.new_page();p.goto(BASE);r=p.request.get(BASE+'/api/v1/auth/me');assert r.ok;state['new_user']=r.json()['user'];c.close();save_private()

def patient_results(b):
 with Scene(b,'01g_four_form_results','patient','Пациент: четыре шкалы и сохранённые результаты','Все четыре учебные формы доступны; история содержит действительные суммы PHQ-9, PHQ-2 и GAD-7.') as s:
  s.route('/patient/tasks');p=s.p;items=p.request.get(BASE+'/api/v1/patient-experience/questionnaires/assignments').json()['items']
  for code in ('phq_9','phq_2','gad_7'):
   a=next(x for x in items if x['definition_id']=='eval_'+code+'_v1' and x['status']=='submitted')
   s.route('/patient/questionnaires/'+a['id']+'/result','/patient/questionnaires/:requestId/result');s.pause(3)
 combine_chapter('01_existing_patient',['01a_existing_today','01b_existing_questionnaires','01c_plan_message_completed','01d_profile_photo','01e_access_revoke','01f_doctor_access_denied','01g_four_form_results'],300)

def doctor_followup(b):
 with Scene(b,'02k_doctor_adherence','doctor','Врач: факт выполнения вернулся','План и отметка пациента видны врачу после серверного сохранения; назначения автоматически не меняются.') as s:
  s.route('/doctor/patients/'+PID+'/treatment','/doctor/patients/:patientId/treatment');p=s.p;loc=p.get_by_role('heading',name='Опубликованные планы и выполнение');s.focus(loc);s.pause(5);p.mouse.wheel(0,320);s.pause(3)
 with Scene(b,'02l_patient_adverse','patient','Пациент: сообщение о возможном событии','Сохраняю вымышленное сообщение; причинную связь и клиническое решение определяет врач.') as s:
  s.route('/patient/adverse-events/new');f=s.p.locator('[data-form=adverse]');s.fill(f,{'description':'Вымышленное сообщение для жюри о наблюдении, без утверждения причинной связи.'});s.submit(f,'/adverse-events');s.pause(2)
 with Scene(b,'02m_doctor_review_decision','doctor','Врач: оценка события и самостоятельное решение','Рассмотрение и клиническая запись сохраняются явно; алгоритм не принимает их за врача.') as s:
  s.route('/doctor/patients/'+PID+'/adverse-events','/doctor/patients/:patientId/adverse-events');p=s.p;f=p.locator('[data-form=adverse-review]').first;s.fill(f,{'review_text':'Учебный комментарий врача для жюри: причинная связь не установлена.'});s.submit(f,'/review',200);p.reload();s.pause(2)
  s.route('/doctor/patients/'+PID+'/decisions','/doctor/patients/:patientId/decisions');f=p.locator('[data-form=confirm-clinical-decision]');s.fill(f,{'text':'Самостоятельное учебное решение врача после просмотра вымышленных данных.'});f.locator('[name=confirmed]').check()
  with p.expect_response(lambda r:'/decisions/' in r.url and r.request.method=='POST') as saved:f.locator('button').click()
  assert saved.value.status==201;s.pause(3)
  s.route('/doctors');s.pause(3)
 ids=['02a_doctor_overview','02b_visit_lifecycle','02c_plan_lifecycle','02d_patient_receives','02k_doctor_adherence','02e_behavioral','02f_patient_intake','02g_qwen_nlp','02h_qwen_chat','02i_signals_message','02j_patient_answer','02l_patient_adverse','02m_doctor_review_decision']
 combine_chapter('02_doctor',ids,360)

def invitation_detail(b):
 with Scene(b,'00e_invitation_detail','doctor','Приглашение: ссылка, ключ и QR закрыты','Отдельное учебное приглашение: категории доступа видны, секретные области закрыты; затем отзываю ссылку.') as s:
  s.route('/doctor/invitations');p=s.p;f=p.locator('[data-form=create-invitation]');s.fill(f,{'recipient_email':state['new_email']});f.locator('[name=category]').first.check()
  with p.expect_response(lambda r:r.url.endswith('/invitations') and r.request.method=='POST') as made:f.locator('button').click()
  assert made.value.status==201;inv=made.value.json();s.pause(.3)
  boxes=p.locator('#created-invitation code,#created-invitation img').evaluate_all('es=>es.map(e=>{let r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height]})')
  p.locator('#created-invitation h3').evaluate('e=>window.scrollBy({top:e.getBoundingClientRect().top-120,behavior:"instant"})');s.pause(.3)
  boxes+=p.locator('#created-invitation code,#created-invitation img').evaluate_all('es=>es.map(e=>{let r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height]})')
  # Expand each secret's bounding region to cover the scroll trajectory, rather than hiding the whole screen.
  final=boxes[len(boxes)//2:];first=boxes[:len(boxes)//2];s.masks=[]
  for a,z in zip(first,final):
   x=min(a[0],z[0])-8;y=max(0,min(a[1],z[1])-8);right=max(a[0]+a[2],z[0]+z[2])+8;bottom=min(900,max(a[1]+a[3],z[1]+z[3])+8)
   if bottom>y:s.masks.append((x,y,right-x,bottom-y))
  s.pause(6)
  # Revoke via the existing guarded UI control if available, otherwise normal authenticated API cleanup.
  from tests_e2e.test_jury_live import mutate
  assert mutate(p,'POST','/api/v1/onboarding/invitations/'+inv['id']+'/revoke',{}).ok
  s.pause(1)
 combine_chapter('00_guest_new_patient',['00a_invitation','00b_guest_registration','00c_invite_consent','00d_doctor_new_link','00e_invitation_detail'],180)

def catalog_links(b):
 with Scene(b,'06b_catalog_links','shared','Связи материалов и поиск','Реальные внутренние переходы; 242 записи / 77 препаратов подтверждены ранее. Внешняя доступность не проверена.') as s:
  s.route('/clinical-library?type=medicine','/clinical-library');p=s.p
  # Actual search form and a genuine catalog link, not hard-coded fabricated relationships.
  f=p.locator('[data-form=catalog-search]')
  if f.count():
   field=f.locator('input[name=q]')
   if field.count():field.fill('Авиандр');f.locator('button').click();s.pause(2)
  link=p.locator('a[href*="item="]').first;link.click();s.pause(2);detail=p.locator('#catalog-detail')
  for kind in ('diagnosis','therapy','instrument'):
   links=detail.locator('a[href*="item='+kind+'%3A"],a[href*="item='+kind+':"]')
   if not links.count():break
   link=links.first;s.focus(link);link.click();s.pause(3)
   detail=p.locator('#catalog-detail')
 combine_chapter('06_catalog_complete',['06_catalog_and_assessments','06b_catalog_links'],180)

def remaining(b):
 patient_results(b)
 doctor_followup(b)
 invitation_detail(b)
 research_finish(b)
 catalog_links(b)
 roadmap_final(b)

def final_extra(b):
 with Scene(b,'06c_catalog_connected','shared','От препарата к шкале: реальные ссылки','Поиск сертралина → диагноз → КПТ → связанный диагноз → GAD-7. Справочник не формирует назначения.') as s:
  s.route('/clinical-library?type=medicine','/clinical-library');p=s.p;f=p.locator('[data-form=catalog-search]');f.locator('[name=q]').fill('сертралин');f.locator('button').click();s.pause(2)
  p.locator('a[href*="item=medicine%3Asertraline"]').first.click();s.pause(3)
  for kind,id in [('diagnosis','F41.1'),('therapy','cbt'),('diagnosis','F41.1'),('instrument','gad_7')]:
   link=p.locator('#catalog-detail a[href*="item='+kind+'%3A'+id+'"]').first;s.focus(link);link.click();s.pause(3)
  action=p.get_by_role('link',name='Пройти выбранный опросник',exact=True);s.focus(action);action.click();s.pause(3);p.locator('[data-form=guest-questionnaire] fieldset').first.locator('input[value="1"]').check();s.pause(2)
 with Scene(b,'03f_admin_partial','clinic_admin','Клиника: частично реализовано','Лицензии и профессиональное подключение требуют развития; действительные OIDC/MFA в этом контуре не настроены.',status='DEMO_WITH_LIMITATION') as s:
  s.route('/clinic/licenses');s.pause(4);s.route('/clinic/invitations');s.pause(4)
 with Scene(b,'04c_research_partial','researcher','Исследования: ограничения доступа','Частично реализовано: отдельные наборы и cohort builder требуют study grants. Учебный A/B — отдельный рабочий путь.',status='DEMO_WITH_LIMITATION') as s:
  s.route('/research/cohorts');s.pause(4);s.route('/research/datasets');s.pause(4)

def dark_signal(b):
 with Scene(b,'02n_dark_signal','doctor','Сигнал безопасности · тёмная тема','Сохранённая оценка врача и основание сигнала. Правило наблюдений не устанавливает клинический риск.') as s:
  s.route('/doctor/alerts');p=s.p;items=p.request.get(BASE+'/api/v1/doctor-experience/signals').json()['items'];signal=next(x for x in items if x['source']=='wellbeing_observation');s.route('/doctor/alerts/'+signal['id'],'/doctor/alerts/:alertId')
  p.locator('[data-command=menu]').click();p.locator('[data-command=settings]').click();p.locator('label.toggle').click();expect(p.locator('#theme-switch')).to_be_checked();p.locator('[data-command=close-modal]').click();s.pause(4);p.mouse.wheel(0,330);s.pause(4)
  p.locator('[data-command=menu]').click();p.locator('[data-command=settings]').click();p.locator('label.toggle').click();expect(p.locator('#theme-switch')).not_to_be_checked();p.locator('[data-command=close-modal]').click();s.pause(1)

if __name__=='__main__':
 arg=sys.argv[1] if len(sys.argv)>1 else 'prepare'
 with sync_playwright() as pw:
  b=pw.chromium.launch(headless=True);prepare(b)
  if arg in globals() and callable(globals()[arg]):globals()[arg](b)
  elif arg!='prepare':raise SystemExit('Unknown chapter '+arg)
  b.close()
