const {test}=require('node:test');
const assert=require('node:assert/strict');
const {makeArena,legalTargets,applyMove,scores}=require('../arena.cjs');
const players=[{name:'gemma',model:'gemma3:latest'},{name:'apex',model:'apex-direct:7b'}];
test('characters have distinct spawns and equal starting strength',()=>{
 const state=makeArena(Array.from({length:14},(_,index)=>({name:'agent_'+index,model:'local'})));
 assert.equal(new Set(state.players.map(row=>`${row.x},${row.z}`)).size,14);
 assert.equal(state.sectors.filter(tile=>tile.owner).length,14);
 assert.ok(state.sectors.filter(tile=>tile.owner).every(tile=>tile.strength===2));
});
test('server rejects remote movement and does not mutate the board',()=>{
 const state=makeArena(players);const before=JSON.stringify(state);
 assert.throws(()=>applyMove(state,'gemma',{action:'claim',target:'A1'}),/adjacent/);
 assert.equal(JSON.stringify(state),before);
});
test('actual moves claim adjacent ground and produce replay evidence',()=>{
 const state=makeArena(players);const target=legalTargets(state,'gemma').find(tile=>!tile.owner);
 const event=applyMove(state,'gemma',{action:'claim',target:target.id,reason:'Expand'});
 assert.equal(event.owner,'gemma');assert.equal(state.events.length,1);
 assert.equal(scores(state).find(row=>row.name==='gemma').tiles,2);
});
test('fortification cannot steal land and defended territory needs multiple attacks',()=>{
 const state=makeArena(players);const player=state.players[0];const target=state.sectors.find(tile=>tile.owner==='apex');
 player.x=target.x;player.z=target.z;
 assert.throws(()=>applyMove(state,'gemma',{action:'fortify',target:target.id}),/own territory/);
 applyMove(state,'gemma',{action:'claim',target:target.id});assert.equal(target.owner,'apex');
 applyMove(state,'gemma',{action:'claim',target:target.id});assert.equal(target.owner,'gemma');
});
test('invalid actors and actions never execute as host commands',()=>{
 const state=makeArena(players);
 assert.throws(()=>applyMove(state,'ghost',{action:'claim',target:'A1'}),/Unknown/);
 assert.throws(()=>applyMove(state,'gemma',{action:'shell',target:'A1'}),/action/);
});
test('exploration discovers without claiming or changing another agents land',()=>{
 const state=makeArena(players);const target=legalTargets(state,'gemma').find(tile=>!tile.owner);
 const event=applyMove(state,'gemma',{action:'explore',target:target.id});
 assert.equal(event.owner,null);assert.deepEqual(state.players[0].visited,[target.id]);
 assert.equal(scores(state).find(row=>row.name==='gemma').tiles,1);
});
test('gathering requires available resources and rule evaluation never mints inventory',()=>{
 const state=makeArena(players);const target=legalTargets(state,'gemma').find(tile=>!tile.owner);
 assert.throws(()=>applyMove(state,'gemma',{action:'gather',target:target.id}),/No resources/);
 const tile=state.sectors.find(row=>row.id===target.id);tile.resource={block:'oak_log',remaining:1};
 applyMove(state,'gemma',{action:'gather',target:target.id});
 assert.equal(tile.resource.remaining,1);assert.equal(state.players[0].resources,undefined);
});