import test from 'node:test';
import assert from 'node:assert/strict';
import {versionsFor,chooseVersion,timelineFor,frameAt,keepRange} from '../assets/sprite-edit-workbench/instant/editor-model.mjs';
const frames=Array.from({length:10},()=>({duration_ticks:1}));
const draft={fps:10,speed:1,start:1,end:10,excluded:[]};
test('10 frames minus final 5 plays only first 5, with compact timeline',()=>{
 const t=timelineFor(frames,{...draft,excluded:[5,6,7,8,9]});
 assert.deepEqual(t.map(f=>f.index),[0,1,2,3,4]);assert.equal(t.at(-1).start+t.at(-1).duration,.5);
 assert.equal(frameAt(t,.45),4);
});
test('holes, empty selection, one frame and range boundaries',()=>{
 assert.deepEqual(timelineFor(frames,{...draft,excluded:[1,3],start:2,end:5}).map(f=>f.index),[2,4]);
 assert.equal(timelineFor(frames,{...draft,excluded:frames.map((_,i)=>i)}).length,0);
 assert.deepEqual(timelineFor(frames,{...draft,start:10}).map(f=>f.index),[9]);
});
test('retained holds stay intact; uniform timing and speed are explicit',()=>{
 const f=[{duration_ticks:4},{duration_ticks:7},{duration_ticks:2}];
 const d={...draft,end:3,excluded:[1],speed:2};
 assert.deepEqual(timelineFor(f,d).map(f=>f.duration),[.2,.1]);
 assert.deepEqual(timelineFor(f,{...d,timing:'uniform'}).map(f=>f.duration),[.05,.05]);
});
test('legacy order, append-only versions and remembered choice',()=>{
 const a={h3Candidate:{id:'h3',manifest:'h3/manifest.json'},compactCandidate:{id:'compact',manifest:'compact/manifest.json'},walkCandidate:{id:'trim',manifest:'trim/manifest.json'}};
 const before=versionsFor(a);assert.deepEqual(before.map(v=>v.id),['h3','compact','trim']);
 const after=versionsFor({...a,h3Candidate:{id:'h3-v2',manifest:'new/manifest.json'}},before);
 assert.deepEqual(after.map(v=>v.id),['h3','compact','trim','h3-v2']);
 assert.equal(chooseVersion(after), 'new/manifest.json');
 assert.equal(chooseVersion(after,'compact/manifest.json'),'compact/manifest.json');
 assert.equal(chooseVersion(after,'reference'),'reference');
 assert.equal(chooseVersion(after,'missing'),'new/manifest.json');
 const withGeneric=versionsFor({...a,candidates:[{id:'any-provider',manifest:'generic/manifest.json'}]},after);
 assert.equal(withGeneric.at(-1).id,'any-provider');
});
test('fresh browser respects generic chronological order and fractional frame holds',()=>{
 const versions=versionsFor({candidates:[{manifest:'v1.json'},{manifest:'v2.json'},{manifest:'v3.json'}]});
 assert.deepEqual(versions.map(v=>v.key),['v1.json','v2.json','v3.json']);
 assert.equal(chooseVersion(versions),'v3.json');
 const recalled=JSON.parse(JSON.stringify({idle:'v1.json',attack:'v2.json'}));
 assert.equal(chooseVersion(versions,recalled.idle),'v1.json');
 assert.equal(chooseVersion(versions,recalled.attack),'v2.json');
 assert.equal(timelineFor([{duration_ticks:.5}],{...draft,end:1})[0].duration,.05);
});

test('Shift range includes both ends, supports reverse and preserves outside selection',()=>{
 const excluded=Array.from({length:200},(_,i)=>i);
 const kept=keepRange(excluded,99,149);
 assert.equal(200-kept.length,51);
 assert.deepEqual(keepRange(excluded,149,99),kept);
 assert.deepEqual(keepRange([0,2,3,4,6],2,4),[0,6]);
 assert.deepEqual(keepRange([0,1,2],1,1),[0,2]);
 assert.equal(excluded.length,200);
});
