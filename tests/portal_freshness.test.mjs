import assert from 'node:assert/strict';
import {publicationFreshness, publicationMessage} from '../docs/portal-freshness.mjs';

const same = d => ({signalDate:d,paperDate:d,historyDate:d,riskDate:d});
const at = d => new Date(d+'T12:00:00Z');

const fresh=publicationFreshness(same('2026-10-16'),at('2026-10-17'));
assert.equal(fresh.healthy,true);
assert.match(publicationMessage(fresh),/GitHub/);

const longWeekend=publicationFreshness(same('2026-10-16'),at('2026-10-20'));
assert.equal(longWeekend.healthy,true, 'ordinary long holiday weekend must not cause false stale');

const broken=publicationFreshness(same('2026-10-09'),at('2026-10-17'));
assert.equal(broken.healthy,false);
assert.equal(broken.oldestDate,'2026-10-09');
assert.deepEqual(broken.stale,['signal','paper','history','risk']);
assert.match(publicationMessage(broken),/מיושנים/);

const mismatch=publicationFreshness({...same('2026-10-16'),paperDate:'2026-10-15'},at('2026-10-17'));
assert.equal(mismatch.inconsistent,true);
assert.equal(mismatch.healthy,false);
assert.match(publicationMessage(mismatch),/פער תאריכים/);

const future=publicationFreshness({...same('2026-10-16'),paperDate:'2026-10-19'},at('2026-10-17'));
assert.deepEqual(future.invalid,['paper']);
assert.equal(future.healthy,false);

for(const invalid of ['2026-02-30','2026-10-9','10/16/2026',undefined,'']){
  const result=publicationFreshness({...same('2026-10-16'),paperDate:invalid},at('2026-10-17'));
  assert.ok(result.invalid.includes('paper'));
}
assert.throws(()=>publicationFreshness(same('2026-10-16'),new Date(NaN)),/INVALID_FRESHNESS_CLOCK/);
console.log('PORTAL_PUBLICATION_FRESHNESS_TESTS_PASS');
