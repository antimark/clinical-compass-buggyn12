"""Offline edits of actual Chromium footage. No generated app screens or AI replies."""
import sys,os,json,csv,subprocess,hashlib,shutil,datetime
from pathlib import Path
from record_jury_screencast import OUT,PRIVATE,ROOT,FF,FP,probe,duration,encode,caption,append,stamp
CLIPS=PRIVATE/'sanitized-source-clips' if (PRIVATE/'sanitized-source-clips').exists() else OUT/'source_clips'; CLIPS.mkdir(exist_ok=True)
HISTORY=[json.loads(x) for x in (OUT/'SCENES.jsonl').read_text().splitlines()]
LATEST={r['id']:r for r in HISTORY}
for key,r in LATEST.items():
 src=OUT/r['file'];dest=CLIPS/(key+'.mp4')
 if src.exists() and not dest.exists():shutil.copy2(src,dest)
# Public clips get Russian captions; no successful scene is re-recorded.
for key in ['06_catalog_and_assessments','00a_invitation','00b_guest_registration','00c_invite_consent','00d_doctor_new_link','01a_existing_today','01b_existing_questionnaires']:
 r=LATEST[key];masks=r['masks']
 if key=='00c_invite_consent':
  # Token may move upwards while the consent area scrolls. Mask the complete trajectory.
  x,y,w,h=masks[0];masks=[(0,0,1440,int(y+h+12))]
 title={'06_catalog_and_assessments':'Справочник и четыре шкалы','00a_invitation':'Приглашение нового пациента','00b_guest_registration':'Гость → новый пациент','00c_invite_consent':'Новый пациент: явное согласие','00d_doctor_new_link':'Врач: связь подтверждена','01a_existing_today':'Существующий пациент · Сегодня','01b_existing_questionnaires':'Учебные опросники: сохранение'}.get(key,key)
 encode(PRIVATE/'raw'/r['raw_file'],CLIPS/(key+'.mp4'),title,r['description'],r['status'],masks)
# Preserve the first attempts privately, including script-only selector/viewer waits.
faildir=PRIVATE/'failed-attempts';faildir.mkdir(exist_ok=True)
for key in ['01c_existing_plan_message','04_researcher']:
 if (CLIPS/(key+'.mp4')).exists():shutil.copy2(CLIPS/(key+'.mp4'),faildir/(key+'.mp4'))
# Real completed plan/message part; upload is shown separately in 01d.
if not (CLIPS/'01c_plan_message_completed.mp4').exists():
 subprocess.run([FF,'-y','-v','error','-i',str(CLIPS/'01c_existing_plan_message.mp4'),'-t','25','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-an',str(CLIPS/'01c_plan_message_completed.mp4')],check=True)
# The successful research actions precede Chromium's extra CSV-download navigation.
# Keep original source intact privately; the actual downloaded CSV is displayed in 04b.
LATEST['04_researcher']['limitations']='A/B и CSV сохранены; прямое открытие .csv в Chromium начинало повторное скачивание. Отдельный текстовый просмотр04b. График отсутствует.'
# Keep failure attempt metadata; no fabricated replacement test pass.
SCENES={**LATEST};SCENES['01c_plan_message_completed']={**LATEST['01c_existing_plan_message'],'id':'01c_plan_message_completed','seconds':25,'events':[e for e in LATEST['01c_existing_plan_message']['events'] if e['start']<25],'result':'LIVE_RECORDED_PART','limitations':'Только успешно записанные план/сообщение/профиль до ожидания неверного селектора загрузки. Загрузка отдельно01d.'}

# Include the actual creation from the first capture, with its recording-only interruption disclosed.
created=next(r for r in HISTORY if r['id']=='02b_visit_lifecycle' and r['result']=='FAIL')
full_created=PRIVATE/'visit-created-source.mp4'
encode(PRIVATE/'raw'/created['raw_file'],full_created,'Создание черновика: первый дубль','Черновик сохранён. Затем исправлен селектор записи; продолжаем с тем же документом, без повторного создания.','LIVE_VERIFIED')
subprocess.run([FF,'-y','-v','error','-i',str(full_created),'-t','8','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-an',str(CLIPS/'02b_visit_created_part.mp4')],check=True)
SCENES['02b_visit_created_part']={**created,'id':'02b_visit_created_part','seconds':8,'events':[{**created['events'][0],'end':8}],'result':'LIVE_RECORDED_PART','limitations':'Создание прошло201; ожидание неверного селектора скрипта раскрыто в титре. Продолжение с тем же документом в02b.'}

def cut(key,start=0,end=None):
 p=CLIPS/(key+'.mp4');d=duration(p);end=min(d,end if end is not None else d);assert end>start
 if start==0 and abs(end-d)<.02:return p,{'scene':key,'source_start':0,'source_end':d,'seconds':d}
 target=PRIVATE/'cuts'/(key+'-'+str(start)+'-'+str(round(end,3))+'.mp4');target.parent.mkdir(exist_ok=True)
 subprocess.run([FF,'-y','-v','error','-ss',str(start),'-i',str(p),'-t',str(end-start),'-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-an','-movflags','+faststart',str(target)],check=True)
 return target,{'scene':key,'source_start':start,'source_end':end,'seconds':duration(target)}
def concat(files,target):
 spec=PRIVATE/(target.stem+'-edit.txt');spec.write_text('\n'.join("file '"+str(x)+"'" for x in files));subprocess.run([FF,'-y','-v','error','-f','concat','-safe','0','-i',str(spec),'-c','copy','-movflags','+faststart',str(target)],check=True)
EDL={}
def make(file,selection,limit):
 files=[];events=[];offset=0
 for item in selection:
  if isinstance(item,str):item=(item,0,None)
  p,entry=cut(*item);entry['output_start']=offset;offset+=entry['seconds'];entry['output_end']=offset;files.append(p);events.append(entry)
 target=OUT/file;concat(files,target);assert duration(target)<=limit,(file,duration(target),limit)
 EDL[file]=events;print(file,round(duration(target),2),flush=True)

chapters={
'00_guest_new_patient':['00a_invitation','00b_guest_registration','00c_invite_consent','00d_doctor_new_link','00e_invitation_detail'],
'01_existing_patient':['01a_existing_today','01b_existing_questionnaires','01c_plan_message_completed','01d_profile_photo','01e_access_revoke','01f_doctor_access_denied','01g_four_form_results'],
'02_doctor':['02a_doctor_overview','02b_visit_created_part','02b_visit_lifecycle','02c_plan_lifecycle','02d_patient_receives','02k_doctor_adherence','02e_behavioral','02f_patient_intake','02g_qwen_nlp','02h_qwen_chat','02i_signals_message','02n_dark_signal','02j_patient_answer','02l_patient_adverse','02m_doctor_review_decision'],
'03_clinic_admin':['03a_admin_hidden','03b_patient_name_optin','03c_admin_name_visible','03d_patient_revoke_name','03e_admin_revoked','03f_admin_partial'],
'04_researcher':['04_researcher','04b_csv_readback','04c_research_partial'],
'05_experimental_and_roadmap':['05a_experimental','05b_planned'],
'06_catalog_and_assessments':['06_catalog_and_assessments','06c_catalog_connected']}
limits=[180,300,360,180,180,120,180]
for (name,selection),limit in zip(chapters.items(),limits):make('chapters/'+name+'.mp4',selection,limit)
full=[('00b_guest_registration',0,10),'00a_invitation',('00b_guest_registration',10,None),'00c_invite_consent','00d_doctor_new_link',('00e_invitation_detail',2,None),'01a_existing_today','01b_existing_questionnaires',('01c_plan_message_completed',0,15),('02a_doctor_overview',0,12),'02b_visit_created_part','02b_visit_lifecycle','02c_plan_lifecycle','02d_patient_receives','02k_doctor_adherence','02f_patient_intake','02g_qwen_nlp','02h_qwen_chat','02i_signals_message','02n_dark_signal','02j_patient_answer','03a_admin_hidden','03b_patient_name_optin','03c_admin_name_visible','03d_patient_revoke_name','03e_admin_revoked',('03f_admin_partial',0,7),'04_researcher','04b_csv_readback',('04c_research_partial',0,7),('06_catalog_and_assessments',0,23),'06c_catalog_connected',('05a_experimental',0,10),('05b_planned',0,14)]
make('Clinical_Compass_Jury_Full_Walkthrough_RU.mp4',full,600)
nlp=float([json.loads(x) for x in (OUT/'AI_TIMINGS.jsonl').read_text().splitlines() if 'fresh_real_nlp' in x][-1]['seconds'])
quick=[('00e_invitation_detail',2,7),('00b_guest_registration',10,28),('00b_guest_registration',30,None),('00c_invite_consent',4,None),'02b_visit_lifecycle','02c_plan_lifecycle','02d_patient_receives',('02g_qwen_nlp',0,nlp+15),('04_researcher',14,None),('04b_csv_readback',0,6),('05b_planned',0,6)]
make('Clinical_Compass_Jury_Quick_Demo_RU.mp4',quick,180)
(OUT/'EDIT_DECISION_LIST.json').write_text(json.dumps(EDL,ensure_ascii=False,indent=2))
# Remove surplus copies from chapters while preserving all short footage in source_clips.
expected={name+'.mp4' for name in chapters}
for p in (OUT/'chapters').glob('*.mp4'):
 if p.name not in expected:
  dest=CLIPS/p.name
  if not dest.exists():shutil.copy2(p,dest)
  p.unlink() # duplicate only; source footage and private raw remain preserved
# Failed full attempts are private; completed portions remain public with explicit notes.
for name in ['01c_existing_plan_message.mp4']:
 p=CLIPS/name
 if p.exists():p.unlink() # identical copy retained at PRIVATE/failed-attempts
fields=['role','scenario_id','route','action','implementation_status','verification_status','video_file','start_time','end_time','evidence','limitations']
rows=[]
def intervals(file,edits):
 result=[]
 for edit in edits:
  r=SCENES.get(edit['scene']);
  if not r:continue
  for e in r['events']:
   lo=max(e['start'],edit['source_start']);hi=min(e['end'],edit['source_end'])
   if hi<=lo:continue
   start=edit['output_start']+lo-edit['source_start'];end=edit['output_start']+hi-edit['source_start']
   status=r['status'];verification='LIVE_VERIFIED' if r['result']=='PASS' else 'DEMO_WITH_LIMITATION'
   result.append([r['role'],r['id'],e['route'],e['action'],status,verification,file,stamp(start),stamp(end),'SCENES.jsonl; EDIT_DECISION_LIST.json',r.get('limitations','')])
 return result
for file,edits in EDL.items():rows+=intervals(file,edits)
routes=json.loads((ROOT/'frontend/dist/assets/data/routes.json').read_text());inventory=[]
for route in routes:
 match=next((row for row in rows if row[2]==route['path'] and row[6].startswith('chapters/')),None)
 if match:inventory.append([route['role'],'route_inventory',route['path'],route['action'],match[4],match[5],match[6],match[7],match[8],match[9],match[10]])
 else:inventory.append([route['role'],'route_inventory',route['path'],route['action'],'NOT_CAPTURED','NOT_CAPTURED','','','','frontend/dist/assets/data/routes.json; reports/phase2/FEATURE_PARITY.csv','Не снимался: ограниченный формат видео. Прежняя проверка не подменяет запись. Гранты/OIDC/условные идентификаторы сохраняют серверные ограничения.'])
assert len(inventory)==102
with (OUT/'VIDEO_INDEX.csv').open('w') as f:w=csv.writer(f);w.writerow(fields);w.writerows(inventory+rows)
(OUT/'SOURCE_CLIP_MANIFEST.json').write_text(json.dumps([{'scene':k,'file':'source_clips/'+k+'.mp4','raw_private_basename':r.get('raw_file'),'result':r['result']} for k,r in SCENES.items() if (CLIPS/(k+'.mp4')).exists()],ensure_ascii=False,indent=2))
print('Inventory102; captured',sum(r[5]!='NOT_CAPTURED' for r in inventory),flush=True)
