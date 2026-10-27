import {api} from './api.js';
const form=document.getElementById('request-form');const output=document.getElementById('response');
const allowlist=new Set(['/api/v1/health','/api/v1/onboarding/bootstrap','/api/v1/p0/auth/capabilities','/api/v1/public/doctors','/api/v1/clinical-catalog/search']);
form.addEventListener('submit',async e=>{e.preventDefault();const endpoint=form.elements.endpoint.value;if(!allowlist.has(endpoint))return;const btn=form.querySelector('button');btn.disabled=true;output.textContent='Загрузка…';try{let data=await api.get(endpoint);if(data&&typeof data==='object'){const d=structuredClone(data);delete d.csrf_token;data=d;}output.textContent=JSON.stringify(data,null,2);}catch(err){output.textContent=err.message;}finally{btn.disabled=false;}});
try{document.documentElement.dataset.theme=localStorage.getItem('cc.theme')==='dark'?'dark':'light';}catch{}
