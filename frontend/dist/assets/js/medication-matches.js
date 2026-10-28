import {api} from './api.js';
import {esc,attr,errorState} from './ui.js';

export function diagnosisFields(diagnoses=[]){
 const rows=[...diagnoses.slice(0,20)];if(rows.length<20)rows.push({});
 return `<fieldset><legend>Диагнозы, введённые врачом</legend><p class="small muted">Точный код МКБ-10. Совпадения с инструкциями — справочные варианты для рассмотрения, не назначение. Очистите код, чтобы убрать диагноз из черновика.</p>${rows.map(d=>`<div data-diagnosis-row data-original-code="${attr(d.code||'')}" data-original-version="${attr(d.version||'')}" class="space-top-12"><label class="field">Код диагноза<input name="diagnosis_code" maxlength="32" value="${attr(d.code||'')}" placeholder="Например: F41.1" autocomplete="off"></label><label class="field">Статус диагноза<select name="diagnosis_status"><option value="preliminary" ${d.status!=='confirmed'?'selected':''}>Предварительный</option><option value="confirmed" ${d.status==='confirmed'?'selected':''}>Подтверждён врачом</option></select></label><div data-diagnosis-matches aria-live="polite"></div></div>`).join('')}</fieldset>`;
}

async function exactDiagnosis(code){
 const result=await api.get('/api/v1/clinical-workflow/icd10?q='+encodeURIComponent(code));
 const item=result.items.find(x=>x.code===code);
 if(!item)throw new Error('Код не найден в доступном справочнике МКБ-10. Уточните код или очистите поле.');
 return {code:item.code,version:result.version};
}
export async function formDiagnoses(form){
 const diagnoses=[];
 for(const row of form.querySelectorAll('[data-diagnosis-row]')){
  const input=row.querySelector('[name=diagnosis_code]'),code=input.value.trim().toUpperCase();
  if(!code)continue;
  if(diagnoses.some(x=>x.code===code))throw new Error('Один код диагноза указан несколько раз.');
  const diagnosis=code===row.dataset.originalCode&&row.dataset.originalVersion?{code,version:row.dataset.originalVersion}:await exactDiagnosis(code);
  diagnoses.push({...diagnosis,status:row.querySelector('[name=diagnosis_status]').value});
 }
 return diagnoses;
}
export function matchingCards(data,diagnosis,selectable=false){
 return `<div class="space-top-12"><h3>Препараты по диагнозу ${esc(diagnosis.code)}</h3><p class="small muted">${esc(data.label)} · ${diagnosis.status==='confirmed'?'диагноз подтверждён врачом':'предварительная формулировка врача'}. ${esc(data.limitation)}</p>${data.items.length?[...data.items].sort((a,b)=>a.reference.title.localeCompare(b.reference.title,'ru')).map(({reference:r,rule})=>`<article class="card inset"><h4>${esc(r.title)}</h4><p>Основание: ${esc(rule.code)} — ${esc(rule.match_basis)}</p><p class="small muted">Совпадение с кодом в исходной инструкции. Возраст, противопоказания, взаимодействия и пригодность для пациента проверяет врач.</p><div class="row"><a class="btn btn-secondary" href="/#/clinical-library?type=medicine&item=${attr(encodeURIComponent('medicine:product:'+r.id))}">Открыть ${esc(r.title)} в справочнике</a>${selectable?`<button type="button" class="btn btn-secondary" data-command="choose-reference-medication" data-title="${attr(r.title)}" data-reference="${attr(r.id)}" data-version="${attr(r.version)}">Выбрать ${esc(r.title)} для черновика</button>`:''}</div></article>`).join(''):'<p>Точных справочных совпадений нет. Врач может заполнить план самостоятельно.</p>'}</div>`;
}
export async function savedMedicationMatches(documents){
 const diagnoses=[];
 for(const doc of documents.filter(d=>d.kind==='encounter'&&['draft','signed','published'].includes(d.status))){
  for(const d of doc.content?.diagnoses||[])if(!diagnoses.some(x=>x.code===d.code&&x.version===d.version))diagnoses.push(d);
 }
 if(!diagnoses.length)return '<p class="small muted">Для подбора справочных вариантов сохраните структурированный диагноз в записи приёма.</p>';
 return (await Promise.all(diagnoses.map(async d=>{
  try{return matchingCards(await api.get('/api/v1/references/matches?code='+encodeURIComponent(d.code)+'&version='+encodeURIComponent(d.version)),d,true);}
  catch(e){return errorState(e);}
 }))).join('');
}
export function onDiagnosisInput(input){
 const row=input.closest('[data-diagnosis-row]');if(!row)return;
 const target=row.querySelector('[data-diagnosis-matches]'),code=input.value.trim().toUpperCase();
 const generation=(row._diagnosisGeneration||0)+1;row._diagnosisGeneration=generation;clearTimeout(row._diagnosisTimer);target.textContent='';
 if(!code)return;
 row._diagnosisTimer=setTimeout(async()=>{
  try{
   const d=await exactDiagnosis(code);const data=await api.get('/api/v1/references/matches?code='+encodeURIComponent(code)+'&version='+encodeURIComponent(d.version));
   if(row.isConnected&&row._diagnosisGeneration===generation)target.innerHTML=matchingCards(data,{...d,status:row.querySelector('[name=diagnosis_status]').value});
  }catch(e){if(row.isConnected&&row._diagnosisGeneration===generation)target.innerHTML=errorState(e);}
 },350);
}
export function chooseMedication(node){
 const form=document.querySelector('form[data-form=create-treatment][data-kind=medication]');
 if(!form)throw new Error('Откройте раздел лечения пациента.');
 form.elements.title.value=node.dataset.title;form.elements.reference_id.value=node.dataset.reference;form.elements.reference_version.value=node.dataset.version;
 form.scrollIntoView({block:'center'});form.elements.title.focus();
}
