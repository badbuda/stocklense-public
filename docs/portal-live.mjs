/* Private staged summaries. Only materialize a displayed value if the server
   returned versioned, sha-bound evidence; never synthesize older Paper sessions.
   These summaries DO NOT establish full receipt-chain proof or broker execution. */
const VALID_DATE=/^20\d\d-\d\d-\d\d$/;
const SHA=/^[a-f0-9]{64}$/;
const STATES=new Set(['NO_STAGING_RECEIPT','SIGNAL_S3_VERSIONED',
                      'SIGNAL_PAPER_CONTINUITY_S3_SHA_BOUND','INVALID_EVIDENCE']);
const VERIFIED=new Set(['ON_TIME_QUALIFIED','LATE_WITH_CONTEMPORANEOUS_EVIDENCE']);

function dateMs(raw){
 if(typeof raw!=='string'||!VALID_DATE.test(raw))return NaN;
 const n=Date.parse(raw+'T00:00:00Z');
 return Number.isFinite(n)&&new Date(n).toISOString().slice(0,10)===raw?n:NaN;
}
function evidence(meta){
 return !!meta && SHA.test(meta.sha256||'') &&
   typeof meta.version_id==='string'&&meta.version_id.length>1 &&
   meta.version_id!=='null' &&
   typeof meta.saved_at_utc==='string' &&
   Number.isFinite(Date.parse(meta.saved_at_utc));
}
function amount(x){
 return typeof x==='number'&&Number.isFinite(x)&&x>0;
}
export function stagingSnapshot(rows,now=new Date()){
 if(!Array.isArray(rows)||rows.length>14||!Number.isFinite(now.getTime()))
   throw Error('UNTRUSTED_STAGING_TIMELINE');
 const currentDay=Date.UTC(now.getUTCFullYear(),now.getUTCMonth(),now.getUTCDate());
 const signals=[],paper=[],missing=[],invalid=[];
 let prev='';
 for(const entry of rows){
   if(!entry||!STATES.has(entry.status)||!Number.isFinite(dateMs(entry.session_date))||
      entry.session_date<=prev||dateMs(entry.session_date)>currentDay)
     throw Error('INVALID_STAGING_TIMELINE_ORDER');
   prev=entry.session_date;
   if(entry.status==='INVALID_EVIDENCE'){invalid.push(entry.session_date);continue}
   if(entry.status==='NO_STAGING_RECEIPT'){missing.push(entry.session_date);continue}
   if(!evidence(entry.signal)||![0,1,1.25,2,3].includes(entry.signal.level)||
      typeof entry.signal.target_leverage!=='number'||
      !Number.isFinite(entry.signal.target_leverage)||
      entry.signal.target_leverage<0||entry.signal.target_leverage>3)
     throw Error('UNVERIFIED_STAGING_SIGNAL');
   signals.push(entry);
   if(entry.status==='SIGNAL_PAPER_CONTINUITY_S3_SHA_BOUND'){
     if(!evidence(entry.paper)||!amount(entry.paper.equity)||
        !Number.isInteger(entry.paper.trade_count)||entry.paper.trade_count<0||
        !VERIFIED.has(entry.paper.continuity_status))
       throw Error('UNVERIFIED_STAGING_PAPER');
     paper.push(entry);
   }else if(entry.paper!=null)throw Error('PAPER_WITHOUT_SHA_BOUND_STATUS');
 }
 const newestSignal=signals.at(-1)||null;
 const lastPaper=paper.at(-1)||null;
 let gap=false;
 if(paper.length){
   const low=paper[0].session_date,high=lastPaper.session_date;
   gap=rows.some(r=>r.session_date>=low&&r.session_date<=high&&
        r.status!=='SIGNAL_PAPER_CONTINUITY_S3_SHA_BOUND');
 }
 const ageOf=(row)=>row?Math.floor((currentDay-dateMs(row.session_date))/86400000):Infinity;
 // Do not silently turn a stale or incomplete Paper series into current NAV.
 const currentPaper=!gap&&!invalid.length&&lastPaper&&ageOf(lastPaper)<=4?lastPaper:null;
 const currentSignal=!invalid.length&&newestSignal&&ageOf(newestSignal)<=4?newestSignal:null;
 return {
   signal:currentSignal,
   paper:currentPaper,
   paperSeries:currentPaper?paper.map(x=>({date:x.session_date,s:x.paper.equity})):[],
   status:invalid.length?'INVALID_EVIDENCE':
     gap?'PAPER_CHAIN_GAP':
     currentPaper?'VERIFIED_RECENT_PAPER_SUMMARIES':
     currentSignal?'SIGNAL_ONLY_NO_RECENT_PAPER':
     'NO_RECENT_VERIFIED_RECEIPTS',
   missing, invalid,
   evidenceScope:'S3_OBJECT_VERSION_SHA_BOUND_NOT_FULL_CHAIN_NOT_BROKER'
 };
}
