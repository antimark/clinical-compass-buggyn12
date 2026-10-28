"""User-authorized restoration of synthetic invitation UI from genuine raw footage."""
import json,shutil,subprocess,time,hashlib,os
from pathlib import Path
from record_jury_screencast import OUT,PRIVATE,ROOT,FF,encode,duration,probe,append
policy={'show_synthetic_invitation_values':True,'authorization':'Explicit user request to display prototype QR, invitation codes and links','scope':['00a_invitation','00c_invite_consent','00e_invitation_detail'],'notes':'Original synthetic invitations are consumed/revoked; no reactivation, no new recording or inference. Passwords/session cookies/keys remain private.'}
backup=PRIVATE/'before-invitation-restoration';backup.mkdir(exist_ok=True)
affected=['chapters/00_guest_new_patient.mp4','Clinical_Compass_Jury_Full_Walkthrough_RU.mp4','Clinical_Compass_Jury_Quick_Demo_RU.mp4']
for file in affected+['TECHNICAL_VALIDATION.json','PRIVACY_FRAME_SCAN.json','RECORDING_REPORT.md','DISCLOSED_LIMITATIONS.md']:
 src=OUT/file;dst=backup/Path(file).name
 if not dst.exists():shutil.copy2(src,dst)
archive=ROOT/'deliverables/Clinical_Compass_Jury_Videos_RU_20261028.zip'
if archive.exists() and not (backup/archive.name).exists():shutil.copy2(archive,backup/archive.name)
(OUT/'INVITATION_DISPLAY_POLICY.json').write_text(json.dumps(policy,ensure_ascii=False,indent=2))
latest={r['id']:r for r in [json.loads(x) for x in (OUT/'SCENES.jsonl').read_text().splitlines()]}
clips=PRIVATE/'sanitized-source-clips'
captions={
'00a_invitation':('Приглашение нового пациента','Врач задаёт категории доступа. Настоящие учебные ссылка, ключ и QR; связь создаётся после согласия.'),
'00c_invite_consent':('Новый пациент: явное согласие','Пациент проверяет приглашение и явно подтверждает категории; затем видит созданную связь.'),
'00e_invitation_detail':('Приглашение: ссылка, ключ и QR','Реальное учебное приглашение показывает механику передачи доступа. После записи ссылка отозвана.')}
for key,(title,desc) in captions.items():
 p=clips/(key+'.mp4')
 if not (backup/p.name).exists():shutil.copy2(p,backup/p.name)
 encode(PRIVATE/'raw'/latest[key]['raw_file'],p,title,desc,latest[key]['status'],masks=())
 print('RESTORED',key,flush=True)
edl=json.load(open(OUT/'EDIT_DECISION_LIST.json'));metrics=json.load(open(OUT/'TECHNICAL_VALIDATION.json'))
for file in affected:
 parts=[]
 for i,e in enumerate(edl[file]):
  source=clips/(e['scene']+'.mp4');start=e['source_start'];end=e['source_end']
  if start==0 and abs(duration(source)-end)<.02:part=source
  else:
   part=PRIVATE/'cuts'/(Path(file).stem+'-restored-'+str(i)+'.mp4')
   subprocess.run([FF,'-y','-v','error','-ss',str(start),'-i',str(source),'-t',str(end-start),'-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-an','-movflags','+faststart',str(part)],check=True)
  parts.append(part)
 spec=PRIVATE/(Path(file).stem+'-restored-concat.txt');spec.write_text('\n'.join("file '"+str(p)+"'" for p in parts))
 target=OUT/file
 subprocess.run([FF,'-y','-v','error','-f','concat','-safe','0','-i',str(spec),'-c','copy','-movflags','+faststart',str(target)],check=True)
 data=probe(target);v=next(x for x in data['streams'] if x['codec_type']=='video');seconds=float(data['format']['duration']);old=next(x for x in metrics if x['file']==file)
 assert abs(seconds-old['duration_seconds'])<.05 and seconds<=old['limit_seconds']
 assert v['codec_name']=='h264' and v['width']==1920 and v['height']==1080 and v['avg_frame_rate']=='30/1'
 r=subprocess.run([FF,'-v','error','-i',str(target),'-f','null','-'],capture_output=True,text=True);assert r.returncode==0 and not r.stderr
 old.update(bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),duration_seconds=seconds,revision='synthetic invitation UI restored by explicit user request')
 print('DECODE PASS',file,round(seconds,2),flush=True)
(OUT/'TECHNICAL_VALIDATION.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2))
# Real player verification for the three changed files only.
from playwright.sync_api import sync_playwright
with sync_playwright() as w:
 b=w.chromium.launch(headless=True);p=b.new_page();p.goto((PRIVATE/'playback.html').as_uri())
 for file in affected:
  meta=next(x for x in metrics if x['file']==file);p.locator('video').evaluate('(e,url)=>{e.pause();e.src=url;e.load()}',(OUT/file).as_uri());p.wait_for_function('document.querySelector("video").readyState>=2');p.locator('video').evaluate('async e=>{e.muted=true;await e.play()}');p.wait_for_function('document.querySelector("video").currentTime>.6')
  for t in [meta['duration_seconds']/2,meta['duration_seconds']-1]:
   p.locator('video').evaluate('(e,t)=>{e.pause();e.currentTime=t}',t);p.wait_for_function('(t)=>{let v=document.querySelector("video");return Math.abs(v.currentTime-t)<.25&&v.readyState>=2}',arg=t)
  assert p.locator('video').evaluate('e=>e.error?.code||null') is None
  append(OUT/'PLAYBACK_RESULTS.jsonl',{'file':file,'result':'PASS','revision':'user-authorized invitation restoration','method':'actual Chromium play and seek; changed files only'})
 b.close()
# Recheck password fragments, while intentionally permitting prototype invitation tokens and QR.
frames=PRIVATE/'invitation-restored-review';frames.mkdir(exist_ok=True)
for key in captions:
 subprocess.run([FF,'-y','-v','error','-i',str(clips/(key+'.mp4')),'-vf','fps=2',str(frames/(key+'-%04d.png'))],check=True)
state=json.load(open(PRIVATE/'state.json'));actors=json.load(open('/private/tmp/clinical-compass-jury-handoff-20261027/jury-actors.json'));passwords=[state['new_password']]+[x['password'] for x in actors.values()]
secrets=PRIVATE/'passwords-only-scan.txt';secrets.write_text('\n'.join(passwords));os.chmod(secrets,0o600)
scan=json.loads(subprocess.check_output(['/private/tmp/cc-video-tools/video_privacy_scan',str(frames),str(secrets)]));assert not any(x['secret_matches'] for x in scan['findings'])
scan.update(authorization='Prototype invitation values/QR intentionally visible by explicit user request',password_secret_matches=0,readable_demo_qr_findings=sum(x['readable_qr'] for x in scan['findings']),historical_redacted_check='Retained privately in before-invitation-restoration; no longer describes current invitation footage')
(OUT/'PRIVACY_FRAME_SCAN.json').write_text(json.dumps(scan,ensure_ascii=False,indent=2))
# One full-size frame to inspect restored values, without writing token payloads into logs.
subprocess.run([FF,'-y','-v','error','-ss','7','-i',str(clips/'00e_invitation_detail.mp4'),'-frames:v','1',str(PRIVATE/'invitation-restored-review.png')],check=True)
append(ROOT/'reports/phase3/raw/screencast-recording-20261028.jsonl',{'revision':'user-authorized restoration of synthetic QR/code/link','affected':affected,'result':'PASS','n':3,'new_app_actions':0,'new_ai_requests':0,'timestamp':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()})
print('Changed3 playback PASS; visible demo QR samples',scan['readable_demo_qr_findings'],'password findings0',flush=True)
