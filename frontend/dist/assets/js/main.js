import {formDiagnoses,onDiagnosisInput,chooseMedication} from './medication-matches.js';
import {api,bootstrap,getCsrf,segment} from './api.js';
import {icon,esc,attr,link,button,state,errorState} from './ui.js';
import {chrome,accountMenu,resolveView,roleHomes,roleNames,catalogDetail} from './views.js';
import {clinicalFormAction,clinicalCommand,renderLabSummary} from './clinical-demo.js';
import {syncPending,handleGuestSubmit,readPending} from './guest-assessments.js';
const app={session:null,bootstrap:null,env:'unknown',routes:[],period:30,invitation:null,inviteToken:'',started:false,pendingSaveError:''};
const $=(q,root=document)=>root.querySelector(q);
const byid=(s)=>document.getElementById(s);
const alertError=(form,message)=>{const target=$('[data-form-error]',form);if(target){target.textContent=message||'';target.setAttribute('role','alert');}};
const messageFor=(e)=>e?.message||'Произошла ошибка. Попробуйте ещё раз.';
let renderId=0,modalReturn=null,modalHandler=null,menuOpen=false;
function routeInfo(){let raw=(location.hash.startsWith('#/')?location.hash.slice(1):location.pathname);if(!raw||raw==='/index.html')raw='/';const [pathPart]=raw.split('?');let path=pathPart.replace(/\/+$/,'')||'/';try{path=decodeURI(path)}catch{}
 return {path,query:new URLSearchParams(raw.split('?').slice(1).join('?'))};}
function matchRoute(path){for(const r of [...app.routes].sort((a,b)=>b.path.replace(/:[^/]+/g,'____').length-a.path.replace(/:[^/]+/g,'____').length)){
  const names=[];const regex=new RegExp('^'+r.path.split('/').map(s=>{if(s.startsWith(':')){names.push(s.slice(1));return '([^/]+)';}return s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}).join('/')+'$');const m=regex.exec(path);
  if(m){let params={};names.forEach((k,i)=>{try{params[k]=decodeURIComponent(m[i+1]);}catch{params[k]=m[i+1];}});return {route:r,params};}
 }return {route:null,params:{}};}
function permitted(route){if(!route||!['patient','doctor','clinic','research'].includes(route.role))return true;
 const role=app.session?.context?.role;return route.role==='clinic'?['clinic_admin','platform_admin'].includes(role):role===({research:'researcher'}[route.role]||route.role);}
function intendedRoute(raw){if(typeof raw!=='string'||!raw.startsWith('/')||raw.startsWith('//')||/[\\\x00-\x1f\x7f]/.test(raw))return null;const path=raw.split('?')[0];const target=matchRoute(path).route;return target&&permitted(target)&&!['/login','/register'].includes(path)?raw:null;}
function buildShell(routePath,inside){const bits=chrome(app.session,app.env,routePath);const main=app.session&&routePath.startsWith('/'+(app.session.context.role==='clinic_admin'?'clinic':app.session.context.role==='researcher'?'research':app.session.context.role))&&bits.aside;
 return `${bits.head}<main id="main" class="shell" tabindex="-1">${main?`<div class="side-layout">${bits.aside}<div class="content-area">${inside}</div></div>`:inside}</main>${bits.footer}`;}
async function render(){const current=++renderId,{path}=routeInfo(),{route,params}=matchRoute(path);
 const container=byid('app');container.classList.toggle('is-home',path==='/');menuClose();container.innerHTML=buildShell(path,`<div aria-busy="true">${state('Загружаем страницу','Получаем актуальные данные из сервера.','loading')}</div>`);
 let content;
 try{content=permitted(route)?await resolveView(route,path,params,app):`${pageTitle('Доступ ограничен')}${state('Недостаточно прав','Войдите с учётной записью указанной роли. После входа вернём вас к выбранному разделу.','forbidden',link('/login?next='+encodeURIComponent(path+(routeInfo().query.size?'?'+routeInfo().query.toString():'')),'Войти и продолжить','primary'))}`;}
 catch(e){content=`${pageTitle('Ошибка загрузки')}${errorState(e)}`;}
 if(current!==renderId)return;
 container.innerHTML=buildShell(path,content||`${pageTitle('Раздел недоступен')}${state('Не удалось открыть страницу','Проверьте маршрут.')}`);
 document.title=`${route?.title||'Clinical Compass'} · Clinical Compass`;
 if(path==='/invite/accept'||path.startsWith('/invite/')){let code=params.token||app.inviteToken;if(code){const input=$('#invite-token');if(input)input.value=code;}}
 if((path==='/clinical-library'||path==='/doctor/clinical-library')&&routeInfo().query.has('item')){let item=routeInfo().query.get('item')||'';let idx=item.indexOf(':');if(idx>0){const detail=byid('catalog-detail');if(detail){const html=await catalogDetail(item.slice(0,idx),item.slice(idx+1));if(current!==renderId)return;detail.innerHTML=html;detail.scrollIntoView({block:'start',behavior:'instant'});}}}
}
function pageTitle(v){return `<h1 class="page-title">${esc(v)}</h1>`;}
function navTo(path){if(!path.startsWith('/'))return;menuClose();closeModal();location.href='/#'+path;if(routeInfo().path===path)render();}
function toast(text){const el=byid('toast-root');el.innerHTML=`<div class="toast">${esc(text)}</div>`;setTimeout(()=>{if(el.firstElementChild?.textContent===text)el.textContent='';},3800);}
function menuClose(){byid('floating-root').replaceChildren();menuOpen=false;const btn=byid('avatar-button');if(btn)btn.setAttribute('aria-expanded','false');}
function menuToggle(){if(menuOpen){menuClose();return;}
 const btn=byid('avatar-button');if(!btn||!app.session)return;menuOpen=true;
 const bounds=btn.getBoundingClientRect(),menuWidth=parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--account-menu-width"))||320,left=Math.max(12,Math.min(innerWidth-menuWidth-12,bounds.right-menuWidth));
 const float=byid('floating-root');float.innerHTML=`<div class="account-menu" role="menu" aria-label="Меню аккаунта" >${accountMenu(app.session,app.env).replace(/^<div class="account-menu"[^>]*>/,'').replace(/<\/div>$/,'')}</div>`;
 const menu=$("#floating-root .account-menu");if(menu){menu.style.left=Math.max(10,left)+"px";menu.style.top=(bounds.bottom+12)+"px";}btn.setAttribute('aria-expanded','true');const first=$('[role="menuitem"]',float);if(first)first.focus();
}
function closeModal(){const root=byid('overlay-root');root.replaceChildren();document.body.style.overflow='';document.removeEventListener('keydown',modalHandler);modalHandler=null;if(modalReturn?.isConnected)modalReturn.focus();modalReturn=null;}
function modal(content,heading='Настройки'){const opener=document.activeElement;closeModal();menuClose();modalReturn=opener?.isConnected?opener:byid('avatar-button');
 const root=byid('overlay-root');root.innerHTML=`<div class="overlay" data-overlay="true"><section class="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><button class="btn btn-secondary btn-icon close" type="button" data-command="close-modal" aria-label="Закрыть окно">${icon('x')}</button><h2 id="dialog-title">${esc(heading)}</h2><div class="dialog-body">${content}</div></section></div>`;document.body.style.overflow='hidden';$('.dialog button',root)?.focus();
 modalHandler=(e)=>{if(e.key==='Escape'){e.preventDefault();closeModal();return;}if(e.key==='Tab'){const els=[...root.querySelectorAll('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled])')];if(!els.length)return;const i=els.indexOf(document.activeElement);if(e.shiftKey&&i===0){e.preventDefault();els.at(-1).focus();}else if(!e.shiftKey&&i===els.length-1){e.preventDefault();els[0].focus();}}};document.addEventListener('keydown',modalHandler);
}
function settings(){modal(`<div class="list-row"><div class="row-main"><h4>Тёмная тема</h4><div class="small muted">Liquid Glass Clear — единый материал интерфейса</div></div><label class="toggle"><input aria-label="Тёмная тема" type="checkbox" id="theme-switch" ${document.documentElement.dataset.theme==='dark'?'checked':''}><span class="track"></span></label></div><p class="small muted space-top-20">Настройки оформления хранятся только в этом браузере. Клинические разрешения задаются отдельно сервером.</p>`,'Настройки');}
function setTheme(dark){document.documentElement.dataset.theme=dark?'dark':'light';try{localStorage.setItem('cc.theme',dark?'dark':'light');}catch{}}
async function boot(){try{app.routes=await (await fetch('/assets/data/routes.json')).json();}catch{app.routes=[];}
 try{app.bootstrap=await bootstrap();app.session=app.bootstrap.session;app.env=app.bootstrap.boot.environment||'unknown';}catch{app.bootstrap={boot:{enabled:false},oidc:{enabled:false}};}
 app.started=true;await render();}
function clearValidation(form){alertError(form,'');}
function fromForm(form){const f=new FormData(form);return Object.fromEntries(f.entries());}
function startBusy(form){if(form.dataset.pending)return false;form.dataset.pending='1';form.querySelectorAll('button').forEach(b=>{b.dataset.wasDisabled=b.disabled?'1':'0';b.disabled=true;});return true;}
function stopBusy(form){delete form.dataset.pending;form.querySelectorAll('button').forEach(b=>{if(b.dataset.wasDisabled==='0')b.disabled=false;delete b.dataset.wasDisabled;});}
async function syncSession(){app.bootstrap=await bootstrap();app.session=app.bootstrap.session;app.env=app.bootstrap.boot.environment||'unknown';}
async function submit(form){if(!startBusy(form))return;clearValidation(form);let destination=null;try{const action=form.dataset.form,d=fromForm(form);
 switch(action){
 case 'login':{await api.post('/api/v1/onboarding/login',{email:d.email,password:d.password});await syncSession();destination=app.inviteToken?'/invite/'+segment(app.inviteToken):(roleHomes[app.session?.context?.role]||'/');const next=intendedRoute(routeInfo().query.get('next'));if(!app.inviteToken&&next)destination=next;if(readPending()&&app.session?.context?.role==='patient'){try{destination=await syncPending(app.session)||destination;app.pendingSaveError='';}catch(e){app.pendingSaveError='Вход выполнен, но результат ещё не сохранён: '+messageFor(e);destination='/assessments/'+segment(readPending().code)+'/result';}}break;}
 case 'register':{
  if(d.password!==d.confirm_password)throw new Error('Пароли не совпадают.');if(!form.querySelector("[name=terms_consent]")?.checked)throw new Error('Подтвердите условия регистрации.');
  let payload={display_name:d.display_name,email:d.email,password:d.password,terms_consent:true};if(app.inviteToken)payload.invitation_token=app.inviteToken;
  await api.post('/api/v1/onboarding/register',payload);await syncSession();destination=app.inviteToken?'/invite/'+segment(app.inviteToken):'/patient';if(readPending()&&app.session?.context?.role==='patient'){try{destination=await syncPending(app.session)||destination;app.pendingSaveError='';}catch(e){app.pendingSaveError='Вход выполнен, но результат ещё не сохранён: '+messageFor(e);destination='/assessments/'+segment(readPending().code)+'/result';}}break;}
 case 'invite-preview':{
  let token=d.token.trim();const match=token.match(/\/invite\/([^?&#/]+)/);if(match)token=decodeURIComponent(match[1]);const r=await api.post('/api/v1/onboarding/invitations/preview',{token});app.invitation=r;app.inviteToken=token;
  const categories={symptoms:'Симптомы',diagnosis:'Диагнозы',medications:'Назначения и лекарства',severity:'Выраженность состояния'};
  const root=byid('invitation-preview');if(root)root.innerHTML=`<div class="card inset"><h3>Приглашение от ${esc(r.doctor?.name||'специалиста')}</h3><p class="small muted">Срок: ${esc(r.expires_at||'не указан')} · Версия согласия: ${esc(r.consent_version)}</p><h4>Запрашиваемые права</h4>${(r.categories||[]).map(x=>`<div class="list-row">${icon('shield')} ${esc(categories[x]||x)}</div>`).join('')}<div class="grid-line"></div>${app.session?.context?.role==='patient'?`<form data-form="invite-accept" class="form-stack"><label class="checkline"><input type="checkbox" name="consent" required>Я принимаю именно перечисленные права</label><p class="error-inline" data-form-error role="alert"></p><div class="row"><button class="btn btn-primary">Принять приглашение</button><button type="button" class="btn btn-quiet" data-command="decline-invite">Отказаться</button></div></form>`:`<p class="muted small">Войдите как пациент, чтобы дать согласие.</p>${link('/login','Войти','primary')}`}</div>`;
  toast('Приглашение проверено сервером');break;}
 case 'invite-accept':{if(!app.inviteToken||!app.invitation)throw new Error('Сначала проверьте приглашение.');if(!d.consent)throw new Error('Нужно явное согласие.');await api.post('/api/v1/onboarding/invitations/accept',{token:app.inviteToken,consent:true,consent_version:app.invitation.consent_version});app.invitation=null;app.inviteToken='';destination='/patient/specialists';break;}
 case 'checkin':{await api.post('/api/v1/patients/me/check-ins',{mood_score:Number(d.mood_score),comparison:d.comparison,note:d.note||''});toast('Отметка сохранена');await render();break;}
 case 'new-request':{const r=await api.post('/api/v1/previsit-cases',{doctor_id:d.doctor_id,text:d.text,symptoms:[],conditions:[],case_consent:true});destination='/patient/requests/'+segment(r.id);break;}
 case 'clinical-message':{await api.post('/api/v1/threads/patient_doctor/'+segment(form.dataset.id)+'/messages',{text:d.text});toast('Сообщение доставлено в сохранённый диалог');await render();break;}
 case 'team-visibility-create':{if(d.doctor_a===d.doctor_b)throw new Error('Выберите двух разных врачей');if(!form.querySelector('[name=confirmed]')?.checked)throw new Error('Нужно явное согласие');await api.post('/api/v1/care-team/visibility',{doctor_a:d.doctor_a,doctor_b:d.doctor_b,allow:true});toast('Разрешение на совместный доступ сохранено');await render();break;}
 case 'confirm-clinical-decision':{if(d.confirmed!=='on')throw new Error('Требуется личное подтверждение врача');await api.post('/api/v1/p0/decisions/'+segment(form.dataset.patient),{text:d.text,explicit_confirmation:true});toast('Подтверждённое решение сохранено');await render();break;}
 case 'adverse-review':{await api.post('/api/v1/p0/adverse-events/'+segment(form.dataset.id)+'/review',{status:d.status,review_text:d.review_text});toast('Оценка сохранена');await render();break;}
 case 'edit-clinical-document':{if(d.confirmed!=='on')throw new Error('Необходимо личное подтверждение врача');const items=[...form.querySelectorAll('fieldset[data-plan-item]')].map(field=>Object.fromEntries([...field.querySelectorAll('[name]')].map(input=>[input.name,input.value])));const diagnoses=form.querySelector('[data-diagnosis-row]')?await formDiagnoses(form):[...form.querySelectorAll('[data-document-diagnosis]')].map(input=>JSON.parse(input.value));await api.put('/api/v1/clinical-workflow/documents/'+segment(form.dataset.id),{revision:Number(form.dataset.revision),mode:form.dataset.mode,content:{narrative:d.narrative||'',assessment:d.assessment||'',follow_up:d.follow_up||'',diagnoses,items}});toast('Изменения черновика сохранены сервером');await render();break;}
 case 'create-encounter':{if(d.confirmed!=='on')throw new Error('Необходимо подтверждение врача');const r=await api.post('/api/v1/clinical-workflow/patients/'+segment(form.dataset.patient)+'/documents',{kind:'encounter',mode:'quick',content:{narrative:d.narrative,assessment:'',follow_up:'',diagnoses:await formDiagnoses(form),items:[]}});toast('Черновик приёма создан. Подпишите и опубликуйте после проверки.');await render();break;}
 case 'create-treatment':{if(d.confirmed!=='on')throw new Error('Необходимо подтверждение врача');const kind=form.dataset.kind;if(!['medication','behavioral'].includes(kind))throw new Error('Неизвестный тип плана');const item={item_type:kind,title:d.title,frequency:d.frequency,duration:d.duration||'',notes:d.notes||''};if(kind==='medication'){item.dose=d.dose;item.route=d.route||'';if(d.reference_id&&d.reference_version){item.reference_id=d.reference_id;item.reference_version=d.reference_version;}}await api.post('/api/v1/clinical-workflow/patients/'+segment(form.dataset.patient)+'/documents',{kind:'treatment',mode:'quick',content:{narrative:'',assessment:'',follow_up:'',diagnoses:[],items:[item]}});toast('Черновик плана создан. Чтобы пациент увидел его, подпишите и опубликуйте.');await render();break;}
 case 'signal-review':{await api.post('/api/v1/doctor-experience/signals/'+segment(form.dataset.id)+'/review',{status:d.status,assessment:d.assessment});toast('Оценка сигнала сохранена');await render();break;}
 case 'case-message':{await api.post('/api/v1/previsit-cases/'+segment(form.dataset.id)+'/messages',{text:d.text});toast('Сообщение отправлено');await render();break;}
 case 'peer-message':{await api.post('/api/v1/threads/doctor_peer/'+segment(form.dataset.id)+'/messages',{text:d.text});toast('Сообщение отправлено');await render();break;}
 case 'offer':{await api.post('/api/v1/previsit-cases/'+segment(form.dataset.id)+'/offers',{proposed_at:new Date(d.proposed_at).toISOString(),format:d.format});toast('Предложение времени отправлено');await render();break;}
 case 'adverse':{await api.post('/api/v1/p0/adverse-events',{description:d.description});toast('Сообщение зарегистрировано');destination='/patient/treatment';break;}
 case 'assign-questionnaire':{await api.post('/api/v1/patient-experience/questionnaires/assignments',{patient_id:d.patient_id,definition_id:d.definition_id});toast('Опросник назначен');await render();break;}
 case 'create-invitation':{const categories=[...form.querySelectorAll('input[name="category"]:checked')].map(x=>x.value);if(!categories.length)throw new Error('Выберите хотя бы одну категорию.');const r=await api.post('/api/v1/onboarding/invitations',{recipient_email:d.recipient_email,categories});const el=byid('created-invitation');if(el){const inviteUrl=r.absolute_url||location.origin+'/#'+r.url;
  el.innerHTML=`<div class="notice space-top-16"><h3>Приглашение готово</h3><p>Передайте ссылку, QR-код или ключ только адресату. Вход по ссылке и регистрация с указанным email позволяют принять разрешения; связь появится после его явного согласия.</p><div class="invite-share"><div><p class="small muted">Ссылка для пациента</p><code class="break-anywhere">${esc(inviteUrl)}</code><div class="row space-top-12"><button type="button" class="btn btn-secondary btn-sm" data-command="copy-invite" data-url="${attr(inviteUrl)}">Скопировать ссылку</button></div><p class="small muted">Ключ приглашения (храните в секрете)</p><code class="break-anywhere">${esc(r.token||'')}</code></div>${r.qr_data_uri?.startsWith('data:image/svg+xml;base64,')?`<div><p class="small muted">Отсканировать QR</p><img class="invite-qr" alt="QR-код приглашения" src="${attr(r.qr_data_uri)}"></div>`:''}</div><p class="small muted">Действует до ${esc(r.expires_at||'указанного срока')}; email получателя проверяется при регистрации.</p></div>`;}toast('Приглашение создано');break;}
 case 'admin-identity-values':{await api.put('/api/v1/admin-privacy/me/values',{fields:{first_name:d.first_name||'',last_name:d.last_name||'',middle_name:d.middle_name||''}});toast('ФИО сохранено, но не раскрыто без согласия');await render();break;}
 case 'admin-identity-consent':{if(!form.querySelector('[name=confirmed]').checked)throw new Error('Нужно отдельное подтверждение.');await api.put('/api/v1/admin-privacy/me/policies/'+segment(d.organization_id),{template_id:d.template_id,confirmed:true,revision:Number(d.revision)});toast('Разрешение сохранено');await render();break;}
 case 'profile':{const payload={revision:Number(form.dataset.revision),display_name:d.display_name,bio:d.bio||'',contact_preference:d.contact_preference};if(app.session?.context?.role==='doctor'){payload.specialty_label=d.specialty_label||'';payload.public_visibility=Boolean(d.public_visibility);}const result=await api.put('/api/v1/profiles/me',payload);form.dataset.revision=result.revision;toast('Профиль сохранён');await syncSession();await render();break;}
 case 'photo':{const file=form.querySelector('input[type="file"]')?.files?.[0];if(!file)throw new Error('Выберите изображение.');if(file.size>2*1024*1024)throw new Error('Максимальный размер фотографии — 2 МБ. Уменьшите файл и повторите загрузку.');const fd=new FormData();fd.append('revision',String(form.dataset.revision));fd.append('file',file);const res=await fetch('/api/v1/profiles/me/photo',{method:'POST',headers:{'X-CSRF-Token':getCsrf()},credentials:'same-origin',body:fd});const obj=await res.json().catch(()=>({}));if(!res.ok)throw new Error(obj.error?.message||'Не удалось загрузить изображение.');toast('Фотография загружена');await render();break;}
 case 'catalog-search':{destination='/clinical-library?q='+encodeURIComponent(d.q||'')+'&type='+encodeURIComponent(d.type||'');break;}
 case 'research-synthetic-filter':{destination='/research/demo-v3?cohort='+encodeURIComponent(d.cohort||'');break;}
 case 'nlp':{if(!d.text||d.text.length>10000)throw new Error('Проверьте длину текста');const r=await api.post('/api/v1/nlp-v3/synthetic-extract',{text:d.text,synthetic:true});const el=byid('nlp-result');if(el)el.innerHTML=`${renderLabSummary(r)}`;break;}
 case 'questionnaire':await saveQuestionnaire(form,true);break;
 case 'guest-questionnaire':destination=await handleGuestSubmit(form);break;
 case 'ci-diary':case 'ci-document':case 'ci-referral':case 'ci-message':{const result=await clinicalFormAction(form,app);if(result?.message)toast(result.message);if(result?.reload)await render();if(result?.destination)destination=result.destination;break;}
 default:throw new Error('Это действие не подключено к backend.');
 }
 if(destination)navTo(destination);
 }catch(e){alertError(form,messageFor(e));}finally{stopBusy(form);}}
async function saveQuestionnaire(form,submitNow=false){const aid=form.dataset.id,answers={};for(const input of form.querySelectorAll('input[data-answer]:checked'))answers[input.name]=Number(input.value);
 const revision=Number(form.dataset.revision),version=form.dataset.version;
 const r=await api.put('/api/v1/patient-experience/questionnaires/assignments/'+segment(aid)+'/draft',{definition_version:version,revision,answers,last_page:0});const next=r.draft?.revision;if(!Number.isInteger(next))throw new Error('Сервер не подтвердил сохранение.');form.dataset.revision=next;
 if(submitNow){await api.post('/api/v1/patient-experience/questionnaires/assignments/'+segment(aid)+'/submit',{definition_version:version,revision:next,idempotency_key:'ui-'+Date.now()+'-'+Math.random().toString(36).slice(2)});navTo('/patient/questionnaires/'+segment(aid)+'/result');}
 else toast('Черновик сохранён сервером');}
async function runCommand(cmd,node){
 try{
  if(cmd==='catalog-section'){const section=document.getElementById(node.dataset.section);if(section){section.focus({preventScroll:true});section.scrollIntoView({block:'start',behavior:'instant'});}return;}
  if(cmd==='choose-reference-medication'){chooseMedication(node);toast('Название перенесено в форму. Дозу и режим определяет врач; ничего не сохранено.');return;}
  if(cmd==='menu'){menuToggle();return;}
  if(cmd==='settings'){settings();return;}
  if(cmd==='close-modal'){closeModal();return;}
  if(cmd==='retry'){await render();return;}
  if(cmd==='decline-invite'){app.invitation=null;app.inviteToken='';byid('invitation-preview').replaceChildren();toast('Приглашение не принято');return;}
  if(cmd==='next-registration'){const form=byid('register-form');const step=$('[data-wizard="1"]',form);const items=[...step.querySelectorAll('input')];if(!items.every(x=>x.reportValidity()))return;step.hidden=true;const next=$('[data-wizard="2"]',form);next.hidden=false;$('.steps span:nth-child(2)',form).classList.add('done');next.querySelector('input')?.focus();return;}
  if(cmd==='back-registration'){const form=byid('register-form');$('[data-wizard="2"]',form).hidden=true;$('[data-wizard="1"]',form).hidden=false;$('.steps span:nth-child(2)',form).classList.remove('done');return;}
  if(cmd==='logout'){
   const path=app.session?.features?.oidc_session?'/api/v1/auth/oidc/logout':'/api/v1/onboarding/logout';await api.post(path,{});app.session=null;app.invitation=null;app.inviteToken='';await syncSession();navTo('/');toast('Вы вышли из аккаунта');return;
  }
  if(cmd==='copy-link'||cmd==='copy-invite'){const txt=cmd==='copy-invite'?node.dataset.url:location.origin+'/#'+routeInfo().path.replace('/share','');if(!navigator.clipboard?.writeText)throw new Error('Буфер обмена недоступен. Скопируйте адрес из строки браузера.');await navigator.clipboard.writeText(txt);toast('Ссылка скопирована');return;}
  if(cmd==='doctor-questionnaire-result'){
   const r=await api.get('/api/v1/patient-experience/questionnaires/assignments/'+segment(node.dataset.id)+'/result');
   modal(`<p class="eyebrow">Результат заполненного опросника</p><h3>${esc(r.title||r.definition_id)}</h3><h2>${esc(r.score)} из ${esc(r.max_score)} баллов</h2><p class="small muted">${esc(r.disclaimer||'Результат без клинической интерпретации.')}</p><div class="reference-section">${(r.answers||[]).map(a=>`<p>${esc(a.label)} — ${esc(a.answer_label||a.value)} (${esc(a.value)} балл(ов))</p>`).join('')}</div>`,'Результат пациента');return;
  }
  if(cmd==='admin-identity-revoke'){if(!confirm('Отозвать разрешение администрации клиники?'))return;node.disabled=true;try{await api.delete('/api/v1/admin-privacy/me/policies/'+segment(node.dataset.org));toast('Разрешение отозвано');await render();}finally{node.disabled=false;}return;}
  if(cmd==='save-guest-assessment'){node.disabled=true;try{const dest=await syncPending(app.session);if(dest){app.pendingSaveError='';navTo(dest);}else throw new Error('Войдите под аккаунтом пациента.');}catch(e){const target=byid('guest-save-error');if(target)target.textContent=messageFor(e);else toast(messageFor(e));}finally{node.disabled=false;}return;}
  if(cmd==='start-assessment'){node.disabled=true;try{const r=await api.post('/api/v1/patient-experience/questionnaires/self-assign',{definition_id:node.dataset.id});navTo('/patient/questionnaires/'+segment(r.id));}finally{node.disabled=false;}return;}
  if(cmd==='save-questionnaire'){const f=node.closest('form');if(!startBusy(f))return;try{await saveQuestionnaire(f,false);alertError(f,'');}catch(e){alertError(f,messageFor(e));}finally{stopBusy(f);}return;}
  if(cmd==='review-request'){if(!confirm('Принять обращение к рассмотрению?'))return;node.disabled=true;try{await api.post('/api/v1/previsit-cases/'+segment(node.dataset.id)+'/review',{confirmation:true});toast('Обращение принято');await render();}finally{node.disabled=false;}return;}
  if(cmd==='confirm-appointment'){if(!confirm('Подтвердить предложенное время?'))return;node.disabled=true;try{await api.post('/api/v1/appointments/'+segment(node.dataset.id)+'/confirm',{});toast('Приём подтверждён');await render();}finally{node.disabled=false;}return;}
  if(cmd==='revoke-doctor-link'){if(!confirm('Отозвать связь с '+(node.dataset.name||'врачом')+'? Доступ этого врача к данным пациента будет прекращён.'))return;await api.delete('/api/v1/patients/me/clinical-links/'+segment(node.dataset.id));toast('Связь отозвана сервером');await render();return;}
  if(cmd==='team-visibility'){const allow=node.dataset.allow==='true';if(!confirm(allow?'Разрешить обмен между выбранными врачами?':'Отключить совместную видимость для этой пары врачей?'))return;await api.post('/api/v1/care-team/visibility',{doctor_a:node.dataset.doctorA,doctor_b:node.dataset.doctorB,allow});toast('Совместная видимость обновлена');await render();return;}
  if(cmd==='sign-document'||cmd==='publish-document'){const action=cmd==='sign-document'?'sign':'publish';if(!confirm(action==='sign'?'Подписать проверенный врачом документ?':'Опубликовать подписанный документ пациенту?'))return;await api.post('/api/v1/clinical-workflow/documents/'+segment(node.dataset.id)+'/'+action,{revision:Number(node.dataset.revision)});toast(action==='sign'?'Документ подписан врачом':'Документ опубликован пациенту');await render();return;}
  if(cmd==='read-notice'){node.disabled=true;try{await api.post('/api/v1/p0/notifications/'+segment(node.dataset.id)+'/read',{});toast('Уведомление отмечено');await render();}finally{node.disabled=false;}return;}
  if(cmd==='report-plan'){const id=node.dataset.id;modal(`<p class="muted">Выберите результат выполнения. Будет создана запись на сервере.</p><div class="row">${[['completed','Выполнено'],['missed','Пропущено'],['uncertain','Не уверен(а)'],['partial','Частично']].map(([v,l])=>`<button type="button" class="btn btn-secondary" data-command="report-outcome" data-id="${attr(id)}" data-outcome="${v}">${l}</button>`).join('')}</div>`,'Отметить выполнение');return;}
  if(cmd==='report-outcome'){node.disabled=true;try{await api.post('/api/v1/p0/plan-items/'+segment(node.dataset.id)+'/report',{outcome:node.dataset.outcome});closeModal();toast('Отметка сохранена');await render();}finally{node.disabled=false;}return;}
  if(node.dataset.commandPending)return;
  const oldContent=node.innerHTML,wasDisabled=node.disabled;
  node.dataset.commandPending='1';node.disabled=true;node.setAttribute('aria-busy','true');
  node.textContent=cmd==='ci-analyze'?'Анализируем локальной моделью…':'Обрабатываем…';
  try{
   const clinical=await clinicalCommand(cmd,node);
   if(clinical){if(clinical.message)toast(clinical.message);if(clinical.destination)navTo(clinical.destination);else if(clinical.reload)await render();return;}
   throw new Error('Действие не подключено.');
  }finally{delete node.dataset.commandPending;node.disabled=wasDisabled;node.removeAttribute('aria-busy');node.innerHTML=oldContent;}
 }catch(e){toast(messageFor(e));}}
function setupListeners(){
 document.addEventListener('click',async e=>{
  const nav=e.target.closest('a[href^="/#"]');if(nav){menuClose();return;}
  const button=e.target.closest('[data-command]');if(button){e.preventDefault();await runCommand(button.dataset.command,button);return;}
  if(e.target.matches('[data-overlay]'))closeModal();
  if(menuOpen&&!e.target.closest('#floating-root')&&!e.target.closest('#avatar-button'))menuClose();
 });
 document.addEventListener('submit',e=>{const form=e.target.closest('form[data-form]');if(!form)return;e.preventDefault();submit(form);});
 document.addEventListener('change',e=>{if(e.target.name==='diagnosis_status')onDiagnosisInput(e.target.closest('[data-diagnosis-row]').querySelector('[name=diagnosis_code]'));if(e.target.id==='theme-switch'){setTheme(e.target.checked);return;}});
 document.addEventListener('input',e=>{
  if(e.target.name==='diagnosis_code')onDiagnosisInput(e.target);
  if(e.target.id==='plan-title'){const f=e.target.form;if(f?.elements.reference_id){f.elements.reference_id.value='';f.elements.reference_version.value='';}}
  if(e.target.id==='doctor-search'){const q=e.target.value.toLocaleLowerCase('ru');document.querySelectorAll('#doctor-grid article').forEach(a=>{a.hidden=!a.textContent.toLocaleLowerCase('ru').includes(q);});}
  if(e.target.id==='patient-search'){const q=e.target.value.toLocaleLowerCase('ru');document.querySelectorAll('#patient-list .list-row').forEach(a=>{a.hidden=!a.textContent.toLocaleLowerCase('ru').includes(q);});}
 });
 document.addEventListener('click',e=>{const btn=e.target.closest('[data-period]');if(!btn)return;app.period=Number(btn.dataset.period);render();});
 window.addEventListener('hashchange',()=>{closeModal();render();window.scrollTo({top:0,behavior:'instant'});});
 window.addEventListener('popstate',()=>{closeModal();render();});
 window.addEventListener('resize',()=>{if(menuOpen)menuClose();});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&menuOpen)menuClose();});
}
try{setTheme(localStorage.getItem('cc.theme')==='dark');}catch{setTheme(false)}
setupListeners();boot();
