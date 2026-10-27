"""Technical, real Chromium playback and known-secret/QR frame checks; no app mutation."""
import json,subprocess,sys,hashlib,time,os
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image,ImageDraw,ImageFont
from record_jury_screencast import OUT,PRIVATE,ROOT,FF,FP,probe,append,FONT
files=[OUT/'Clinical_Compass_Jury_Full_Walkthrough_RU.mp4',OUT/'Clinical_Compass_Jury_Quick_Demo_RU.mp4']+sorted((OUT/'chapters').glob('*.mp4'))
limits=[600,180,180,300,360,180,180,120,180];assert len(files)==9
samples=PRIVATE/'qa-frames';samples.mkdir(exist_ok=True)
metrics=[]
for path,limit in zip(files,limits):
 data=probe(path);v=next(s for s in data['streams'] if s['codec_type']=='video');seconds=float(data['format']['duration'])
 assert v['codec_name']=='h264' and v['width']==1920 and v['height']==1080 and v['avg_frame_rate']=='30/1' and seconds<=limit,(path.name,seconds,v['avg_frame_rate'])
 result=subprocess.run([FF,'-hide_banner','-v','error','-i',str(path),'-f','null','-'],capture_output=True,text=True)
 assert result.returncode==0 and not result.stderr,(path.name,result.stderr[:120])
 for label,t in [('start',min(1,seconds/3)),('middle',seconds/2),('end',max(0,seconds-1))]:
  subprocess.run([FF,'-y','-v','error','-ss',str(t),'-i',str(path),'-frames:v','1',str(samples/(path.stem+'-'+label+'.png'))],check=True)
 row={'file':str(path.relative_to(OUT)),'duration_seconds':seconds,'limit_seconds':limit,'width':v['width'],'height':v['height'],'fps':v['avg_frame_rate'],'codec':v['codec_name'],'pixel_format':v['pix_fmt'],'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'full_decode':'PASS','audio':'none (intentional silent captions)'};metrics.append(row);print('DECODE',path.name,round(seconds,2),flush=True)
(OUT/'TECHNICAL_VALIDATION.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2))
# Playback in the real Chromium media element, not only container metadata.
player=PRIVATE/'playback.html';player.write_text('<!doctype html><html><body style="margin:0;background:#101e2b"><video controls muted style="width:100vw;height:100vh"></video></body></html>')
with sync_playwright() as w:
 b=w.chromium.launch(headless=True);p=b.new_page(viewport={'width':1920,'height':1080});p.goto(player.as_uri())
 for path,meta in zip(files,metrics):
  p.locator('video').evaluate('(e,url)=>{e.pause();e.src=url;e.load();}',path.as_uri());p.wait_for_function('document.querySelector("video").readyState>=2')
  p.locator('video').evaluate('async e=>{e.muted=true;await e.play()}');p.wait_for_function('document.querySelector("video").currentTime>.6')
  checks=[]
  for t in [meta['duration_seconds']/2,max(0,meta['duration_seconds']-1)]:
   p.locator('video').evaluate('(e,t)=>{e.pause();e.currentTime=t}',t);p.wait_for_function('(t)=>{let v=document.querySelector("video");return Math.abs(v.currentTime-t)<.25&&v.readyState>=2}',arg=t);checks.append(t)
  error=p.locator('video').evaluate('e=>e.error?.code||null');assert error is None
  append(OUT/'PLAYBACK_RESULTS.jsonl',{'file':meta['file'],'result':'PASS','start_played_seconds':.6,'seek_targets':checks,'media_error':error,'method':'actual Chromium HTMLVideoElement play and seek'})
 b.close()
# Overview sheets: actual beginning/middle/end frame thumbnails for manual inspection.
paths=sorted(samples.glob('*.png'));thumbs=[]
for p in paths:
 im=Image.open(p).convert('RGB');im.thumbnail((480,270));tile=Image.new('RGB',(480,310),'#142131');tile.paste(im,(0,0));ImageDraw.Draw(tile).text((5,275),p.stem[:57],font=ImageFont.truetype(FONT,12),fill='white');thumbs.append(tile)
for n in range(0,len(thumbs),12):
 group=thumbs[n:n+12];sheet=Image.new('RGB',(1920,310*((len(group)+3)//4)),'#142131')
 for i,im in enumerate(group):sheet.paste(im,((i%4)*480,(i//4)*310))
 sheet.save(samples/('CONTACT-'+str(n//12)+'.png'))
# Sample every half second of secret-bearing invitation clips AFTER redaction.
frames=PRIVATE/'privacy-frames';frames.mkdir(exist_ok=True)
for key in ['00a_invitation','00c_invite_consent','00e_invitation_detail']:
 clip_root=PRIVATE/'sanitized-source-clips' if (PRIVATE/'sanitized-source-clips').exists() else OUT/'source_clips'
 path=clip_root/(key+'.mp4');subprocess.run([FF,'-y','-v','error','-i',str(path),'-vf','fps=2',str(frames/(key+'-%04d.png'))],check=True)
state=json.loads((PRIVATE/'state.json').read_text());known=[]
if state.get('invite',{}).get('token'):known += [state['invite']['token'],state['invite']['token'][:10]]
known += [state['new_password'],state['new_password'][:10]]
actors=json.loads(Path('/private/tmp/clinical-compass-jury-handoff-20261027/jury-actors.json').read_text())
known += [v['password'] for v in actors.values()]
secretfile=PRIVATE/'known-secret-fragments.txt';secretfile.write_text('\n'.join(known));os.chmod(secretfile,0o600)
scan=subprocess.check_output(['/private/tmp/cc-video-tools/video_privacy_scan',str(frames),str(secretfile)])
(OUT/'PRIVACY_FRAME_SCAN.json').write_bytes(scan);result=json.loads(scan);assert result['frames']>0 and not result['findings'],result
print('PLAYBACK9 PASS; privacy frames',result['frames'],'no detected known secrets/readable QR',flush=True)
