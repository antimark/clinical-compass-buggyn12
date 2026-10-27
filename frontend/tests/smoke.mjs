/** Dependency-free model smoke test: synthetic fixtures only; no live Flask requests. */
import {readFileSync} from 'node:fs';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {resolve,dirname,join} from 'node:path';
const src=resolve(dirname(fileURLToPath(import.meta.url)), '..', 'dist')+'/';
const routes=JSON.parse(readFileSync(src+'assets/data/routes.json','utf8'));
const index=readFileSync(src+'index.html','utf8');
for (const filename of ['assets/css/system.css','assets/css/layout.css','assets/css/components.css','assets/js/main.js','assets/js/views.js','assets/js/api.js','assets/js/ui.js','assets/data/routes.json']) {
  if (!readFileSync(src+filename).length) throw new Error('Empty required asset: '+filename);
}
if (/\<script[^>]*\>(?!\s*\<\/script)/i.test(index) || !index.includes('Content-Security-Policy')) throw new Error('Unexpected CSP or inline scripts');
if (routes.length < 98 || new Set(routes.map(r=>r.path)).size!==routes.length) throw new Error('Unexpected route count or duplicates');
globalThis.location={origin:'http://test.local',hash:'#/clinical-library',search:'',pathname:'/'};
globalThis.fetch=async(url)=>{let data={error:{message:'Forbidden'}};let status=403;if(String(url).includes('public/doctors')){status=200;data={items:[],name:'Врач',id:'doc_psy',reviews:[]}}else if(String(url).includes('clinical-catalog/search')){status=200;data={items:[],total:0,source_version:'v5'}};return {ok:status===200,status,headers:new Headers({'content-type':'application/json'}),json:async()=>data};};
const mod=await import(pathToFileURL(src+'assets/js/views.js').href);
// Navigation contract: the brand follows the logged-in role; logout returns to public home.
const guestHead=mod.chrome(null,'synthetic_dev','/').head;
if (!guestHead.includes('class="brand" href="/#/"') || !guestHead.includes('aria-label="Clinical Compass — главная"')) {
  throw new Error('Guest brand must lead to the public home page');
}
for(const [role,home] of Object.entries(mod.roleHomes)){
  const session={context:{role},user:{display_name:'Test'},features:{}};
  const header=mod.chrome(session,'synthetic_dev',home).head;
  if(!header.includes(`class="brand" href="/#${home}"`) || !header.includes('aria-label="Clinical Compass — кабинет"')){
    throw new Error(`Brand must lead to ${role} dashboard (${home})`);
  }
  for(const env of ['synthetic_dev','evaluation_sandbox','production']){
    const menu=mod.accountMenu(session,env);
    if(menu.includes('Мой кабинет') || menu.includes('Начать тестирование')){
      throw new Error(`Redundant menu links remain for ${role} in ${env}`);
    }
    if(!menu.includes('Выйти') || !menu.includes('Настройки')){
      throw new Error(`Required menu actions missing for ${role} in ${env}`);
    }
  }
}
for(const session of [null,{context:{role:'patient'}},{context:{role:'doctor'}}]){
  const html=mod.landing({session});
  if(html.includes('Перейти в кабинет'))throw new Error('Public landing must never show the dashboard CTA');
}
// Public landing presentation contract: new copy, three informational role cards, no buttons.
const landing=mod.landing({session:null});
for(const phrase of ['Лечение не ограничивается сеансами','Пространство, где пациент, специалист и команда клиники находятся на связи.','Пациенту','Специалисту','Исследователю']){
  if(!landing.includes(phrase))throw new Error('Missing home copy: '+phrase);
}
for(const removed of ['Поддержка между визитами','Как устроена платформа','Между приёмами — тоже часть лечения','Справочные материалы']){
  if(landing.includes(removed))throw new Error('Old home copy persists: '+removed);
}
const roleTiles=landing.match(/<article class="action-tile role-tile">[\s\S]*?<\/article>/g)||[];
if(roleTiles.length!==3 || roleTiles.some(html=>/<a\b|<button\b/.test(html))) {
  throw new Error('Role cards must be exactly three non-interactive information cards');
}
if((landing.match(/class="btn btn-secondary tile-action"/g)||[]).length!==2) {
  throw new Error('Only the two primary hero tiles retain their CTA buttons');
}
const mainJs=readFileSync(src+'assets/js/main.js','utf8');
if(!/if\(cmd==='logout'\)[\s\S]*?navTo\('\/'\)/.test(mainJs)){
  throw new Error('Logout must navigate to the public home page');
}
console.log('navigation contract passed: guest, 5 roles, 3 environments, home and logout');
let errors=[];
for(const r of routes){
  const path=r.path.replace(/:([A-Za-z]+)/g,'abc');
  location.hash='#'+path;
  const app={session:r.role==='shared'?null:{context:{role:({clinic:'clinic_admin',research:'researcher'}[r.role]||r.role)},user:{id:'test',display_name:'Test'},features:{}},bootstrap:{boot:{enabled:true},oidc:{enabled:false}},period:30};
  let p={};const names=[...r.path.matchAll(/:([A-Za-z]+)/g)].map(x=>x[1]);names.forEach(n=>p[n]='abc');
  try{let html=await mod.resolveView(r,path,p,app);if(typeof html!=='string'||!html.trim())errors.push([path,'empty content']);else if(html.indexOf('undefined')>0){} }
  catch(e){errors.push([path,e.stack]);}
}
console.log('routes rendered',routes.length,'errors',errors.length);
for(const e of errors)console.log(e[0],e[1]);
if(errors.length)process.exitCode=1;

const fixtures={
 '/api/v1/public/doctors':{items:[{id:'doc_psy',name:'Петров Иван',slug:'doc_psy',specialty:'Психиатр',verified:'synthetic_demo'}]},
 '/api/v1/public/doctors/doc_psy':{id:'doc_psy',name:'Петров Иван',specialty:'Психиатр',bio:'Демо',verified:'synthetic_demo',education:[],certificates:[],publications:[],reviews:[]},
 '/api/v1/patient-experience/dashboard':{patient:{display_name:'Тест Пациент'},assignments:[{id:'a1',definition_id:'demo_10_v1',status:'assigned'}],series:[{label:'Самочувствие',unit:'points',points:[{value:2,observed_at:'2026-10-25T12:00:00Z',source:'test'}]}],appointments:[{id:'apt1',proposed_at:'2026-11-05T12:00:00Z',status:'offered'}],links:[{id:'doc_psy',display_name:'Петров',specialty:'Психиатр'}]},
 '/api/v1/patient-experience/questionnaires/assignments':{items:[{id:'a1',status:'assigned',definition_id:'demo_10_v1'}]},
 '/api/v1/patient-experience/questionnaires/assignments/a1':{assignment:{status:'assigned',definition_version:'1'},draft:{revision:0,answers:{}},definition:{title:'Демо',questions:[{id:'q1',label:'Вопрос 1'}],options:[1,2,3,4],disclaimer:'Демо'}},
 '/api/v1/patient-experience/questionnaires/assignments/a1/result':{score:3,max_score:4,disclaimer:'Демо',answers:[{label:'Вопрос 1',value:3}]},
 '/api/v1/patient-experience/chart':{series:[{label:'Самочувствие',unit:'points',points:[{value:3,observed_at:'2026-10-25T12:00:00Z'}]}]},
 '/api/v1/p0/care-plans':{items:[{title:'План',status:'active',items:[{id:'x',title:'Задание',frequency:'Каждый день'}]}]},
 '/api/v1/appointments':{items:[{id:'apt1',proposed_at:'2026-11-05T12:00:00Z',status:'offered',format:'video'}]},
 '/api/v1/patients/me/links':{items:[{id:'doc_psy',display_name:'Иван',specialty:'Психиатр'}]},
 '/api/v1/patient/care-team-visibility':{items:[]},
 '/api/v1/previsit-cases':{items:[{id:'c1',created_at:'2026-10-25',status:'submitted'}]},
 '/api/v1/previsit-cases/c1':{id:'c1',status:'submitted',intake:{text:'Текст обращения'},created_at:'2026-10-25'},
 '/api/v1/previsit-cases/c1/messages':{items:[]},
 '/api/v1/doctor-experience/dashboard':{doctor:{display_name:'Врач'},counters:{patients:1,cases:1,attention:2,appointments:0},warnings:[{id:'s1',patient_name:'Пациент',title:'Сигнал',status:'open'}],cases:[{id:'c1',patient_name:'Пациент',created_at:'2026-10-25'}],appointments:[]},
 '/api/v1/doctors/me/patients':{items:[{id:'p1',display_name:'Тестовый пациент',attention_level:'routine'}]},
 '/api/v1/doctors/me/patients/p1/overview':{display_name:'Тестовый пациент',trend:'routine'},
 '/api/v1/doctor-experience/signals':{items:[]},
 '/api/v1/profiles/me':{display_name:'Врач',bio:'bio',revision:1,contact_preference:'in_app',photo_url:null,public_visibility:false,role:'doctor'},
 '/api/v1/clinical-catalog/search':{items:[{id:'F32',kind:'diagnosis',title:'Справочная запись',code:'F32'}],total:1,source_version:'v5'},
 '/api/v1/clinical-catalog/diagnosis/F32':{title:'Справочная запись',kind:'diagnosis',id:'F32',source_version:'v5',reference_sections:[{title:'Источники',items:['Ссылка']}]},
 '/api/v1/onboarding/invitations':{items:[]},
 '/api/v1/patient-experience/questionnaires/definitions':{items:[]},
 '/api/v1/research-workflow/definitions':{items:[]},
 '/api/v1/research-workflow/sources':{items:[]},
 '/api/v1/p0/clinic/patients':{items:[]},
 '/api/v1/p1/clinic/staff':{items:[]},
};
globalThis.fetch=async(url)=>{const key=decodeURIComponent(String(url).split('?')[0]);const d=fixtures[key];return {ok:Boolean(d),status:d?200:404,headers:new Headers({'content-type':'application/json'}),json:async()=>d||{error:{message:'Not found'}}};};
const {resolveView}=mod;
const cases=[
 ['/',null],['/doctors',null],['/doctors/doc_psy',null],['/clinical-library',null],
 ['/patient','patient'],['/patient/tasks','patient'],['/patient/trends','patient'],['/patient/treatment','patient'],['/patient/appointments','patient'],['/patient/specialists','patient'],['/patient/requests','patient'],['/patient/requests/c1','patient'],['/patient/requests/c1/chat','patient'],['/patient/questionnaires/a1','patient'],['/patient/questionnaires/a1/result','patient'],
 ['/doctor','doctor'],['/doctor/patients','doctor'],['/doctor/patients/p1','doctor'],['/doctor/alerts','doctor'],['/doctor/requests','doctor'],['/doctor/requests/c1','doctor'],['/doctor/appointments','doctor'],['/doctor/profile/edit','doctor'],
 ['/clinic','clinic_admin'],['/research','researcher']
];
let fails=[];
for(const [path,role] of cases){location.hash='#'+path;const params={requestId:path.split('/').includes('c1')?'c1':'a1',slug:'doc_psy',patientId:'p1'};const r={path,title:path,role:'shared'};const app={session:role?{user:{id:'u1',display_name:'Tester'},context:{role},features:{}}:null,bootstrap:{boot:{enabled:true},oidc:{enabled:false}},period:30};
 try{const html=await resolveView(r,path,params,app);if(typeof html!=='string'||!html.includes('h1'))fails.push([path,'missing h1']);if(html.includes('NaN'))fails.push([path,'NaN in html']);}
 catch(e){fails.push([path,e.stack]);}
}
console.log('tested',cases.length,'passed',cases.length-fails.length,'errors',fails.length);fails.forEach(x=>console.log(...x));if(fails.length)process.exitCode=1;
