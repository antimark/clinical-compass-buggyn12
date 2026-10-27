/* Whitelisted icons and HTML-escaped data projections. */
const paths={
 compass:'<circle cx="12" cy="12" r="9"/><path d="m16.3 7.7-2.7 5.9-5.9 2.7 2.7-5.9z"/>',
 arrow:'<path d="M5 12h14m-7-7 7 7-7 7"/>',left:'<path d="M19 12H5m7 7-7-7 7-7"/>',
 chevron:'<path d="m9 18 6-6-6-6"/>',down:'<path d="m6 9 6 6 6-6"/>',
 user:'<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',users:'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
 search:'<circle cx="11" cy="11" r="7"/><path d="m16 16 5 5"/>', plus:'<path d="M12 5v14M5 12h14"/>',
 calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/>',
 clipboard:'<rect x="5" y="4" width="14" height="18" rx="2"/><path d="M9 4.5V3h6v1.5M9 11h6m-6 4h6"/>',
 chart:'<path d="M3 3v18h18M6 16l5-5 4 3 5-8"/>', heart:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8z"/>',
 shield:'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
 book:'<path d="M4 4h7a4 4 0 0 1 4 4v13a4 4 0 0 0-4-4H4zM20 4h-1a4 4 0 0 0-4 4v13a4 4 0 0 1 4-4h1z"/>',
 mail:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
 message:'<path d="M21 11a8 8 0 0 1-8 8H5l-3 3v-8a8 8 0 1 1 19-3z"/>',
 check:'<path d="m5 12 5 5 9-10"/>',x:'<path d="M18 6 6 18M6 6l12 12"/>',
 settings:'<path d="M12 2v3m0 14v3M2 12h3m14 0h3M4.9 4.9l2.1 2.1m10 10 2.1 2.1M19.1 4.9 17 7m-10 10-2.1 2.1"/><circle cx="12" cy="12" r="4"/>',
 logout:'<path d="M9 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h4M16 17l5-5-5-5m5 5H9"/>',
 bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
 clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/>',
 warning:'<path d="m12 3 10 18H2zM12 9v5m0 3h.01"/>',
 info:'<circle cx="12" cy="12" r="10"/><path d="M12 11v5m0-9h.01"/>',
 star:'<path d="m12 2 3.1 6.4 7 .9-5.1 5 .9 7-5.9-3.3-5.9 3.3.9-7-5.1-5 7-.9z"/>',
 external:'<path d="M14 3h7v7m0-7-11 11"/><path d="M21 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h6"/>',
 copy:'<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
 flask:'<path d="M9 3h6m-5 0v7l-6 9a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3l-6-9V3M7 16h10"/>',
 refresh:'<path d="M20 11a8 8 0 0 0-15-4L3 9m0-6v6h6M4 13a8 8 0 0 0 15 4l2-2m0 6v-6h-6"/>',
 lock:'<rect x="4" y="10" width="16" height="12" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
 activity:'<path d="M2 12h4l3-8 6 16 3-8h4"/>',
 upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 17v4h16v-4"/>',
 file:'<path d="M6 2h8l5 5v15H6zM14 2v6h5M9 13h7M9 17h7"/>',
 spark:'<path d="m12 2 2.2 7.8L22 12l-7.8 2.2L12 22l-2.2-7.8L2 12l7.8-2.2z"/>'
};
export function icon(name='info',size=20){return `<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths[name]||paths.info}</svg>`;}
export function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
export function attr(v){return esc(v);}
export function link(path,label,variant='secondary',iconName=''){return `<a class="btn btn-${variant}" href="/#${attr(path)}">${iconName?icon(iconName):''}${esc(label)}</a>`;}
export function button(label,act,variant='secondary',extra=''){return `<button type="button" class="btn btn-${variant}" data-command="${attr(act)}" ${extra}>${esc(label)}</button>`;}
export function state(title,description,kind='empty',action=''){return `<div class="state ${kind==='error'?'danger':''}"><div class="state-icon">${icon(kind==='error'?'warning':kind==='loading'?'clock':kind==='forbidden'?'lock':'info')}</div><h3>${esc(title)}</h3><p>${esc(description)}</p>${action}</div>`;}
export function errorState(e){const code=e?.status||0;return state(code===403?'Доступ ограничен':code===404?'Материал не найден':code===401?'Нужен вход':'Не удалось загрузить данные',e?.message||'Попробуйте ещё раз.',code===403?'forbidden':'error',`<button type="button" class="btn btn-secondary" data-command="retry">${icon('refresh')} Повторить</button>`);}
export function loader(){return `<div class="card"><div class="skeleton long"></div><div class="skeleton"></div><div class="skeleton short"></div></div>`;}
export function compactDate(x){if(!x)return 'Дата не указана';const d=new Date(x);return Number.isNaN(d.getTime())?esc(x):d.toLocaleDateString('ru-RU',{day:'numeric',month:'long',year:'numeric'});}
export function compactTime(x){if(!x)return 'Не указано';const d=new Date(x);return Number.isNaN(d.getTime())?esc(x):d.toLocaleString('ru-RU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});}
export function initials(str=''){return String(str||'CC').trim().split(/\s+/).slice(0,2).map(s=>s[0]||'').join('').toUpperCase();}
export function pic(doc,large=false){let src=doc.photo_url;const map={'doc_psy':'/assets/images/doctors/doc_psy.jpg','doc_ther':'/assets/images/doctors/doc_ther.jpg','doc_other':'/assets/images/doctors/doc_other.jpg'};if(!src&&doc.verified==='synthetic_demo')src=map[doc.id];if(src&&src.startsWith('/'))return `<img class="doctor-photo ${large?'large':''}" src="${attr(src)}" alt="Фото специалиста" loading="lazy">`;return `<div class="doctor-avatar ${large?'large':''}" aria-hidden="true">${esc(initials(doc.name||doc.display_name))}</div>`;}
export function pretty(v){if(v===true)return 'Да';if(v===false)return 'Нет';if(v===null||v===undefined||v==='')return 'Не указано';if(Array.isArray(v))return v.map(pretty).join(', ');if(typeof v==='object')return Object.entries(v).filter(([k,val])=>val!==undefined && typeof val!=='object').map(([k,val])=>`${k}: ${pretty(val)}`).join(' · ');return String(v);}
export function fields(data,limit=10){return Object.entries(data||{}).filter(([k,v])=>v!==null&&v!==undefined&&!['id','user_id','patient_id','doctor_id','organization_id','photo_url','intake_json','token','email','password','csrf_token','qr_svg','qr_data_uri'].includes(k)&&typeof v!=='object').slice(0,limit).map(([k,v])=>`<div class="list-row"><span class="small muted">${esc(k.replaceAll('_',' '))}</span><strong class="small">${esc(pretty(v))}</strong></div>`).join('');}
export function tile(title,descr,path,iconName='arrow',cta='Открыть'){return `<article class="action-tile"><div class="tile-icon">${icon(iconName)}</div><div><h3>${esc(title)}</h3><p>${esc(descr)}</p></div><a class="btn btn-secondary tile-action" href="/#${attr(path)}">${esc(cta)} ${icon('arrow')}</a></article>`;}
