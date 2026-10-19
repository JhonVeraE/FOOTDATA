// Cross-language contract: browser combinations must match the archived engine.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const data=JSON.parse(fs.readFileSync(path.join(root,'web/data/fijas.json'),'utf8'));
class FrozenDate extends Date{constructor(...args){super(...(args.length?args:[data.generated_at]));}}
const context=vm.createContext({Date:FrozenDate});
vm.runInContext(fs.readFileSync(path.join(root,'web/fijas.js'),'utf8'),context);
for(const day of data.days)for(const expected of day.parlays){
 const actual=context.liveParlay(data.matches.filter(m=>m.date_lima===day.date_lima),expected.size);
 if(expected.status==='available'){
  assert(actual);assert(Math.abs(actual.probability-expected.probability)<1e-12);
  assert.deepEqual(Array.from(actual.legs,m=>m.fixture_id).sort(),expected.legs.map(m=>m.fixture_id).sort());
 }else assert.equal(actual,null);
}
// Expired fixture is excluded even when the frozen pool still contains it.
const base=data.matches.find(m=>m.parlay_selection),pool=[];
for(let i=0;i<3;i++)pool.push({...base,fixture_id:String(i),home:'H'+i,away:'A'+i});
pool[0].kickoff_utc='2000-01-01T00:00:00Z';assert.equal(context.liveParlay(pool,3),null);
console.log('Browser/backend accumulator contracts match for all seven dates; started fixture excluded.');
assert.equal(context.oddsComparison({minimum_odds:2.1,fair_odds:1.8},1),null);
assert.equal(context.oddsComparison({minimum_odds:2.1,fair_odds:1.8},2).above,false);
assert.equal(context.oddsComparison({minimum_odds:2.1,fair_odds:1.8},2).theoreticalBreakEven,true);
assert.equal(context.oddsComparison({minimum_odds:2.1,fair_odds:1.8},2.2).above,true);
console.log('Price comparator separates theoretical break-even from the adverse-scenario threshold.');
