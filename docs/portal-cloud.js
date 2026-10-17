/* Optional Cognito PKCE: access token kept in memory only, never in URL/storage. */
let config=null, accessToken=null, expiresAt=0, getHistory=()=>null;
const byId=id=>document.getElementById(id);
const status=s=>{const n=byId('cloud-status');if(n)n.textContent=s};
const html=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
const money=x=>x!=null&&x!==''&&Number.isFinite(Number(x))?String.fromCharCode(36)+new Intl.NumberFormat('en-US',{maximumFractionDigits:2}).format(Number(x)):'—';
const b64=bytes=>btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');
const random=()=>b64(crypto.getRandomValues(new Uint8Array(32)));
async function challenge(verifier){return b64(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier))))}
function validateConfig(c){
 if(!c||c.enabled!==true)return false;
 const api=new URL(c.api_base_url),domain=new URL(c.cognito_domain);
 if(api.protocol!=='https:'||domain.protocol!=='https:'||!domain.hostname.endsWith('.amazoncognito.com'))throw Error('INVALID_CLOUD_ORIGIN');
 if(!/^[a-z0-9]+$/i.test(c.client_id||''))throw Error('INVALID_COGNITO_CLIENT');
 if(c.redirect_uri!==location.origin+'/portal.html')throw Error('INVALID_COGNITO_REDIRECT');
 return true;
}
async function login(){
 if(!config)return;
 const verifier=random(),nonce=random();
 sessionStorage.setItem('stocklens-pkce',JSON.stringify({verifier,nonce,at:Date.now()}));
 const params=new URLSearchParams({
   response_type:'code',client_id:config.client_id,redirect_uri:config.redirect_uri,
   scope:'openid email',state:nonce,code_challenge_method:'S256',
   code_challenge:await challenge(verifier)
 });
 location.assign(config.cognito_domain+'/oauth2/authorize?'+params);
}
async function completeLogin(){
 const query=new URLSearchParams(location.search);
 const code=query.get('code'),state=query.get('state'),error=query.get('error');
 if(!code&&!error)return false;
 history.replaceState(null,'',location.pathname+location.hash);
 if(error){status('הכניסה נכשלה: '+error);return true}
 let pending;try{pending=JSON.parse(sessionStorage.getItem('stocklens-pkce')||'null')}catch{}
 sessionStorage.removeItem('stocklens-pkce');
 if(!pending||pending.nonce!==state||Date.now()-pending.at>600000){status('תוקף בקשת ההתחברות פג או שמזהה האבטחה שגוי.');return true}
 const form=new URLSearchParams({
   grant_type:'authorization_code',client_id:config.client_id,
   redirect_uri:config.redirect_uri,code,code_verifier:pending.verifier
 });
 const response=await fetch(config.cognito_domain+'/oauth2/token',{
   method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},
   body:form.toString(),cache:'no-store'
 });
 if(!response.ok)throw Error('COGNITO_TOKEN_EXCHANGE_FAILED_'+response.status);
 const o=await response.json();
 if(typeof o.access_token!=='string'||o.token_type!=='Bearer')throw Error('INVALID_TOKEN_RESPONSE');
 accessToken=o.access_token;expiresAt=Date.now()+(Number(o.expires_in||3600)-60)*1000;
 status('מחובר ל־AWS באופן אישי. הטוקן נשמר בזיכרון הלשונית בלבד.');
 byId('cloud-load').disabled=false;
 if(byId('cloud-staging-load'))byId('cloud-staging-load').disabled=false;
 return true;
}
function datesForCurrentJournal(){
 const h=getHistory(),days=h?.daily?.map(r=>r.date).filter(x=>x>='2026-10-08')||[];
 return [...new Set(days)].slice(-20);
}
export async function refreshCloudJournal(){
 if(!config){status('עדיין אין תצורת CloudFormation פרטית. הנתונים המוצגים בדשבורד מגיעים מפרסומי GitHub.');return}
 if(!accessToken||Date.now()>=expiresAt){status('יש להתחבר שוב דרך Cognito כדי לקרוא את DynamoDB.');byId('cloud-load').disabled=true;return}
 const days=datesForCurrentJournal();
 if(!days.length){status('עדיין אין ימי מסחר שהושלמו עבור יומן DynamoDB.');return}
 status('טוען רשומות DynamoDB מאומתות ל־'+days.length+' ימי מסחר...');
 const url=config.api_base_url.replace(/\/$/,'')+'/v1/sessions?dates='+encodeURIComponent(days.join(','));
 const r=await fetch(url,{headers:{'Authorization':'Bearer '+accessToken},cache:'no-store'});
 if(r.status===401||r.status===403){accessToken=null;status('פג תוקף האימות או שאין הרשאות לחשבון הזה.');byId('cloud-load').disabled=true;return}
 if(!r.ok)throw Error('AWS_JOURNAL_HTTP_'+r.status);
 const d=await r.json();
 if(d.kind!=='STOCKLENS_AUTHENTICATED_READ_ONLY_AWS_JOURNAL'||!Array.isArray(d.sessions)||
    d.broker_orders_authorized!==false||d.broker_fills_observed!==false)throw Error('UNTRUSTED_AWS_JOURNAL_REPLY');
 const matches=d.sessions.filter(x=>x.status==='PASS').length;
 const errors=d.sessions.filter(x=>x.status==='INVALID_EVIDENCE').length;
 status('DynamoDB — '+matches+' ימים תקינים, '+(d.sessions.length-matches-errors)+' טרם נשמרו, '+errors+' רשומות שנפסלו בבדיקת SHA. קריאה אישית בלבד.');
 const root=byId('cloud-results');root.hidden=false;
 root.innerHTML='<table><thead><tr><th>יום מסחר</th><th>סטטוס אימות</th><th>רמת סיגנל</th><th>שווי Paper</th><th>עסקאות Paper</th><th>מועד ארכוב ב־AWS</th></tr></thead><tbody>'+
 d.sessions.map(row=>'<tr><td>'+html(row.session_date)+'</td><td>'+html(row.status)+'</td><td>'+html(row.signal?.level??'—')+'</td><td>'+money(row.paper?.row?.equity)+'</td><td>'+html(row.paper?.trades?.length??'—')+'</td><td>'+html(row.paper?.recorded_at_utc||row.signal?.recorded_at_utc||'—')+'</td></tr>').join('')+'</tbody></table>';
}
/* JWT-authenticated S3 Staging: distinct from the stale production DynamoDB view. */
function stagingWeekdays(){
 const result=[],d=new Date(); d.setUTCHours(0,0,0,0);
 for(let i=0;i<35&&result.length<14;i++,d.setUTCDate(d.getUTCDate()-1)){
   if(d.getUTCDay()!==0&&d.getUTCDay()!==6)result.push(d.toISOString().slice(0,10));
 }
 return result.reverse();
}
async function refreshStagingJournal(){
 const notice=byId('cloud-staging-status'),container=byId('cloud-staging-results');
 if(!config||!accessToken||Date.now()>=expiresAt){notice.textContent='נדרשת התחברות Cognito לקריאת נתוני Staging';return}
 notice.textContent='טוען ראיות S3 פרטיות…';
 const url=config.api_base_url.replace(/\/$/,'')+'/v1/staging?dates='+encodeURIComponent(stagingWeekdays().join(','));
 const r=await fetch(url,{headers:{Authorization:'Bearer '+accessToken},cache:'no-store'});
 if(r.status===404){notice.textContent='נתיב Staging המאובטח טרם הותקן';return}
 if(r.status===401||r.status===403){accessToken=null;byId('cloud-staging-load').disabled=true;notice.textContent='תוקף ההתחברות פג';return}
 if(!r.ok)throw Error('STAGING_READ_HTTP_'+r.status);
 const response=await r.json();
 if(response.kind!=='STOCKLENS_AUTHENTICATED_STAGING_S3_READ_ONLY'||
    response.source!=='PRIVATE_VERSIONED_STAGING_S3'||
    !Array.isArray(response.sessions)||response.sessions.length>14||
    response.broker_orders_authorized!==false||response.broker_fills_observed!==false||
    response.full_chain_verified_by_portal!==false||response.production_cutover_authorized!==false)
   throw Error('UNTRUSTED_STAGING_EVIDENCE');
 const allowed=new Set(['NO_STAGING_RECEIPT','SIGNAL_S3_VERSIONED','SIGNAL_PAPER_CONTINUITY_S3_SHA_BOUND','INVALID_EVIDENCE']);
 if(response.sessions.some(x=>!x||!/^20\d\d-\d\d-\d\d$/.test(x.session_date)||!allowed.has(x.status)))
   throw Error('INVALID_STAGING_SESSIONS');
 const signals=response.sessions.filter(x=>x.status==='SIGNAL_S3_VERSIONED'||x.status==='SIGNAL_PAPER_CONTINUITY_S3_SHA_BOUND');
 const paper=response.sessions.filter(x=>x.status==='SIGNAL_PAPER_CONTINUITY_S3_SHA_BOUND');
 const invalid=response.sessions.filter(x=>x.status==='INVALID_EVIDENCE');
 notice.textContent='S3 Staging: '+signals.length+' סיגנלים, '+paper.length+' ימי Paper, '+invalid.length+' ראיות פסולות. אחרון: '+(signals.at(-1)?.session_date||'אין')+'. תצוגת SHA/גרסה, לא אימות מלא של שרשרת Paper או מסחר אמיתי.';
 container.hidden=false;
 container.innerHTML='<table><thead><tr><th>יום</th><th>מצב</th><th>רמת חשיפה</th><th>מינוף</th><th>שווי Paper מדומה</th><th>שמירת סיגנל ב־AWS</th></tr></thead><tbody>'+
 response.sessions.slice().reverse().map(x=>'<tr><td>'+html(x.session_date)+'</td><td>'+html(x.status)+'</td><td>'+
 html(x.signal?.level??'—')+'</td><td>'+html(x.signal?.target_leverage??'—')+'</td><td>'+
 money(x.paper?.equity)+'</td><td>'+html(x.signal?.saved_at_utc||'—')+'</td></tr>').join('')+'</tbody></table>';
}
export function initCloudJournal({getHistory:historyProvider}){
 getHistory=historyProvider;
 const loginBtn=byId('cloud-login'),loadBtn=byId('cloud-load');
 loginBtn?.addEventListener('click',()=>login().catch(err=>status('שגיאה בהתחברות: '+err.message)));
 loadBtn?.addEventListener('click',()=>refreshCloudJournal().catch(err=>status('שגיאת קריאה מ־AWS: '+err.message)));
 byId('cloud-staging-load')?.addEventListener('click',()=>refreshStagingJournal().catch(err=>{byId('cloud-staging-status').textContent='שגיאת S3: '+err.message}));
 fetch('./cloud-config.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(async cfg=>{
   if(!validateConfig(cfg)){status('חיבור DynamoDB אישי טרם הופעל. כדי להפעיל דרוש API מאובטח ותצורת Cognito, לא הרשאות AWS בדפדפן.');return}
   config=cfg;loginBtn.disabled=false;
   status('אפשר להתחבר לחשבון Cognito פרטי כדי לקרוא רשומות DynamoDB בזמן אמת.');
   const authenticated=await completeLogin();
   if(authenticated&&accessToken){await refreshCloudJournal();await refreshStagingJournal().catch(err=>{byId('cloud-staging-status').textContent='שגיאת S3: '+err.message})}
 }).catch(err=>status('חיבור AWS פרטי אינו זמין: '+err.message));
}
