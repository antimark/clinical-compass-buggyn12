/* Real same-origin session/CSRF adapter. No mock medical data and no credential storage. */
let csrf='';
export class ApiError extends Error {
  constructor(status, code, message){ super(message || 'Ошибка сервера');this.name='ApiError';this.status=status;this.code=code||'UNKNOWN'; }
}
export function getCsrf(){return csrf;}
export function setCsrf(token){if(typeof token==='string'&&token)csrf=token;}
export async function request(method,path,data,options={}){
  if(!path.startsWith('/api/v1/'))throw new Error('Недопустимый API путь');
  const headers={Accept:'application/json'};
  if(data!==undefined){headers['Content-Type']='application/json';}
  if(csrf)headers['X-CSRF-Token']=csrf;
  let response;
  try {response=await fetch(path,{method,credentials:'same-origin',headers,body:data===undefined?undefined:JSON.stringify(data),signal:options.signal});}
  catch(e){if(e.name==='AbortError')throw e;throw new ApiError(0,'NETWORK','Не удалось связаться с сервером. Проверьте соединение.');}
  const type=response.headers.get('content-type')||'';
  const body=type.includes('application/json')?await response.json().catch(()=>null):null;
  if(body&&typeof body.csrf_token==='string')setCsrf(body.csrf_token);
  if(!response.ok){throw new ApiError(response.status,body?.error?.code||'HTTP_'+response.status,body?.error?.message||{
    401:'Войдите в аккаунт, чтобы продолжить.',403:'У вас нет прав для этого действия.',404:'Запрошенные данные не найдены.',409:'Данные изменились. Обновите страницу.',422:'Проверьте введённые данные.',429:'Слишком много запросов. Попробуйте позже.'
  }[response.status]||'Сервер временно недоступен.');}
  if(body===null)throw new ApiError(response.status,'INVALID_RESPONSE','Сервер вернул неожиданный ответ вместо JSON.');
  return body;
}
export const api={get:(p)=>request('GET',p),post:(p,d={})=>request('POST',p,d),put:(p,d)=>request('PUT',p,d),patch:(p,d)=>request('PATCH',p,d),delete:(p,d)=>request('DELETE',p,d)};
export const segment=(v)=>encodeURIComponent(String(v));
export async function bootstrap(){const [boot,oidc,cap,session]=await Promise.allSettled([
  api.get('/api/v1/onboarding/bootstrap'),api.get('/api/v1/auth/oidc/capabilities'),api.get('/api/v1/p0/auth/capabilities'),api.get('/api/v1/auth/me')
]);return {boot:boot.status==='fulfilled'?boot.value:{enabled:false,environment:'unknown'},oidc:oidc.status==='fulfilled'?oidc.value:{enabled:false},cap:cap.status==='fulfilled'?cap.value:{},session:session.status==='fulfilled'?session.value:null};}
