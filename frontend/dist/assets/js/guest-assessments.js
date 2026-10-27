import {api,segment} from './api.js';
import {esc,attr,link,state,errorState} from './ui.js';
export const GUEST_KEY='cc_pilot_guest_result_v1';
export const GUEST_CODES=['phq_9','phq_2','gad_7','gad_2'];
const heading=(h,sub='')=>`<h1 class="page-title">${esc(h)}</h1>${sub?`<p class="page-intro">${esc(sub)}</p>`:''}`;
const warning='<div class="notice warning">Учебный режим только с вымышленными ответами. Русская редакция не утверждена; сумма не является диагнозом. Не вводите реальные сведения о здоровье.</div>';
const keyFor=(code)=>'eval_'+code+'_v1';
export function readPending(){
 try {const x=JSON.parse(sessionStorage.getItem(GUEST_KEY)||'null');
  if(!x||!GUEST_CODES.includes(x.code)||!x.answers||typeof x.answers!=='object'||!Number.isInteger(x.score)||!x.key)return null;
  return x;
 }catch{return null;}
}
export function clearPending(){try{sessionStorage.removeItem(GUEST_KEY);}catch{}}
export function storePending(definition,answers){
 if(!GUEST_CODES.includes(definition.source_id))throw new Error('Недоступная форма');
 const questions=definition.questions||[],valid={};
 if(Object.keys(answers).length!==questions.length)throw new Error('Заполните все вопросы');
 for(const q of questions){const opts=(q.options||[]).map(o=>o.value);if(!Object.hasOwn(answers,q.id)||!Number.isInteger(answers[q.id])||!opts.includes(answers[q.id]))throw new Error('Проверьте ответы');valid[q.id]=answers[q.id];}
 const score=Object.values(valid).reduce((a,b)=>a+b,0),max=definition.max_score;
 if(score<definition.min_score||score>max)throw new Error('Некорректная сумма');
 const saved={code:definition.source_id,key:keyFor(definition.source_id),title:definition.title,version:definition.version,
   answers:valid,score,min_score:definition.min_score,max_score:max,
   nonce:crypto.randomUUID?crypto.randomUUID():'pilot-'+Date.now(),saved_at:new Date().toISOString()};
 try{sessionStorage.setItem(GUEST_KEY,JSON.stringify(saved));}catch{throw new Error('В этом браузере нельзя временно сохранить ответы. Используйте режим с разрешённым sessionStorage.');}
 return saved;
}
export async function syncPending(session){
 const pending=readPending();if(!pending||session?.context?.role!=='patient')return null;
 // Server validates the definition, the answers, the revision, the score, the session, and CSRF.
 // Client score is NEVER sent as the authoritative server score.
 const assigned=await api.post('/api/v1/patient-experience/questionnaires/self-assign',{definition_id:pending.key,idempotency_key:pending.nonce.slice(0,80)});
 const id=segment(assigned.id);
 const base='/api/v1/patient-experience/questionnaires/assignments/'+id;
 const current=await api.get(base);
 if(current.assignment?.status==='submitted'){
   // Never overwrite another result. Return that exact server object.
   const result=await api.get(base+'/result');
   if(JSON.stringify(Object.keys(pending.answers).sort().map(k=>[k,pending.answers[k]]))!==
     JSON.stringify(Object.keys(result.answers.reduce((a,x)=>(a[x.question_id]=x.value,a),{})).sort().map(k=>[k,result.answers.find(a=>a.question_id===k)?.value])))
       throw new Error('Найден уже завершённый опросник. Проверьте историю, затем сохраните новый отдельно.');
   clearPending();return '/patient/questionnaires/'+id+'/result';
 }
 const draft=await api.put(base+'/draft',{definition_version:current.assignment.definition_version,
     revision:current.draft.revision,answers:pending.answers,last_page:0});
 const r=await api.post(base+'/submit',{definition_version:current.assignment.definition_version,
   revision:draft.draft.revision,idempotency_key:pending.nonce.slice(0,80)});
 if(r.score!==pending.score)throw new Error('Сервер вычислил отличающийся результат; сохранение требует проверки.');
 clearPending();return '/patient/questionnaires/'+id+'/result';
}
export async function guestPage(path,app){
 let data;
 try{data=await api.get('/api/v1/evaluation/questionnaires/public-definitions');}
 catch(e){return heading('Пилотные опросники')+`<section class="card">${errorState(e)}</section>`;}
 const defs=data.items||[];
 const code=path.split('/')[2],resultPath=path.endsWith('/result');
 if(!code)return heading('Опросники для демонстрации','Можно пройти без регистрации и увидеть предварительную сумму, а затем сохранить в профиле.')+warning+
 `<section class="card">${defs.map(d=>`<div class="list-row"><div class="row-main"><h3>${esc(d.title)}</h3><p class="small muted">${d.questions.length} вопросов · сумма ${d.min_score}–${d.max_score}</p></div>${link('/assessments/'+segment(d.source_id),'Пройти','primary')}</div>`).join('')}</section>`;
 const def=defs.find(d=>d.source_id===code);
 if(!def)return heading('Опросник не найден')+link('/assessments','К списку опросников');
 if(resultPath){const saved=readPending();if(!saved||saved.code!==code)return heading('Нет результата')+warning+link('/assessments/'+code,'Заполнить опросник','primary');
  return heading('Результат: '+def.title)+warning+`<section class="card"><p class="eyebrow">Предварительный локальный результат · ещё не сохранён в профиль</p><h2>${saved.score} из ${saved.max_score} баллов</h2><p>Сумма ответов без диагностической интерпретации.</p><p class="small muted">Временные ответы хранятся только в текущей вкладке браузера до закрытия вкладки или успешного переноса в аккаунт.</p><div class="row">${app.session?.context?.role==='patient'?`<button class="btn btn-primary" data-command="save-guest-assessment">Сохранить в мой профиль</button>`:!app.session?`${link('/login','Войти и сохранить','primary')}${link('/register/patient','Зарегистрироваться и сохранить','secondary')}`:'<p>Для сохранения требуется аккаунт пациента. Выйдите из текущей роли и войдите как пациент.</p>'}${link('/assessments','Другие опросники','secondary')}</div><p id="guest-save-error" class="error-inline" role="alert">${esc(app.pendingSaveError||'')}</p><h3>Ответы</h3>${def.questions.map(q=>`<div class="list-row"><span>${esc(q.label)}</span><strong>${esc(q.options.find(o=>o.value===saved.answers[q.id])?.label||'—')}</strong></div>`).join('')}</section>`;
 }
 return heading(def.title,'Заполните вопросы и посмотрите предварительный результат без входа.')+warning+
 `<section class="card"><form data-form="guest-questionnaire" data-code="${attr(code)}" class="form-stack">${def.questions.map((q,i)=>`<fieldset class="field bare-fieldset"><legend class="question-legend">${i+1}. ${esc(q.label)}</legend><div class="row">${q.options.map(o=>`<label class="chip"><input type="radio" required data-guest-answer="true" name="${attr(q.id)}" value="${attr(o.value)}"> ${esc(o.label)}</label>`).join('')}</div></fieldset>`).join('')}<p class="error-inline" data-form-error role="alert"></p><div class="row"><button type="submit" class="btn btn-primary">Посмотреть результат</button>${link('/assessments','Назад','secondary')}</div></form></section>`;
}
export async function handleGuestSubmit(form){
 const code=form.dataset.code,definitions=await api.get('/api/v1/evaluation/questionnaires/public-definitions');
 const def=definitions.items.find(d=>d.source_id===code);if(!def)throw new Error('Форма недоступна');
 const answers={};for(const x of form.querySelectorAll('[data-guest-answer]:checked'))answers[x.name]=Number(x.value);
 storePending(def,answers);return '/assessments/'+code+'/result';
}
