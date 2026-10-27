/* Model-contract test: synthetic definitions and simulated HTTP (not Flask E2E). */
import {strict as assert} from 'node:assert';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {storePending,readPending,clearPending,syncPending,GUEST_CODES} from '../dist/assets/js/guest-assessments.js';
const base=resolve('../clinical_catalog_data/v5/catalog/instruments');
const storage=new Map();
globalThis.sessionStorage={getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
const defs=GUEST_CODES.map(code=>{
 const raw=JSON.parse(readFileSync(base+'/'+code+'.json','utf8'));
 const questions=raw.questions.map(q=>({id:q.id,label:q.text,options:q.options.map(o=>({value:o.score,label:o.label}))}));
 return {source_id:code,id:'eval_'+code+'_v1',version:raw.instrument_version,title:code,
  min_score:raw.scoring.min_score,max_score:raw.scoring.max_score,questions};
});
for(const def of defs){
 const zero=Object.fromEntries(def.questions.map(q=>[q.id,0]));
 const max=Object.fromEntries(def.questions.map(q=>[q.id,3]));
 assert.equal(storePending(def,zero).score,def.min_score);
 assert.equal(storePending(def,max).score,def.max_score);
 assert.equal(readPending().code,def.source_id);
 assert.throws(()=>storePending(def,Object.fromEntries(def.questions.slice(1).map(q=>[q.id,3]))));
 assert.throws(()=>storePending(def,{...zero,[def.questions[0].id]:99}));
 clearPending();
}
const def=defs[0],values=Object.fromEntries(def.questions.map(q=>[q.id,2]));
const pending=storePending(def,values);
const saved=[];
let revision=0;
globalThis.fetch=async(path,options={})=>{
 const method=options.method||'GET',data=options.body?JSON.parse(options.body):null;
 const prefix='/api/v1/patient-experience/questionnaires/assignments/';
 saved.push({method,path,data});let payload=null;
 if(path.endsWith('/self-assign'))payload={id:'dq_test'};
 else if(path===prefix+'dq_test')payload={assignment:{status:'assigned',definition_version:def.version},draft:{revision}};
 else if(path.endsWith('/draft')){assert.deepEqual(data.answers,values);assert.equal(data.revision,0);payload={draft:{revision:++revision}};}
 else if(path.endsWith('/submit')){assert.equal(data.revision,1);payload={score:pending.score};}
 return {ok:!!payload,status:payload?200:404,headers:new Headers({'content-type':'application/json'}),json:async()=>payload||{error:{message:'missing'}}};
};
const location=await syncPending({context:{role:'patient'}});
assert.equal(location,'/patient/questionnaires/dq_test/result');
assert.equal(readPending(),null);
assert.deepEqual(saved.map(s=>s.method),['POST','GET','PUT','POST']);
storePending(def,values);
assert.equal(await syncPending({context:{role:'doctor'}}),null);
assert.notEqual(readPending(),null);
clearPending();
console.log('4 questionnaire guest score ranges, partial validation, synthetic server-save handshake passed (HTTP simulated).');
