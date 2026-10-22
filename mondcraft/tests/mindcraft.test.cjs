const {test}=require('node:test');
const assert=require('node:assert/strict');
const {loadMindcraft,executeSkill,verifySkillResult,verifyTransfer,placeVerifiedBlock,movementDistance}=require('../mindcraft-skills.cjs');
const {routeAgentChat,hasAgentRecipient,studioTravelTarget,survivalRoleTarget}=require('../chat-routing.cjs');
const {placementStandTargets,starterHouseBlocks,houseFootprintContains,houseStagingTarget}=require('../studio-house.cjs');
test('actual Mindcraft library supplies embodied collection crafting and living skills',async()=>{
 const {skills}=await loadMindcraft();
 for(const name of ['collectBlock','craftRecipe','smeltItem','placeBlock','consume','goToBed','giveToPlayer'])assert.equal(typeof skills[name],'function');
});
test('adapter rejects generated host code instead of executing it',async()=>{
 const bot={inventory:{items:()=>[]},output:'',entity:{position:{x:0,y:5,z:0}}};
 await assert.rejects(executeSkill(bot,'newAction',{code:'anything'}),/Unsupported action/);
 await assert.rejects(executeSkill(bot,'place',{item:'stone',x:500,y:5,z:0}),/nearby/);
});
test('inference slots serve waiting characters before new arrivals',async()=>{
 const {InferenceQueue}=require('../inference-queue.cjs');const queue=new InferenceQueue(1);const order=[];
 await queue.acquire();
 const first=queue.acquire().then(()=>order.push('first'));
 const second=queue.acquire().then(()=>order.push('second'));
 queue.release();await first;
 const third=queue.acquire().then(()=>order.push('third'));
 queue.release();await second;queue.release();await third;queue.release();
 assert.deepEqual(order,['first','second','third']);assert.equal(queue.active,0);
});
test('skill receipts require requested item deltas and exact placed-block readback',()=>{
 assert.equal(verifySkillResult('collect',{item:'oak_log',count:1},true,{}, {oak_sapling:4}),false);
 assert.equal(verifySkillResult('collect',{item:'oak_log',count:2},true,{oak_log:1},{oak_log:2}),false);
 assert.equal(verifySkillResult('collect',{item:'oak_log',count:1},true,{oak_log:1},{oak_log:2}),true);
 assert.equal(verifySkillResult('craft',{item:'crafting_table',count:1},true,{}, {crafting_table:1}),true);
 assert.equal(verifySkillResult('place',{item:'oak_planks'},true,{}, {},'air'),false);
 assert.equal(verifySkillResult('place',{item:'oak_planks'},true,{}, {},'oak_planks'),true);
});
test('direct agent chat is routed without action-status noise',()=>{
 const agent={name:'seven',messages:[]};
 assert.equal(routeAgentChat(agent,'llama','@seven Can you bring wood?'),true);
 assert.equal(routeAgentChat(agent,'seven','I will gather.'),false);
 assert.equal(routeAgentChat(agent,'llama','[llama] collect: gathered 2 oak_log'),false);
 assert.equal(routeAgentChat(agent,'llama','@seventeen meet me here'),false);
 assert.equal(routeAgentChat(agent,'Ghost','Can you help?'),true);
 assert.deepEqual(agent.messages,[{from:'llama',text:'@seven Can you bring wood?'},{from:'Ghost',text:'Can you help?'}]);
});
test('coordination chat is short and one-to-one',()=>{
 const names=new Set(['seven','llama','qwen']);
 assert.equal(hasAgentRecipient({name:'llama'},'@seven I have logs for you.',names),true);
 assert.equal(hasAgentRecipient({name:'llama'},'@seven @qwen I have logs.',names),false);
 assert.equal(hasAgentRecipient({name:'llama'},'@seven '+'x'.repeat(180),names),false);
});
test('studio roles receive concrete movement targets',()=>{
 const builder={x:49,y:4,z:-1};
 assert.deepEqual(studioTravelTarget('builder',builder),{x:48,y:5,z:0});
 const scoutTarget=studioTravelTarget('site scout',builder,{x:48,y:5,z:0},{x:48,y:5,z:0},'sniffles');
 assert.notDeepEqual(scoutTarget,{x:48,y:5,z:0});
 assert.deepEqual(studioTravelTarget('log supplier',builder),builder);
 assert.deepEqual(studioTravelTarget('plank supplier',builder),builder);
 assert.equal(studioTravelTarget(null,builder),null);
});
test('survival roles spread out to gather, scout, explore and defend home',()=>{
 const home={x:0,y:64,z:0};
 assert.deepEqual(survivalRoleTarget('builder',home,'llama',null,{oak_log:15}),home);
 assert.notDeepEqual(survivalRoleTarget('builder',home,'llama'),home);
 assert.deepEqual(survivalRoleTarget('defender',home),home);
 const gathering=survivalRoleTarget('gatherer',home,'gemma');
 const scouting=survivalRoleTarget('scout',home,'sniffles');
 assert.ok(Math.abs(Math.hypot(gathering.x,gathering.z)-12)<0.8);
 assert.ok(Math.abs(Math.hypot(scouting.x,scouting.z)-24)<0.8);
 assert.equal(survivalRoleTarget('gatherer',home,'gemma').x!==survivalRoleTarget('gatherer',home,'llama').x||survivalRoleTarget('gatherer',home,'gemma').z!==survivalRoleTarget('gatherer',home,'llama').z,true);
 assert.equal(survivalRoleTarget('gatherer',null),null);
});
test('house spectators move out of the build footprint to distinct waiting spots',()=>{
 const site={x:49,y:4,z:-2};
 assert.equal(houseFootprintContains({x:50,y:4,z:0},site),true);
 assert.equal(houseFootprintContains({x:48,y:4,z:0},site),false);
 const target=studioTravelTarget('house spectator',null,site,{x:50,y:4,z:0},'gemma');
 assert.ok(target);
 assert.equal(houseFootprintContains(target,site),false);
 assert.notDeepEqual(houseStagingTarget(site,'gemma'),houseStagingTarget(site,'qwen'));
});
test('house builder steps around the footprint to reach a floor support',()=>{
 assert.deepEqual(placementStandTargets({x:48,y:4,z:-1}),[
  {x:47,y:5,z:0},{x:50,y:5,z:0},{x:50,y:5,z:-3},{x:47,y:5,z:-3},
 ]);
 assert.equal(movementDistance(0.5),0.5);
 assert.equal(movementDistance(0),0.5);
 assert.equal(movementDistance(50),6);
 assert.equal(movementDistance(undefined),2);
 assert.deepEqual(starterHouseBlocks(48,4,-1)[0],{item:'oak_planks',x:49,y:4,z:2});
});
test('material handoffs require recipient inventory readback',()=>{
 assert.equal(verifyTransfer('oak_log',4,{oak_log:0},{oak_log:4}),true);
 assert.equal(verifyTransfer('oak_log',4,{oak_log:0},{oak_log:3}),false);
 assert.equal(verifyTransfer('oak_planks',4,{oak_planks:2},{oak_planks:5}),false);
 assert.equal(verifyTransfer('oak_log',4,{oak_log:0},{oak_log:0},true),true);
});
test('safe house placement retries adjacent faces and verifies the placed block',async()=>{
 const {Vec3}=require('vec3');let placedName='air';let attempts=0;
 const bot={entity:{position:new Vec3(1.5,4,1.5)},inventory:{items:()=>[{name:'oak_planks',type:5,count:8}]},output:'',
    blockAt(position){const pos=position.floored();if(pos.x===1&&pos.y===4&&pos.z===1)return {name:placedName,position:pos};if((pos.x===1&&pos.y===3&&pos.z===1)||(pos.x===0&&pos.y===4&&pos.z===1))return {name:'grass_block',boundingBox:'block',position:pos};return {name:'air',boundingBox:'empty',position:pos};},
  equip:async()=>{},lookAt:async()=>{},placeBlock:async()=>{attempts++;if(attempts===1)throw Error('first face blocked');placedName='oak_planks';}};
 assert.equal(await placeVerifiedBlock(bot,'oak_planks',1,4,1),true);
 assert.equal(attempts,2);
 assert.equal(bot.blockAt(new Vec3(1,4,1)).name,'oak_planks');
});
test('safe house placement never replaces an occupied block',async()=>{
 const {Vec3}=require('vec3');let calls=0;
 const bot={entity:{position:new Vec3(1,4,1)},inventory:{items:()=>[{name:'oak_planks',type:5,count:8}]},output:'',blockAt:()=>({name:'oak_log',boundingBox:'block',position:new Vec3(1,4,1)}),placeBlock:async()=>{calls++;}};
 await assert.rejects(placeVerifiedBlock(bot,'oak_planks',1,4,1),/Build only into air/);
 assert.equal(calls,0);
});
test('studio coordination messages target another character explicitly',()=>{
 const message='@seven I will gather oak logs; please choose the studio site.';
 const names=new Set(['seven','llama']);
 assert.equal(hasAgentRecipient({name:'llama'},message,names),true);
 assert.equal(hasAgentRecipient({name:'llama'},'@Ghost I need oak logs.',names),false);
 assert.equal(hasAgentRecipient({name:'llama'},'@llama I found the site.',names),false);
 assert.equal(hasAgentRecipient({name:'llama'},'@seventeen meet me.',names),false);
});