/* Real Chromium smoke test of the published static portal and Yahoo ETF simulator. */
const assert=require('node:assert/strict');
const { chromium }=require('playwright');
const fs=require('node:fs');
const base=(process.env.PORTAL_BASE_URL || 'http://127.0.0.1:8765').replace(/\/$/,'');
const failures=[];
const screenshotSuffix=(process.env.PORTAL_SCREENSHOT_SUFFIX || 'local').replace(/[^a-z0-9-]/gi,'');
(async()=>{
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
try{
 const page=await browser.newPage({viewport:{width:1440,height:900},deviceScaleFactor:1});
 page.on('pageerror',e=>{failures.push(e.message);console.error('PORTAL_RUNTIME_STACK:',e.stack||e.message)});
 page.on('console',m=>{if(m.type()==='error')console.error('BROWSER_CONSOLE_ERROR:',m.text())});
 page.on('requestfailed',q=>console.error('BROWSER_REQUEST_FAILED:',q.url(),q.failure()?.errorText));
 page.on('response',r=>{if(r.status()>=400)console.error('BROWSER_HTTP_ERROR:',r.status(),r.url())});
 await page.goto(base+'/',{waitUntil:'networkidle',timeout:60000});
 await page.waitForURL(/portal\.html/,{timeout:12000});
 assert.match(await page.title(),/StockLens/);
 try {await page.waitForFunction(()=>document.querySelector('#kpi-days')?.textContent!=='—',{timeout:25000});} catch(error) {
   console.error('PAGE_RUNTIME_ERRORS:',JSON.stringify(failures));
   console.error('PAGE_LOCATION:',page.url());
   console.error('PAGE_LOAD_ERROR:',await page.locator('#load-error').textContent());
   console.error('PAGE_MODULES:',await page.locator('script[type=module]').count());
   throw error;
 }
 const currentSignal=await page.locator('#asof-badge').textContent();
 assert.match(currentSignal,/20\d\d-\d\d-\d\d/);
 assert.equal((await page.locator('.page.visible').getAttribute('data-view')),'overview');
 assert.match(await page.locator('#kpi-nav').textContent(),/^\$/);
 assert.match(await page.locator('#readiness-clarity').textContent(),/אין אישור למסחר אמיתי/);
 const governance=await page.evaluate(async()=>{
   const [d,h,r]=await Promise.all([
     fetch('data.json',{cache:'no-store'}).then(x=>x.json()),
     fetch('portal-history.json',{cache:'no-store'}).then(x=>x.json()),
     fetch('observed_tqqq_risk_audit.json',{cache:'no-store'}).then(x=>x.json())
   ]);
   return {paper:d.paper.sessions,research:d.capital_readiness.prospective_completed_sessions,
     cum:d.paper.latest.cumulative_return,technical:d.capital_readiness.technical_checks_pass,
     signalSession:d.signal.asof_date,paperSession:d.paper.latest.session_date,
     historySession:h.updated_session,riskSession:r.period.end};
 });
 assert.ok(governance.signalSession,'No published signal session');
 const paperArchiveStale=governance.paperSession!==governance.signalSession;
 // A stale *archival* Paper is an expected, explicitly degraded data state.
 // E2E must prove the UI displays its ERROR banner instead of failing the
 // browser itself. Operational readiness stays fail-closed in the separate
 // publication-health workflow; never reclassify the Paper as current.
 if(paperArchiveStale){
   const reason=`Paper is stale versus published signal: PUBLISHED_PAPER_ARCHIVE_STALE:paper=${governance.paperSession}:signal=${governance.signalSession}`;
   console.warn('PORTAL_ARCHIVAL_PAPER_DEGRADED_EXPECTED:',reason);
 }
 assert.equal(governance.historySession,governance.signalSession,'Historical ETF feed is stale');
 assert.equal(governance.riskSession,governance.signalSession,'Risk cohort is stale');
 assert.match(await page.locator('#health-list').textContent(),/תאריך נתוני האתר/);
 assert.equal(await page.locator('#feed-status').isVisible(),true,'Static publication must disclose source freshness');
 assert.match(await page.locator('#kpi-nav-source').textContent(),/ארכיון GitHub/);
 assert.match(await page.locator('#staging-overview-status').textContent(),/Staging/);
 const feedBanner=await page.locator('#feed-status').textContent();
 assert.match(feedBanner,/GitHub|מיושנים|פער תאריכים|חסרים/);
 if(paperArchiveStale){
   assert.match(feedBanner,/פער תאריכים|מיושנים|חסרים/,'Stale Paper must be explicitly disclosed');
   assert.equal(await page.locator('#feed-status').evaluate(e=>e.classList.contains('error')),true,
     'Stale Paper archive must render a visible error state');
 }
 const oldestPublished=[governance.signalSession,governance.paperSession,governance.historySession,governance.riskSession].sort()[0];
 const snapshotAge=Math.floor((Date.now()-Date.parse(oldestPublished+'T00:00:00Z'))/86400000);
 if(snapshotAge>4)assert.match(feedBanner,/מיושנים|פער תאריכים|חסרים/,'Stale dates must never appear as live');

 const healthText=await page.locator('#health-list').textContent();
 if(paperArchiveStale){
   assert.match(healthText,/פער תאריכים · Signal/,'Health dashboard must explain stale Paper mismatch');
   assert.match(healthText,new RegExp('Paper '+governance.paperSession),
     'Health dashboard must show the actual archived Paper session');
 }else{
   assert.match(healthText,/מאומת · /,'Healthy matching sources must be labeled verified');
 }
 assert.equal((await page.locator('#real-paper-sessions').textContent()).trim(),
   new Intl.NumberFormat('en-US').format(governance.paper));
 assert.equal((await page.locator('#research-session-count').textContent()).trim(),
   new Intl.NumberFormat('en-US').format(governance.research));
 assert.equal((await page.locator('#real-paper-return').textContent()).trim(),
   (100*governance.cum).toFixed(2)+'%');
 assert.equal(governance.technical,false,'Technical capital gate remains blocked');
 assert.match(await page.locator('#model-parity-state').textContent(),/טרם הוכח/);
 if(await page.locator('#paper-chart-empty').isVisible()) assert.match(await page.locator('#paper-chart-empty').textContent(),/יום מדומה אחד|אין ימי Paper/);
 await page.locator('button[data-page=paper]').click();
 assert.match(await page.locator('#trades-body').textContent(),/TQQQ/);
 assert.match(await page.locator('#trades-body').textContent(),/BUY|קנייה/);
 await page.locator('#trades-body tr[data-trade-index]').first().click();
 assert.match(await page.locator('#paper-trade-detail').textContent(),/מחיר מקור|מחיר מדומה/);
 assert.match(await page.locator('#paper-trade-detail').textContent(),/עלות החלקה/);
 assert.match(await page.locator('#journal-status').textContent(),/יומן Paper|אין חורים|פרסום|רצף/);
 const cloudConfig=await page.evaluate(()=>fetch('cloud-config.json',{cache:'no-store'}).then(r=>r.json()));
 const approvedOrigin=new URL(cloudConfig.redirect_uri).origin;
 const onApprovedOrigin=new URL(page.url()).origin===approvedOrigin;
 if(cloudConfig.enabled===true&&onApprovedOrigin){
   await page.waitForFunction(()=>!document.querySelector('#cloud-login')?.disabled,{timeout:10000});
   assert.equal(await page.locator('#cloud-login').isEnabled(),true,'Private Cognito login should be offered');
   assert.equal(await page.locator('#cloud-load').isDisabled(),true,'No journal read before Cognito authentication');
   assert.equal(await page.locator('#cloud-staging-load').isDisabled(),true,'No Staging S3 read before authentication');
 }else{
   assert.equal(await page.locator('#cloud-login').isDisabled(),true,'Cognito login must be disabled on nonapproved origins or when unconfigured');
 }
 await page.locator('button[data-page=performance]').click();
 assert.ok(await page.locator('#performance-chart polyline').count()===2,'Both observed ETF curves drawn');
 assert.match(await page.locator('#perf-period').textContent(),/2010/);
 await page.locator('button[data-page=research]').click();
 assert.ok(await page.locator('#experiments .experiment').count()>=1,'Research experiments populated');
 await page.locator('button[data-page=simulator]').click();
 await page.waitForFunction(()=>{const text=document.querySelector('#sim-strategy')?.textContent;return text && text.charAt(0)===String.fromCharCode(36)},{timeout:15000});
 await page.locator('#sim-form button[type=submit]').click();
 const first=await page.locator('#sim-strategy').textContent();
 assert.match(first,/\$/);
 assert.ok(await page.locator('#sim-chart polyline').count()===2,'Scenario compares real modeled StockLens and QQQ');
 assert.ok(await page.locator('#sim-events tr').count()>1,'Scenario produces simulated trade receipts');
 assert.ok(await page.locator('#scenario-compare-body tr').count()>=6,'Scenario B comparison populated');
 assert.ok(await page.locator('#scenario-compare-chart polyline').count()===2,'Scenario A and B are plotted independently');
 const priorComparison=await page.locator('#scenario-compare-body').textContent();
 await page.locator('#scenario-b-monthly').fill('9000');
 await page.locator('#scenario-b-form button[type=submit]').click();
 assert.notEqual(priorComparison,await page.locator('#scenario-compare-body').textContent(),'B contribution change must recompute comparison');
 await page.locator('#sim-initial').fill('150000');
 await page.locator('#sim-form button[type=submit]').click();
 const second=await page.locator('#sim-strategy').textContent();
 assert.notEqual(first,second,'Changing capital must change output');
 await page.screenshot({path:'/tmp/stocklens-desktop-'+screenshotSuffix+'.png',fullPage:true});
 const mobile=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:1});
 mobile.on('pageerror',e=>failures.push(e.message));
 await mobile.goto(base+'/portal.html',{waitUntil:'networkidle',timeout:60000});
 await mobile.waitForFunction(()=>document.querySelector('#kpi-days')?.textContent!=='—',{timeout:25000});
 await mobile.locator('#menu-toggle').click();
 assert.equal(await mobile.locator('#menu-toggle').getAttribute('aria-expanded'),'true');
 await mobile.locator('button[data-page=paper]').click();
 assert.equal((await mobile.locator('.page.visible').getAttribute('data-view')),'paper');
 await mobile.screenshot({path:'/tmp/stocklens-mobile-'+screenshotSuffix+'.png',fullPage:true});
 // Authenticated S3 staging path is exercised using only synthetic, local
 // browser-intercepted OAuth/API fixtures. No AWS credentials or API calls.
 // This guards against UI exceptions hidden from the public unauthenticated E2E.
 const authed=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:1});
 authed.on('pageerror',e=>failures.push('AUTHED_STAGING_RUNTIME:'+e.message));
 await authed.addInitScript(()=>{
   sessionStorage.setItem('stocklens-pkce',JSON.stringify({
     verifier:'mock-ci-pkce-verifier',nonce:'ci-nonce',at:Date.now()
   }));
 });
 const fixtureOrigin=new URL(base).origin;
 const mockCors={
   'access-control-allow-origin':fixtureOrigin,
   'access-control-allow-headers':'authorization,content-type',
   'access-control-allow-methods':'GET,POST,OPTIONS'
 };
 const apiOrigin='https://c2r39dbwkg.execute-api.eu-central-1.amazonaws.com';
 const cognitoOrigin='https://stocklens-portal-634740393398.auth.eu-central-1.amazoncognito.com';
 await authed.route('**/cloud-config.json',route=>route.fulfill({
   status:200,contentType:'application/json',
   body:JSON.stringify({enabled:true,api_base_url:apiOrigin,cognito_domain:cognitoOrigin,
     client_id:'mock-ci-client',redirect_uri:fixtureOrigin+'/portal.html'})
 }));
 await authed.route(cognitoOrigin+'/oauth2/token',route=>route.fulfill({
   status:200,contentType:'application/json',headers:mockCors,
   body:JSON.stringify({access_token:'mock-ci-token-only',token_type:'Bearer',expires_in:3600})
 }));
 const archivedDays=['2026-10-08','2026-10-09','2026-10-12','2026-10-13',
   '2026-10-14','2026-10-15','2026-10-16'];
 await authed.route('**/v1/sessions?*',route=>route.fulfill({
   status:200,contentType:'application/json',headers:mockCors,
   body:JSON.stringify({kind:'STOCKLENS_AUTHENTICATED_READ_ONLY_AWS_JOURNAL',
     broker_orders_authorized:false,broker_fills_observed:false,
     sessions:archivedDays.map(d=>({session_date:d,status:'MISSING_BOTH'}))})
 }));
 const isoDay=(offset)=>{
   const d=new Date();d.setUTCHours(0,0,0,0);d.setUTCDate(d.getUTCDate()-offset);
   return d.toISOString().slice(0,10);
 };
 const meta={sha256:'a'.repeat(64),version_id:'fixture-version',saved_at_utc:new Date().toISOString()};
 const fakePaper=(day,equity,tradeCount)=>({
   session_date:day,status:'SIGNAL_PAPER_CONTINUITY_S3_SHA_BOUND',
   signal:{...meta,level:3,target_leverage:3},
   paper:{...meta,sha256:'b'.repeat(64),equity,trade_count:tradeCount,
     continuity_status:'ON_TIME_QUALIFIED'}
 });
 await authed.route('**/v1/staging?*',route=>route.fulfill({
   status:200,contentType:'application/json',headers:mockCors,
   body:JSON.stringify({kind:'STOCKLENS_AUTHENTICATED_STAGING_S3_READ_ONLY',
     source:'PRIVATE_VERSIONED_STAGING_S3',broker_orders_authorized:false,
     broker_fills_observed:false,full_chain_verified_by_portal:false,
     production_cutover_authorized:false,
     sessions:[fakePaper(isoDay(1),100050,1),fakePaper(isoDay(0),100100,2)]})
 }));
 await authed.goto(base+'/portal.html?code=ci-only&state=ci-nonce',
   {waitUntil:'networkidle',timeout:60000});
 await authed.waitForFunction(()=>
   document.querySelector('#staging-overview-status')?.textContent.includes('Paper Staging S3'),
   null,{timeout:15000});
 assert.match(await authed.locator('#cloud-staging-status').textContent(),/2 ימי Paper/);
 assert.match(await authed.locator('#kpi-trades').textContent(),/3 אירועי Paper/);
 assert.match(await authed.locator('#kpi-nav-source').textContent(),/Staging S3/);
 assert.equal((await authed.locator('#cloud-staging-results tr').count())>=3,true);
 assert.deepEqual(failures,[],'Portal JavaScript/runtime errors found');
 console.log('PORTAL_E2E_PASS: desktop/mobile, historic charts, paper ledger, Yahoo real-TQQQ simulator, cost and input recalculation');
} finally{await browser.close()}
})().catch(err=>{console.error('PORTAL_E2E_FAILURE',err);process.exitCode=1});
