const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const {once}=require('node:events');
process.env.MONDCRAFT_MC_PORT='55917';
const {createAgentBot,executeSkill,inventory,loadMindcraft,verifyTransfer}=require('./mindcraft-skills.cjs');
const {InferenceQueue}=require('./inference-queue.cjs');
const {routeAgentChat,hasAgentRecipient,studioTravelTarget,survivalRoleTarget}=require('./chat-routing.cjs');
const {createStarterHousePlan,houseFootprintContains,placementStandTargets}=require('./studio-house.cjs');
const ROOT=path.resolve(__dirname,'..');
const PROPERTIES=fs.readFileSync(path.join(ROOT,'runtime/mondcraft/native-server/server.properties'),'utf8');
const WORLD_NAME=PROPERTIES.match(/^level-name=(.*)$/m)?.[1]?.trim()||'world';
const SAVE=path.join(ROOT,'runtime/mondcraft',`population-${WORLD_NAME}.json`);
const HOME_FILE=path.join(ROOT,'runtime/mondcraft',`home-${WORLD_NAME}.json`);
let homePosition=null;
if(fs.existsSync(SAVE))try{const savedHome=JSON.parse(fs.readFileSync(HOME_FILE,'utf8'));if(savedHome.world===WORLD_NAME)homePosition=savedHome.position;}catch{}
const agents=new Map();
let running=true,paused=false,thinking=0;
const inferenceQueue=new InferenceQueue(2);
const wait=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
const allowed=new Set(['collect','craft','smelt','place','equip','eat','sleep','visit','give','move','say','defend','idle']);
const HOSTILE_MOBS=new Set(['blaze','cave_spider','creeper','drowned','elder_guardian','ender_dragon','enderman','endermite','evoker','ghast','guardian','hoglin','husk','illusioner','magma_cube','phantom','pillager','ravager','shulker','silverfish','skeleton','slime','spider','stray','vex','vindicator','witch','wither','wither_skeleton','zoglin','zombified_piglin','zombie','zombie_villager']);

function save(){fs.writeFileSync(SAVE+'.tmp',JSON.stringify({world:WORLD_NAME,home:homePosition,updatedAt:Date.now(),agents:[...agents.values()].map(agent=>({name:agent.name,model:agent.model,goal:agent.goal,assignment:agent.assignment,taskRole:agent.taskRole,roleWaypointKey:agent.roleWaypointKey,roleWaypointReached:agent.roleWaypointReached,houseBuild:agent.houseBuild,memory:agent.memory.slice(-8),lastResult:agent.lastResult,lastChatAt:agent.lastChatAt||0}))}));fs.renameSync(SAVE+'.tmp',SAVE);}
function snapshot(){return {status:running&&!paused?'living':'paused',mode:'native-survival-mindcraft',minecraft:{world:WORLD_NAME,home:homePosition,port:55917,version:'1.16.5'},inference:{active:inferenceQueue.active,limit:inferenceQueue.limit,queued:inferenceQueue.waiters.length},players:[...agents.values()].map(agent=>({name:agent.name,model:agent.model,connected:!!agent.bot?.entity&&agent.connected,position:agent.bot?.entity?.position,inventory:agent.bot?.inventory?inventory(agent.bot):{},health:agent.bot?.health,food:agent.bot?.food,gameMode:agent.bot?.game?.gameMode,status:agent.status,goal:agent.assignment||agent.goal,personalGoal:agent.goal,taskRole:agent.taskRole||null,lastResult:agent.lastResult})),events:[...agents.values()].flatMap(agent=>agent.memory).sort((left,right)=>left.at-right.at).slice(-50)};}
async function requestJson(url,body,timeout=300000){const response=await fetch(url,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(timeout)});const data=await response.json();if(!response.ok)throw Error(data.error||'Wrapper request failed');return data;}

function recordAction(agent,action,args,result,started){
 const receipt={agent:agent.name,model:agent.model,action,args,result,at:Date.now(),elapsed_s:(Date.now()-started)/1000};
 agent.lastResult=receipt;agent.memory.push(receipt);agent.memory=agent.memory.slice(-12);
 fs.appendFileSync(path.join(ROOT,'runtime/mondcraft/life.jsonl'),JSON.stringify(receipt)+'\n');save();
}

async function buildHouseStep(agent){
 const bot=agent.bot;
 if(!agent.houseBuild){
  const plan=createStarterHousePlan(bot,homePosition||{x:48,y:5,z:0});
  if(!plan){agent.houseBuild={status:'blocked: no flat clear footprint found'};agent.status=agent.houseBuild.status;save();return;}
  agent.houseBuild={status:'preparing',site:plan.site,blocks:plan.blocks,index:0};
  save();
 }
 const build=agent.houseBuild;
 if(build.status==='complete'||build.status.startsWith('blocked:')){agent.status=build.status;await wait(10000);return;}
 const blockers=[...agents.values()].filter(other=>other!==agent&&other.connected&&other.bot?.entity&&houseFootprintContains(other.bot.entity.position,build.site));
 if(blockers.length){agent.status=`waiting for ${blockers.length} players to clear house footprint`;await wait(500);return;}
 const stocks=inventory(bot);const plankBlocks=build.blocks.filter(block=>block.item==='oak_planks').length;
 if(build.blocks.some(block=>block.item==='crafting_table')&&!(stocks.crafting_table||0)){
  if((stocks.oak_planks||0)<4){
   if(!(stocks.oak_log||0)){build.status='blocked: no logs remain for the crafting table';agent.status=build.status;save();return;}
   const started=Date.now();let result;
   try{result=await executeSkill(bot,'craft',{item:'oak_planks',count:1});}
   catch(error){result={success:false,error:error.message,before:stocks,after:inventory(bot),output:bot.output};}
   recordAction(agent,'craft',{item:'oak_planks',count:1},result,started);
   if(!result.success){build.status='blocked: crafting-table planks were not verified';agent.status=build.status;save();return;}
   return;
  }
  const started=Date.now();let result;
  try{result=await executeSkill(bot,'craft',{item:'crafting_table',count:1});}
  catch(error){result={success:false,error:error.message,before:stocks,after:inventory(bot),output:bot.output};}
  recordAction(agent,'craft',{item:'crafting_table',count:1},result,started);
  if(!result.success){build.status='blocked: crafting table was not verified';agent.status=build.status;save();return;}
  return;
 }
 const plankDeficit=plankBlocks-(stocks.oak_planks||0);
 if(plankDeficit>0){
  const recipes=Math.ceil(plankDeficit/4);
  if((stocks.oak_log||0)<recipes){build.status='blocked: not enough oak logs for the clear-site house';agent.status=build.status;save();return;}
  const started=Date.now();let result;
  try{result=await executeSkill(bot,'craft',{item:'oak_planks',count:recipes});}
  catch(error){result={success:false,error:error.message,before:stocks,after:inventory(bot),output:bot.output};}
  recordAction(agent,'craft',{item:'oak_planks',count:recipes},result,started);
  if(!result.success){build.status='blocked: plank crafting was not verified';agent.status=build.status;save();return;}
  build.status='positioning at clear build site';agent.status=build.status;save();return;
 }
 if(build.status==='preparing'){
  build.status='positioning at clear build site';save();
 }
 if(build.status==='positioning at clear build site'){
  const target={x:build.site.x+1,y:build.site.y+1,z:build.site.z+5};
  const started=Date.now();let result;
  try{result=await executeSkill(bot,'move',target);}
  catch(error){result={success:false,error:error.message,before:inventory(bot),after:inventory(bot),output:bot.output};}
  recordAction(agent,'move',{...target,taskRole:'builder'},result,started);
  if(!result.success){build.status='blocked: could not reach the selected clear site';agent.status=build.status;save();return;}
  build.status='building verified starter house';agent.status=build.status;save();return;
 }
 const block=build.blocks[build.index];
 if(!block){
  const skipped=build.skipped?.length||0;
  build.status=skipped?`partial: ${build.blocks.length-skipped}/${build.blocks.length} blocks verified`:'complete';
  agent.status=skipped?build.status:'complete: starter house verified';save();
  bot.chat(skipped?`[llama] House partial: ${build.blocks.length-skipped}/${build.blocks.length} blocks verified; ${skipped} safe placements skipped.`:'[llama] Starter house complete; all planned blocks verified.');return;
 }
 const {Vec3}=require('vec3');const current=bot.blockAt(new Vec3(block.x,block.y,block.z));
 if(current?.name===block.item){build.index++;save();return;}
 if(!current||current.name!=='air'){build.status=`blocked: ${block.x},${block.y},${block.z} is ${current?.name||'unavailable'}`;agent.status=build.status;save();return;}
 const started=Date.now();let result;
 try{result=await executeSkill(bot,'place',block);}
 catch(error){result={success:false,error:error.message,before:inventory(bot),after:inventory(bot),output:bot.output};}
 if(result.success){
  build.index++;build.placementAttempts={};
  agent.status=`building house ${build.index}/${build.blocks.length}`;
  recordAction(agent,'place',block,result,started);
  if(build.index>=build.blocks.length){
   const skipped=build.skipped?.length||0;
   build.status=skipped?`partial: ${build.blocks.length-skipped}/${build.blocks.length} blocks verified`:'complete';
   agent.status=skipped?build.status:'complete: starter house verified';save();
   bot.chat(skipped?`[llama] House partial: ${build.blocks.length-skipped}/${build.blocks.length} blocks verified; ${skipped} safe placements skipped.`:'[llama] Starter house complete; all planned blocks verified.');return;
  }
  if(build.index%8===0)bot.chat(`[llama] House progress: ${build.index}/${build.blocks.length} blocks verified.`);
  await wait(250);return;
 }
 recordAction(agent,'place',block,result,started);
 if(result.targetBlock==='air'){
  build.placementAttempts=build.placementAttempts||{};
  const key=`${block.x},${block.y},${block.z}`;
  const attempts=build.placementAttempts[key]||0;
  if(attempts<3){
   build.placementAttempts[key]=attempts+1;
   const target={...placementStandTargets(block)[attempts],distance:0.5};const moveStarted=Date.now();let moved;
  try{moved=await executeSkill(bot,'move',target);}
  catch(error){moved={success:false,error:error.message,before:inventory(bot),after:inventory(bot),output:bot.output};}
  recordAction(agent,'move',{...target,reason:'reach next house support face'},moved,moveStarted);
  agent.status=moved.success?`repositioned for house block ${build.index+1}/${build.blocks.length}`:`trying alternate position for house block ${build.index+1}/${build.blocks.length}`;save();return;
  }
  build.skipped=build.skipped||[];build.skipped.push({block,reason:'placement failed after three safe approaches'});build.index++;build.placementAttempts[key]=0;save();
  agent.status=`continuing house; skipped obstructed target ${block.x},${block.y},${block.z}`;
  return;
 }
 build.status=`blocked: placement failed at ${block.x},${block.y},${block.z}`;agent.status=build.status;save();
}

async function live(agent){
 const bot=agent.bot;
 while(running&&agent.connected){
  try{
   while(paused&&running)await wait(300);
   if(!running)break;
    if(agent.taskRole==='defender'){
     const hostile=bot.nearestEntity(entity=>HOSTILE_MOBS.has(entity.name)&&bot.entity.position.distanceTo(entity.position)<=8);
     if(hostile){
      agent.status='defending home from '+hostile.name;const started=Date.now();let result;
      try{result=await executeSkill(bot,'defend',{});}
      catch(error){result={success:false,error:error.message,before:inventory(bot),after:inventory(bot),output:bot.output};}
      recordAction(agent,'defend',{mob:hostile.name},result,started);await wait(1000);continue;
     }
    }
    const builderPosition=agents.get('llama')?.bot?.entity?.position;
    const builderSite=agents.get('llama')?.houseBuild?.site||homePosition||{x:48,y:4,z:-1};
    const isFrontierTask=agent.assignment?.includes('frontier survival');
    const roleTarget=agent.assignment?(isFrontierTask?survivalRoleTarget(agent.taskRole,homePosition,agent.name,bot.entity.position,inventory(bot)):studioTravelTarget(agent.taskRole,builderPosition,builderSite,bot.entity.position,agent.name)):null;
    const roleTargetKey=roleTarget?`${agent.taskRole}:${roleTarget.x},${roleTarget.y},${roleTarget.z}`:null;
    if(agent.roleWaypointKey!==roleTargetKey){agent.roleWaypointKey=roleTargetKey;agent.roleWaypointReached=!roleTarget;save();}
    if(roleTarget&&!agent.roleWaypointReached&&bot.entity.position.distanceTo({x:roleTarget.x,y:roleTarget.y,z:roleTarget.z})<=4){agent.roleWaypointReached=true;save();}
    if(roleTarget&&!agent.roleWaypointReached){
     agent.status='moving to studio';
     const started=Date.now();let result;
     try{result=await executeSkill(bot,'move',{x:roleTarget.x,y:roleTarget.y,z:roleTarget.z});}
     catch(error){result={success:false,error:error.message,before:inventory(bot),after:inventory(bot),output:bot.output};}
     const receipt={agent:agent.name,model:agent.model,action:'move',args:{...roleTarget,taskRole:agent.taskRole},result,at:Date.now(),elapsed_s:(Date.now()-started)/1000};
     agent.lastResult=receipt;agent.memory.push(receipt);agent.memory=agent.memory.slice(-12);
     fs.appendFileSync(path.join(ROOT,'runtime/mondcraft/life.jsonl'),JSON.stringify(receipt)+'\n');save();
     await wait(result.success?1000:5000);
     continue;
    }
    const builderStock=inventory(bot);
    const builderReady=(builderStock.oak_log||0)>=15||(builderStock.oak_planks||0)>=54;
    if(agent.taskRole==='builder'&&agent.assignment?.toLowerCase().includes('starter house')&&builderReady){
     await buildHouseStep(agent);
     if(agent.houseBuild?.status!=='awaiting materials')continue;
    }
  agent.status='queued for local model';
  await inferenceQueue.acquire();
  if(!running){inferenceQueue.release();break;}
   thinking++;agent.status='thinking';
   let decision;
   try{
    const nearby=bot.findBlocks({matching:block=>block.name!=='air'&&block.name!=='grass_block'&&block.name!=='dirt'&&block.name!=='bedrock',maxDistance:24,count:80}).map(position=>{const block=bot.blockAt(position);return block?{name:block.name,x:position.x,y:position.y,z:position.z}:null;}).filter(Boolean);
    const nearbyEntities=Object.values(bot.entities||{}).filter(entity=>entity!==bot.entity&&entity.position&&bot.entity.position.distanceTo(entity.position)<=16).map(entity=>({name:entity.name||entity.username||'unknown',type:entity.type,position:{x:Math.round(entity.position.x),y:Math.round(entity.position.y),z:Math.round(entity.position.z)}})).slice(0,40);
      const messages=agent.messages.splice(0);
      agent.hasIncomingChat=messages.length>0;
    try{
    decision=await requestJson('http://127.0.0.1:5050/api/mondcraft/think',{agent:agent.name,state:{position:bot.entity.position,inventory:inventory(bot),health:bot.health,food:bot.food,nearby_blocks:nearby,nearby_entities:nearbyEntities,players:Object.keys(bot.players),home:homePosition,landmarks:homePosition?[{name:'home',...homePosition}]:[],can_initiate_chat:Date.now()-(agent.lastChatAt||0)>=90000,goal:agent.assignment||agent.goal,personal_goal:agent.goal,recent_results:agent.memory.slice(-3),last_error:agent.lastError||null,messages}});
    }catch(error){agent.messages.unshift(...messages);throw error;}
  }finally{thinking--;inferenceQueue.release();}
    if(!running)break;
    if(paused)continue;
    if(!allowed.has(decision.action))throw Error('Unknown embodied skill');
    if(decision.action==='say'){
      if(!hasAgentRecipient(agent,decision.args?.message,agents.keys()))throw Error('Address chat to another active agent with @name');
      if(Date.now()-(agent.lastChatAt||0)<90000&&!agent.hasIncomingChat)throw Error('Chat cooldown active; continue your assigned studio action and reply later');
     agent.lastChatAt=Date.now();
    }
    if(decision.action==='give'&&agent.taskRole==='log supplier'&&(decision.args?.player!=='qwen'||decision.args?.item!=='oak_log'))throw Error('Your studio role is to give oak_log directly to qwen');
    if(decision.action==='give'&&agent.taskRole==='plank supplier'&&(decision.args?.player!=='qwen'||decision.args?.item!=='oak_planks'))throw Error('Your studio role is to give oak_planks directly to qwen');
    const previous=agent.memory.at(-1);
    if(previous?.result?.success===false&&previous.action===decision.action&&JSON.stringify(previous.args)===JSON.stringify(decision.args||{}))throw Error('Repeated failed action blocked; choose a different action using the error and nearby block names');
   if(typeof decision.goal==='string')agent.goal=decision.goal.slice(0,240);
   if(decision.action==='idle'){agent.status='idle';await wait(3000);continue;}
   agent.status=decision.action;
  const before=inventory(bot);const transferTarget=decision.action==='give'?agents.get(decision.args.player):null;const targetBefore=transferTarget?.bot?.entity?inventory(transferTarget.bot):{};let transferObserved=false;
  const onPlayerCollect=(collector,collected)=>{if(collector?.username===transferTarget?.name&&collected?.name===decision.args.item)transferObserved=true;};
  if(transferTarget?.bot?.entity)bot.on('playerCollect',onPlayerCollect);
  const started=Date.now();let result;
   try{
    const action=executeSkill(bot,decision.action,decision.args||{});
    let timer;try{result=await Promise.race([action,new Promise((_,reject)=>{timer=setTimeout(()=>{reject(Error('Game skill timed out; character quarantined to prevent overlapping mutations'));},60000);})]);}catch(error){if(String(error.message).includes('timed out')){bot.interrupt_code=true;bot.pathfinder?.stop();agent.status='quarantined: skill timed out';agent.connected=false;bot.quit('Skill timed out; action halted');}throw error;}finally{clearTimeout(timer);}
  }catch(error){result={success:false,error:error.message,before,after:inventory(bot),output:bot.output};}
  finally{if(transferTarget?.bot?.entity)bot.off('playerCollect',onPlayerCollect);}
   if(decision.action==='give'&&transferTarget?.bot?.entity){await wait(500);const targetAfter=inventory(transferTarget.bot);const verified=verifyTransfer(decision.args.item,decision.args.count||1,targetBefore,targetAfter,transferObserved);result={...result,success:transferObserved||result.success!==false&&verified,transferObserved,recipient:transferTarget.name,recipientBefore:targetBefore,recipientAfter:targetAfter,output:String(result.output||'')+(verified?'\nRecipient pickup/inventory confirms transfer.':'\nRecipient inventory did not confirm transfer.')};}
   const receipt={agent:agent.name,model:agent.model,action:decision.action,args:decision.args,result,at:Date.now(),elapsed_s:(Date.now()-started)/1000};
   agent.lastResult=receipt;agent.memory.push(receipt);agent.memory=agent.memory.slice(-12);
   fs.appendFileSync(path.join(ROOT,'runtime/mondcraft/life.jsonl'),JSON.stringify(receipt)+'\n');save();
    bot.chat((result.success?`[${agent.name}] ${decision.action}: `:`[${agent.name}] failed ${decision.action}: `)+String(result.output||result.error||'done').replace(/\n/g,' ').slice(0,180));
    await wait(result.success?1000:5000);
  }catch(error){agent.status='waiting';agent.lastError=error.message;console.error('LIFE_ERROR',agent.name,error.message);await wait(5000);}
 }
}

async function connect(profile){
 const saved=fs.existsSync(SAVE)?JSON.parse(fs.readFileSync(SAVE,'utf8')).agents?.find(row=>row.name===profile.name):null;
 const agent={...profile,memory:saved?.memory||[],messages:[],lastChatAt:saved?.lastChatAt||0,assignment:saved?.assignment||null,taskRole:saved?.taskRole||null,roleWaypointKey:saved?.roleWaypointKey||null,roleWaypointReached:saved?.roleWaypointReached||false,houseBuild:saved?.houseBuild||null,goal:saved?.goal||'Live alongside Ghost and the other agents: gather wood, craft tools and a workbench, obtain food, and build a useful home with your actual materials. Choose your own plans.',status:'joining',connected:false};
 agent.memory=agent.memory.map(receipt=>{
  const result=receipt.result;
  if(receipt.action==='collect'&&result?.success&&Object.values(result.after||{}).reduce((sum,count)=>sum+count,0)<=Object.values(result.before||{}).reduce((sum,count)=>sum+count,0))return {...receipt,result:{...result,success:false,output:'Historical collection claim was unverified: inventory did not increase. Use actual inventory, exact block names and available resources.'}};
  return receipt;
 });
 const bot=await createAgentBot(agent.name);agent.bot=bot;agents.set(agent.name,agent);
 bot.on('error',error=>{agent.lastError=error.message;});bot.on('end',()=>{agent.connected=false;agent.status='disconnected';save();});
 bot.on('chat',(username,message)=>routeAgentChat(agent,username,message));
 await once(bot,'spawn');
 if(!homePosition){
  homePosition={x:Math.round(bot.entity.position.x),y:Math.floor(bot.entity.position.y),z:Math.round(bot.entity.position.z)};
  fs.mkdirSync(path.dirname(HOME_FILE),{recursive:true});
  fs.writeFileSync(HOME_FILE,JSON.stringify({world:WORLD_NAME,position:homePosition}));save();
 }
 if(bot.game.gameMode!=='survival'){agent.status='blocked: survival mode required';throw Error(agent.name+' is not in survival; autonomous actions blocked');}
 agent.connected=true;agent.status='ready';console.log('LIVING_CHARACTER_JOINED',agent.name,bot.game.gameMode,bot.entity.position.toString());return agent;
}

const api=http.createServer(async(request,response)=>{
 response.setHeader('Content-Type','application/json');response.setHeader('Cache-Control','no-store');
 try{
  if(request.method==='GET'&&request.url==='/state'){response.end(JSON.stringify(snapshot()));return;}
  let raw='';for await(const chunk of request){raw+=chunk;if(raw.length>16000)throw Error('Payload too large');}const data=JSON.parse(raw||'{}');
  if(request.method==='POST'&&request.url==='/task'){
   if(typeof data.goal!=='string'||!data.goal.trim()||data.goal.length>500||typeof data.message!=='string'||!data.message.trim())throw Error('A short shared goal and coordination message are required');
    if(data.roles!==undefined&&(!data.roles||typeof data.roles!=='object'||Array.isArray(data.roles)||Object.keys(data.roles).some(name=>!agents.has(name))||Object.values(data.roles).some(role=>typeof role!=='string'||role.length>40)))throw Error('Task roles must map active characters to short role names');
    if(data.notify!==undefined&&(!Array.isArray(data.notify)||data.notify.some(name=>typeof name!=='string'||!agents.has(name))))throw Error('Task notifications must target active character names');
    if(data.resetBuild!==undefined&&typeof data.resetBuild!=='boolean')throw Error('resetBuild must be a boolean');
    const notified=new Set(data.notify||agents.keys());
    for(const agent of agents.values()){agent.assignment=data.goal.slice(0,500);agent.taskRole=data.roles?.[agent.name]||null;agent.roleWaypointKey=null;agent.roleWaypointReached=false;if(data.resetBuild&&agent.taskRole==='builder')agent.houseBuild=null;if(notified.has(agent.name))agent.messages.push({from:'Ghost',text:data.message.slice(0,500)});}
   save();response.end(JSON.stringify({ok:true,agents:agents.size}));return;
  }
  if(request.method==='POST'&&request.url==='/say'){for(const agent of agents.values())agent.messages.push({from:'Ghost',text:String(data.message||'').slice(0,500)});response.end(JSON.stringify({ok:true}));return;}
  if(request.method==='POST'&&request.url==='/speak'){
   const agent=agents.get(data.agent);const message=data.message;
   if(!agent?.connected||!agent.bot?.entity)throw Error('Selected character is not connected to the native world');
   if(typeof message!=='string'||!message.trim()||message.startsWith('/')||message.length>180)throw Error('Reply must be 1 to 180 characters and cannot be a command');
   agent.bot.chat(message);response.end(JSON.stringify({ok:true,agent:agent.name}));return;
  }
  if(request.method==='POST'&&request.url==='/pause'){paused=!paused;response.end(JSON.stringify({ok:true,paused}));return;}
  if(request.method==='POST'&&request.url==='/stop'){paused=true;response.end(JSON.stringify({ok:true,paused}));return;}
  if(request.method==='POST'&&request.url==='/resume'){paused=false;response.end(JSON.stringify({ok:true,paused}));return;}
  response.statusCode=404;response.end(JSON.stringify({error:'Not found'}));
 }catch(error){response.statusCode=400;response.end(JSON.stringify({error:error.message}));}
});
api.listen(6062,'127.0.0.1',()=>console.log('MONDCRAFT_POPULATION http://127.0.0.1:6062'));
(async()=>{
 await loadMindcraft();const state=await requestJson('http://127.0.0.1:5050/api/mondcraft/state');
 const roster=state.roster.filter(player=>player.name!=='fred').concat(state.roster.filter(player=>player.name==='fred'));
 for(const profile of roster)await connect(profile);
 for(const agent of agents.values())live(agent);
})().catch(error=>{console.error('POPULATION_START_ERROR',error);process.exitCode=1;});