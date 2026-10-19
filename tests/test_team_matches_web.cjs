const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const context=vm.createContext({dayKey:d=>new Intl.DateTimeFormat('en-CA',{year:'numeric',month:'2-digit',day:'2-digit',timeZone:'America/Lima'}).format(d)});
vm.runInContext(fs.readFileSync('web/teams.js','utf8'),context);
const now=new Date('2026-10-19T16:00:00Z');
const played=[{status:'FINISHED',home_score:0,away_score:0,date:'2026-10-18'}];
const scheduled=[
 {fixture_id:'expired',status:'TIMED',date:'2026-10-19',kickoff_utc:'2026-10-19T15:00:00Z'},
 {fixture_id:'future',status:'TIMED',date:'2026-10-19',kickoff_utc:'2026-10-19T19:00:00Z'},
 {fixture_id:'stale',status:'SCHEDULED',date:'2026-10-18',kickoff_utc:null},
 {fixture_id:'unknown_time',status:'SCHEDULED',date:'2026-10-20',kickoff_utc:null},
 {fixture_id:'postponed',status:'POSTPONED',date:'2026-10-01',kickoff_utc:'2026-10-01T19:00:00Z'},
];
const result=context.teamFixtureLists({matches:{played,scheduled}},now);
assert.deepEqual(Array.from(result.upcoming,m=>m.fixture_id),['future','unknown_time','postponed']);
assert.equal(result.played,played);
assert.equal(context.teamFixtureLists({},now).upcoming.length,0);
// A missing kickoff on the Lima calendar day remains visible without inventing a time.
assert.equal(context.teamFixtureLists({matches:{scheduled:[{status:'SCHEDULED',date:'2026-10-19'}]}},new Date('2026-10-20T02:00:00Z')).upcoming.length,1);
console.log('Team match lists exclude expired fixtures, keep unknown dates explicit and preserve final scores.');
