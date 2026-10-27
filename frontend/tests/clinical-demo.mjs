/** Deterministic API-contract rendering tests. NOT a real Flask/browser E2E. */
import {pathToFileURL,fileURLToPath} from 'node:url';
import {resolve,dirname} from 'node:path';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../dist/assets/js');
let calls=[];
const fixture={
 '/api/v1/doctors/me/patients':{items:[{id:'p1',display_name:'Учебный пациент'}]},
 '/api/v1/clinical-intelligence/capabilities':{enabled:true},
 '/api/v1/clinical-intelligence/patients/p1/sources':{items:[{encounter_ref:'c1',source_type:'intake',created_at:'2026-10-01T10:00:00Z'}]},
 '/api/v1/clinical-intelligence/patients/p1/snapshot':{analysis_status:'ready',source_revision:1,source_version:'abc123',mode:'local_llm',tags:[{code:'anxiety',label:'Тревожные переживания',suggestion_id:'tag_1',evidence_refs:['ev1']}],evidence:[{id:'ev1',quote:'тревога'}],draft_suggestions:[{text:'Симптомы тревоги по источнику'}],permissions:{can_review:true}},
 '/api/v1/clinical-intelligence/patients/p1/proposals':{source_version:'abc123',grant_version:'grant123',evidence:[{id:'ev1',quote:'тревога'}],proposals:[{type:'referral',title:'Рассмотреть консультацию психиатра',urgency:'planned',category:'desired',rationale:'Учебное правило',catalog_links:[]}]},
 '/api/v1/clinical-intelligence/patients/p1/reviews':{items:[{suggestion_id:'tag_1',review:{revision:0,status:'pending'}}]},
 '/api/v1/clinical-workflow/patients/p1/documents':{items:[]},
 '/api/v1/clinical-intelligence/patients/p1/referrals':{items:[]},
 '/api/v1/clinical-intelligence/patients/p1/threads':{items:[],source_version:'abc123',grant_version:'grant123'},
 '/api/v1/clinical-intelligence/patient-chat/sources':{patient_ref:'p1',items:[{title:'Личный дневник',source_id:'pd1',source_type:'diary',source_version:'abc123',grant_version:'grant123'}]},
 '/api/v1/clinical-intelligence/threads/t1':{id:'t1',patient_ref:'p1',case_ref:'c1',audience:'patient',revision:2,source_version:'abc123',grant_version:'grant123',context_preview:{description:'Личная запись'},messages:[{role:'user',content:'Что выделено?'},{role:'assistant',content:'Тревожность в тексте'}],jobs:[]}
};
globalThis.location={origin:'http://test.local',hash:'#/doctor/patients/p1/clinical-intelligence?case=c1',search:'',pathname:'/'};
globalThis.fetch=async(path,init={})=>{
  const url=String(path),p=url.split('?')[0];calls.push({path:url,method:init.method||'GET',data:init.body?JSON.parse(init.body):null});
  const val=(init.method||'GET')==='GET'?fixture[p]:(p.endsWith('/snapshot')?fixture['/api/v1/clinical-intelligence/patients/p1/snapshot']:{id:'saved',revision:1,analysis_status:'ready'});
  return {ok:!!val,status:val?200:404,headers:new Headers({'content-type':'application/json'}),json:async()=>val||{error:{message:'Not found'}}};
};
const c=await import(pathToFileURL(root+'/clinical-demo.js').href);
const assert=(condition,msg)=>{if(!condition)throw new Error(msg);};
const hub=await c.doctorClinicalHub();assert(hub.includes('Учебный пациент')&&hub.includes('Разобрать обращение'),'hub lacks patient link');
const html=await c.doctorClinicalCase('p1');
for(const s of ['Тревожные переживания','тревога','Сохранить черновик в медицинскую карту','Зафиксировать решение','Новый чат','Рассмотреть консультацию психиатра'])assert(html.includes(s),'missing '+s);
assert(html.includes('data-command="ci-review"'),'clinician review controls absent');
assert(html.includes('Симптомы тревоги по источнику'),'AI chart proposal not transferred into preview');
const assistant=await c.patientAssistant();assert(assistant.includes('Создать запись')&&assistant.includes('Личный дневник'),'patient personal context absent');
const chat=await c.chatView('/patient/assistant/thread/t1',true);assert(chat.includes('Тревожность в тексте')&&chat.includes('Отправить вопрос'),'patient chat messages missing');
const summary=c.renderLabSummary({mode:'deterministic_mock',data:{facts:[{tag_code:'anxiety',evidence:{quote:'тревога'},assertion:'asserted',temporality:'current'}]}});
assert(summary.includes('Тревожные переживания')&&summary.includes('тревога'),'laboratory must show evidence');
const orig=globalThis.FormData;
globalThis.FormData=class {constructor(form){this.form=form;} entries(){return Object.entries(this.form.values);}};
try{
 const form={dataset:{form:'ci-document',patient:'p1'},values:{narrative:'Тестовая запись врачом проверена',confirmed:'on'}};
 const saved=await c.clinicalFormAction(form);
 assert(saved.reload&&saved.message.includes('Черновик'),'document save confirmation absent');
 let call=calls.at(-1);assert(call.method==='POST'&&call.path.endsWith('/patients/p1/documents'),'wrong chart draft endpoint');
 assert(call.data.kind==='encounter'&&call.data.content.narrative==='Тестовая запись врачом проверена','wrong draft payload');
 const referral={dataset:{form:'ci-referral',patient:'p1',case:'c1',source:'abc123',grant:'grant123'},values:{confirmed:'on',target_specialty:'psychiatrist',category:'desired',urgency:'planned',clinical_reason:'Самостоятельное решение'}};
 await c.clinicalFormAction(referral);
 call=calls.at(-1);assert(call.data.authority==='manual_physician'&&call.data.confirmed===true&&call.data.decision==='create','referral not physician-confirmed');
 const diary={dataset:{form:'ci-diary'},values:{content:'Дневник без идентификаторов',confirmed:'on'}};
 await c.clinicalFormAction(diary);call=calls.at(-1);assert(call.path.endsWith('/patient-chat/diary')&&call.data.confirmed,'diary incorrect');
 const approved=await c.clinicalCommand('ci-review',{dataset:{id:'tag_1',source:'abc123',revision:'0',correctness:'supported'}});
 call=calls.at(-1);assert(approved.reload&&call.data.correctness==='supported'&&call.data.relevance==='relevant','tag review request incorrect');
 const thread=await c.clinicalCommand('ci-patient-thread',{dataset:{patient:'p1',case:'pd1',type:'diary',source:'abc123',grant:'grant123'}});
 call=calls.at(-1);assert(thread.destination.startsWith('/patient/assistant/thread/')&&call.data.source_type==='diary','patient thread incorrect');
}finally{globalThis.FormData=orig;}
console.log('Clinical Intelligence model UI and API payload contract passed ('+calls.length+' simulated HTTP requests; no Flask runtime).');
