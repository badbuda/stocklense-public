import assert from 'node:assert/strict';
import {stagingSnapshot} from '../docs/portal-live.mjs';

const now=new Date('2026-10-20T07:00:00Z');
const sha='a'.repeat(64);
const meta={sha256:sha,version_id:'confirmed-version',saved_at_utc:'2026-10-20T01:30:00+00:00'};
const signal=(day,level=3,leverage=3)=>({
 session_date:day,status:'SIGNAL_S3_VERSIONED',
 signal:{...meta,level,target_leverage:leverage}
});
const paper=(day,equity)=>({
 ...signal(day),status:'SIGNAL_PAPER_CONTINUITY_S3_SHA_BOUND',
 paper:{...meta,sha256:'b'.repeat(64),equity,trade_count:0,continuity_status:'ON_TIME_QUALIFIED'}
});
const empty=(day)=>({session_date:day,status:'NO_STAGING_RECEIPT'});

let view=stagingSnapshot([signal('2026-10-19')],now);
assert.equal(view.status,'SIGNAL_ONLY_NO_RECENT_PAPER');
assert.equal(view.paper,null);
assert.equal(view.signal.session_date,'2026-10-19');
assert.deepEqual(view.paperSeries,[]);

view=stagingSnapshot([empty('2026-10-16'),paper('2026-10-19',102000)],now);
assert.equal(view.status,'VERIFIED_RECENT_PAPER_SUMMARIES');
assert.equal(view.paper.paper.equity,102000);
assert.deepEqual(view.paperSeries,[{date:'2026-10-19',s:102000,tradeCount:0}]);
assert.equal(view.paperSeries.reduce((sum,day)=>sum+day.tradeCount,0),0);

view=stagingSnapshot([paper('2026-10-16',100500),paper('2026-10-19',102000)],now);
assert.equal(view.status,'VERIFIED_RECENT_PAPER_SUMMARIES');
assert.equal(view.paperSeries.length,2);
assert.deepEqual(view.paperSeries.map(x=>x.tradeCount),[0,0]);
// Reproduces the authenticated S3 staging display from a genuine Paper row:
// paperSeries is a chart projection, not the raw API entry. Its trade count
// must survive projection so the UI never dereferences x.paper.trade_count.
const activeWithTrades={...paper('2026-10-19',102000),paper:{...paper('2026-10-19',102000).paper,trade_count:3}};
const withTrades=stagingSnapshot([paper('2026-10-16',100500),activeWithTrades],now);
assert.equal(withTrades.paperSeries.reduce((sum,row)=>sum+row.tradeCount,0),3);
assert.deepEqual(withTrades.paperSeries[1],{date:'2026-10-19',s:102000,tradeCount:3});

const gap=stagingSnapshot([
 paper('2026-10-15',100500),empty('2026-10-16'),paper('2026-10-19',102000)
],now);
assert.equal(gap.status,'PAPER_CHAIN_GAP');
assert.equal(gap.paper,null);

const invalid=stagingSnapshot([{session_date:'2026-10-16',status:'INVALID_EVIDENCE'},paper('2026-10-19',102000)],now);
assert.equal(invalid.status,'INVALID_EVIDENCE');
assert.equal(invalid.paper,null);

for(const bad of [
 {...paper('2026-10-19',102000),paper:{...paper('2026-10-19',102000).paper,sha256:'bad'}},
 {...paper('2026-10-19',102000),paper:{...paper('2026-10-19',102000).paper,continuity_status:'HALTED'}},
 paper('2026-10-19',NaN),
 {...paper('2026-10-19',102000),paper:{...paper('2026-10-19',102000).paper,trade_count:undefined}},
 {...paper('2026-10-19',102000),paper:{...paper('2026-10-19',102000).paper,trade_count:-1}},
 {...signal('2026-10-19'),signal:{...signal('2026-10-19').signal,version_id:'null'}},
]){
 assert.throws(()=>stagingSnapshot([bad],now),/UNVERIFIED/);
}
assert.throws(()=>stagingSnapshot([paper('2026-10-19',102000),paper('2026-10-19',102000)],now),/ORDER/);
assert.throws(()=>stagingSnapshot([paper('2026-10-21',102000)],now),/ORDER/);
assert.throws(()=>stagingSnapshot([paper('2026-02-30',102000)],now),/ORDER/);
assert.throws(()=>stagingSnapshot(Array.from({length:15},(_,i)=>empty('2026-10-01')),now),/UNTRUSTED/);
assert.equal(stagingSnapshot([signal('2026-10-15')],now).signal,null);
assert.equal(stagingSnapshot([signal('2026-10-19',0,0)],now).signal.signal.target_leverage,0);
console.log('PORTAL_PRIVATE_AWS_SOURCE_FAIL_CLOSED_TESTS_PASS');
