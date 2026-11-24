/* Optional Cognito PKCE: access token kept in memory only, never in URL/storage. */
import {stagingSnapshot} from './portal-live.mjs';
let config=null, accessToken=null, expiresAt=0, getHistory=()=>null, stagingUpdated=()=>{},taxUpdated=()=>{},epoch5Updated=()=>{};
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
/* Legacy production ledger ceased prospective writes after 2026-10-09.
   Probe ALL seven actual XNYS sessions in its sealed incident window rather
   than derive requested dates from the stale Oct-09 GitHub daily feed; that
   used to hide five missing DynamoDB sessions behind a false "0 missing". */
export const LEGACY_INCIDENT_SESSIONS=Object.freeze([
 '2026-10-08','2026-10-09','2026-10-12','2026-10-13',
 '2026-10-14','2026-10-15','2026-10-16'
]);
function datesForCurrentJournal(){
 return [...LEGACY_INCIDENT_SESSIONS];
}
export async function refreshCloudJournal(){
 if(!config){status('עדיין אין תצורת CloudFormation פרטית. הנתונים המוצגים בדשבורד מגיעים מפרסומי GitHub.');return}
 if(!accessToken||Date.now()>=expiresAt){status('יש להתחבר שוב דרך Cognito כדי לקרוא את DynamoDB.');byId('cloud-load').disabled=true;return}
 const days=datesForCurrentJournal();
 if(!days.length){status('עדיין אין ימי מסחר שהושלמו עבור יומן DynamoDB.');return}
 status('טוען רשומות DynamoDB מאומתות ל־'+days.length+' ימי מסחר...');
 const url=config.api_base_url.replace(/\/$/,'')+'/v1/sessions?dates='+encodeURIComponent(days.join(','));
 const r=await fetch(url,{headers:{'Authorization':'Bearer '+accessToken},cache:'no-store'});
 if(r.status===401||r.status===403){status('נתיב ארכיון DynamoDB אינו מורשה.');byId('cloud-load').disabled=true;return}
 if(!r.ok)throw Error('AWS_JOURNAL_HTTP_'+r.status);
 const d=await r.json();
 if(d.kind!=='STOCKLENS_AUTHENTICATED_READ_ONLY_AWS_JOURNAL'||!Array.isArray(d.sessions)||
    d.broker_orders_authorized!==false||d.broker_fills_observed!==false)throw Error('UNTRUSTED_AWS_JOURNAL_REPLY');
 const matches=d.sessions.filter(x=>x.status==='PASS').length;
 const errors=d.sessions.filter(x=>x.status==='INVALID_EVIDENCE').length;
 if(d.sessions.length!==days.length||
    d.sessions.some((x,i)=>x?.session_date!==days[i]||
    !['PASS','MISSING_SIGNAL','MISSING_PAPER','MISSING_BOTH','INVALID_EVIDENCE'].includes(x.status)))
    throw Error('INCOMPLETE_OR_MISORDERED_LEGACY_ARCHIVE_REPLY');
 status('ארכיון DynamoDB הישן עד 16.10.2026 — '+matches+' ימים תקינים, '+(d.sessions.length-matches-errors)+' ימים חסרים, '+errors+' רשומות שנפסלו ב־SHA. ימים חסרים אינם עסקאות אמיתיות ואין למלא אותם בדיעבד.');
 const root=byId('cloud-results');root.hidden=false;
 root.innerHTML='<table><thead><tr><th>יום מסחר</th><th>סטטוס אימות</th><th>רמת סיגנל</th><th>שווי Paper</th><th>עסקאות Paper</th><th>מועד ארכוב ב־AWS</th></tr></thead><tbody>'+
 d.sessions.map(row=>'<tr><td>'+html(row.session_date)+'</td><td>'+html(row.status)+'</td><td>'+html(row.signal?.level??'—')+'</td><td>'+money(row.paper?.row?.equity)+'</td><td>'+html(row.paper?.trades?.length??'—')+'</td><td>'+html(row.paper?.recorded_at_utc||row.signal?.recorded_at_utc||'—')+'</td></tr>').join('')+'</tbody></table>';
}
/* Optional private tax route reuses Cognito JWT. It never falls back to public
   account data and never turns a missing endpoint into an estimated tax. */
async function refreshPrivateTax(sessionDate){
 if(!config||!accessToken||Date.now()>=expiresAt||!/^20\d\d-\d\d-\d\d$/.test(sessionDate||'')){
  taxUpdated(null);return;
 }
 const url=config.api_base_url.replace(/\/$/,'')+'/v1/tax?date='+encodeURIComponent(sessionDate);
 const r=await fetch(url,{headers:{Authorization:'Bearer '+accessToken},cache:'no-store'});
 if(r.status===404){taxUpdated(null);return}
 if(r.status===401||r.status===403){taxUpdated(null);return}
 if(!r.ok){taxUpdated(null);throw Error('PRIVATE_TAX_HTTP_'+r.status)}
 const report=await r.json();
 if(report?.kind!=='STOCKLENS_TAX_STATUS_V1'||report.schema_version!==1||
    report.asof_date!==sessionDate||!['RESEARCH_COMPLETE','BLOCKED'].includes(report.status)){
  taxUpdated(null);throw Error('UNTRUSTED_PRIVATE_TAX_REPORT');
 }
 taxUpdated(report);
}
/* JWT-authenticated S3 Staging: distinct from the stale production DynamoDB view. */
function stagingWeekdays(){
 const result=[],d=new Date(); d.setUTCHours(0,0,0,0);
 for(let i=0;i<35&&result.length<14;i++,d.setUTCDate(d.getUTCDate()-1)){
   if(d.getUTCDay()!==0&&d.getUTCDay()!==6)result.push(d.toISOString().slice(0,10));
 }
 return result.reverse();
}
let epoch5Generation=0;
async function refreshEpoch5(){
 const gen=++epoch5Generation, notice=byId('epoch5-status'), box=byId('epoch5-results');
 if(!notice||!box)return;
 box.replaceChildren();

 epoch5Updated({status:'LOADING',rows:[]});
 notice.textContent='טוען את ספר ST החדש…';
 const token=config&&Date.now()<expiresAt?accessToken:null;
 try{
  const dates=stagingWeekdays();
  const endpoint=token?config.api_base_url.replace(/\/$/,'')+'/v1/staging-epoch5?dates='+encodeURIComponent(dates.join(',')):'https://c2r39dbwkg.execute-api.eu-central-1.amazonaws.com/v1/public-model';
  const response=await fetch(endpoint,{headers:token?{Authorization:'Bearer '+token}:{},cache:'no-store'});
  if(gen!==epoch5Generation||(token&&(token!==accessToken||Date.now()>=expiresAt)))return;
  if(!response.ok){epoch5Updated({status:'ERROR',rows:[]});notice.textContent='נתיב Epoch 5 אינו זמין ('+response.status+'). אין הצגת יתרות ישנות במקומו.';return}
  const d=await response.json();
  if(gen!==epoch5Generation||(token&&(token!==accessToken||Date.now()>=expiresAt)))return;
  if(d.kind!==(token?'STOCKLENS_EPOCH5_READ_ONLY_V1':'STOCKLENS_PUBLIC_MODELED_EPOCH5_V1')||d.book!=='NEW_AWS_INDEPENDENT_STAGING_BOOK_EPOCH5_20261124'||d.broker_orders_authorized!==false||d.broker_fills_observed!==false||d.independent_second_vendor_verified!==false||d.full_chain_verified!==false||!Array.isArray(d.sessions)||d.sessions.length>14)throw Error('UNTRUSTED_EPOCH5');
  const rows=d.sessions;
  if(!token&&(d.starting_demo_usd!==100000||!Number.isFinite(Date.parse(d.generated_at_utc))||Math.abs(Date.now()-Date.parse(d.generated_at_utc))>300000))throw Error('PUBLIC_MODEL_NOT_FRESH');
  const validMeta=m=>m&&(!token||(/^[a-f0-9]{64}$/.test(m.sha256)&&typeof m.version_id==='string'&&m.version_id!==''&&m.version_id!=='null'));
  const validNum=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0;
  if(rows.length!==dates.length||rows.some((x,i)=>!x||x.session_date!==dates[i]||
   !['NOT_STARTED','NO_RECEIPT','INVALID_OR_PARTIAL_EVIDENCE','SHA_BOUND_SINGLE_VENDOR_MODELED'].includes(x.paper_status)||
   (x.signal&&(!validMeta(x.signal)||x.signal.session_date!==x.session_date||![0,1,1.25,2,3].includes(x.signal.level)||!validNum(x.signal.target_leverage)||x.signal.target_leverage>3))||
   (x.paper_status==='SHA_BOUND_SINGLE_VENDOR_MODELED'?(!validMeta(x.paper)||x.paper.continuity_status!=='MODELLED_RECEIPT_NOT_INDEPENDENTLY_QUALIFIED'||!validMeta(x.paper.execution_signal)||!['equity','cash','qqq_shares','tqqq_shares','cumulative_fees','cumulative_slippage_cost','trade_count'].every(k=>validNum(x.paper[k]))||x.paper.equity<=0):x.paper!=null)))throw Error('INVALID_EPOCH5_ROWS');
  epoch5Updated({status:'READY',rows,source:token?'PRIVATE':'PUBLIC_DEMO'});
  const latest=rows.filter(x=>x.paper_status==='SHA_BOUND_SINGLE_VENDOR_MODELED'&&x.paper).at(-1);
  notice.textContent=latest?'שווי מדומה אחרון מתועד: '+money(latest.paper.equity)+' · '+latest.session_date+' · לא אימות שרשרת מלאה.':'אין עדיין זוג רשומות Paper ו־Continuity תקין בספר החדש.';
  box.innerHTML='<table><thead><tr><th>יום</th><th>סיגנל של היום</th><th>מצב Paper</th><th>סיגנל ששימש לביצוע</th><th>פעולה</th><th>שווי מדומה</th><th>מזומן</th><th>QQQ</th><th>TQQQ</th><th>עסקאות</th></tr></thead><tbody>'+rows.slice().reverse().map(x=>{const p=x.paper_status==='SHA_BOUND_SINGLE_VENDOR_MODELED'?x.paper:null;return '<tr><td>'+html(x.session_date)+'</td><td>'+html(x.signal_error?'שגיאת אימות':x.signal?.target_leverage??'—')+'</td><td>'+html(x.paper_status)+'</td><td>'+html(p?.execution_signal?.session_date??'—')+'</td><td>'+html(p?.paper_action??'—')+'</td><td>'+money(p?.equity)+'</td><td>'+money(p?.cash)+'</td><td>'+html(p?.qqq_shares??'—')+'</td><td>'+html(p?.tqqq_shares??'—')+'</td><td>'+html(p?.trade_count??'—')+'</td></tr>'}).join('')+'</tbody></table>';
  const trades=rows.flatMap(x=>(x.paper?.trades||[]).map(t=>({day:x.session_date,...t})));
  if(!token&&trades.length)box.innerHTML+='<h3>עסקאות מדומות — Epoch 5</h3><table><thead><tr><th>יום</th><th>פעולה</th><th>נייר</th><th>כמות</th><th>מחיר מדומה</th><th>שעת ניו יורק</th></tr></thead><tbody>'+trades.slice().reverse().map(t=>'<tr><td>'+html(t.day)+'</td><td>'+html(t.side)+'</td><td>'+html(t.symbol)+'</td><td>'+html(t.qty)+'</td><td>'+money(t.modeled_fill_price)+'</td><td>'+html(t.time_et)+'</td></tr>').join('')+'</tbody></table>';
 }catch{if(gen===epoch5Generation){epoch5Updated({status:'ERROR',rows:[]});notice.textContent='לא ניתן לאמת נתוני Epoch 5';box.replaceChildren()}}
}
async function refreshStagingJournal(){
 void refreshEpoch5();
 const notice=byId('cloud-staging-status'),container=byId('cloud-staging-results');
 if(!config||!accessToken||Date.now()>=expiresAt){taxUpdated(null);notice.textContent='נדרשת התחברות Cognito לקריאת נתוני Staging';return}
 notice.textContent='טוען ראיות S3 פרטיות…';taxUpdated(null);
 const url=config.api_base_url.replace(/\/$/,'')+'/v1/staging?dates='+encodeURIComponent(stagingWeekdays().join(','));
 const r=await fetch(url,{headers:{Authorization:'Bearer '+accessToken},cache:'no-store'});
 if(r.status===404){stagingUpdated([]);taxUpdated(null);notice.textContent='נתיב Staging המאובטח טרם הותקן';return}
 if(r.status===401||r.status===403){stagingUpdated([]);taxUpdated(null);notice.textContent='נתיב ארכיון Staging אינו מורשה';return}
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
 stagingUpdated(response.sessions);
 // Only an aligned, SHA-bound current Paper session can authorize a tax read.
 let aligned=null;
 try{aligned=stagingSnapshot(response.sessions).paper?.session_date||null}catch(_){aligned=null}
 // Optional tax API failures MUST NOT conceal a valid SHA-bound Paper session.
 // Authenticated S3 Paper remains readable even before the tax route exists.
 await refreshPrivateTax(aligned).catch(()=>taxUpdated(null));
 container.hidden=false;
 container.innerHTML='<table><thead><tr><th>יום</th><th>מצב</th><th>רמת חשיפה</th><th>מינוף</th><th>שווי Paper מדומה</th><th>שמירת סיגנל ב־AWS</th></tr></thead><tbody>'+
 response.sessions.slice().reverse().map(x=>'<tr><td>'+html(x.session_date)+'</td><td>'+html(x.status)+'</td><td>'+
 html(x.signal?.level??'—')+'</td><td>'+html(x.signal?.target_leverage??'—')+'</td><td>'+
 money(x.paper?.equity)+'</td><td>'+html(x.signal?.saved_at_utc||'—')+'</td></tr>').join('')+'</tbody></table>';
}
export function initCloudJournal({getHistory:historyProvider,onStagingChange,onTaxChange,onEpoch5Change}){
 if(typeof onEpoch5Change==='function')epoch5Updated=onEpoch5Change;
 getHistory=historyProvider;
 if(typeof onStagingChange==='function')stagingUpdated=onStagingChange;
 if(typeof onTaxChange==='function')taxUpdated=onTaxChange;
 const loginBtn=byId('cloud-login'),loadBtn=byId('cloud-load');
 loginBtn?.addEventListener('click',()=>login().catch(err=>status('שגיאה בהתחברות: '+err.message)));
 byId('epoch5-login')?.addEventListener('click',()=>login().catch(err=>status('שגיאה בהתחברות: '+err.message)));
 byId('epoch5-refresh')?.addEventListener('click',()=>refreshEpoch5());
 byId('refresh')?.addEventListener('click',()=>refreshEpoch5());
 void refreshEpoch5();
 loadBtn?.addEventListener('click',()=>refreshCloudJournal().catch(err=>status('שגיאת קריאה מ־AWS: '+err.message)));
 byId('cloud-staging-load')?.addEventListener('click',()=>refreshStagingJournal().catch(err=>{byId('cloud-staging-status').textContent='שגיאת S3: '+err.message}));
 // Authenticated, read-only refresh while the tab is open. Never retain JWT in storage.
 setInterval(()=>{
   if(!config||!accessToken){void refreshEpoch5();return}
   if(Date.now()>=expiresAt){accessToken=null;void refreshEpoch5();stagingUpdated([]);taxUpdated(null);status('פג תוקף ההתחברות ל־AWS; התחברי שוב.');return}
   refreshStagingJournal().catch(err=>{byId('cloud-staging-status').textContent='שגיאת רענון S3: '+err.message});
 },300000);
 fetch('./cloud-config.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(async cfg=>{
   if(!validateConfig(cfg)){status('חיבור DynamoDB אישי טרם הופעל. כדי להפעיל דרוש API מאובטח ותצורת Cognito, לא הרשאות AWS בדפדפן.');return}
   config=cfg;loginBtn.disabled=false;if(byId('epoch5-login'))byId('epoch5-login').disabled=false;
   status('אפשר להתחבר לחשבון Cognito פרטי כדי לקרוא רשומות DynamoDB בזמן אמת.');
   const authenticated=await completeLogin();
   if(authenticated&&accessToken){void refreshStagingJournal().catch(err=>{byId('cloud-staging-status').textContent='שגיאת S3: '+err.message});await refreshCloudJournal()}
 }).catch(err=>status('חיבור AWS פרטי אינו זמין: '+err.message));
}
