const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const {once}=require('node:events');
const squid=require('flying-squid');
const mineflayer=require('mineflayer');
const {pathfinder,Movements,goals}=require('mineflayer-pathfinder');
const {Vec3}=require('vec3');
const {makeArena,legalTargets,validateMove,applyMove,scores}=require('./arena.cjs');
const settings=require('flying-squid/config/default-settings.json');
const ROOT=path.resolve(__dirname,'..');
const SAVE=path.join(ROOT,'runtime','mondcraft','match.json');
const MC_PORT=Number(process.env.MONDCRAFT_MC_PORT||55918);
const PORT=Number(process.env.MONDCRAFT_PORT||6060);
const wool=['red','lime','yellow','blue','orange','purple','light_blue','pink','green','orange','cyan','brown','yellow','magenta'];
const bots=new Map();
let state=null,busy=false;
const server=squid.createMCServer({...settings,host:'127.0.0.1',port:MC_PORT,version:'1.16.5','online-mode':false,'everybody-op':false,'max-players':20,'view-distance':2,'max-entities':80,logging:false,gameMode:1,difficulty:0,worldFolder:path.join(ROOT,'runtime','mondcraft','world'),generation:{name:'superflat',options:{middleThickness:3,seed:2718}}});
const ready=Promise.all([once(server,'listening'),once(server,'pluginsReady')]);
ready.then(()=>{
 if(fs.existsSync(SAVE)){
  const saved=JSON.parse(fs.readFileSync(SAVE,'utf8'));
  if(saved.players?.length){
   state=saved;state.active=null;state.status='ready';
  return (async()=>{for(const player of state.players){player.connected=false;await connect(player);}for(const tile of state.sectors.filter(tile=>tile.owner))await marker(tile);await seedResources();persist();console.log('MONDCRAFT_CHARACTERS_RESTORED',state.players.length);})();
  }
 }
}).catch(error=>console.error('MONDCRAFT_RESTORE',error));
server.on('error',error=>console.error('MINECRAFT_ERROR',error));
server.on('newPlayer',player=>{
 server._sendPlayerList=target=>target._client.write('player_info',{
  action:'add_player',
  data:server.players.map(other=>({uuid:other.uuid,name:other.username,properties:other.profileProperties,gamemode:other.gameMode,ping:other._client.latency}))
 });
 player._client.on('chat',packet=>{
  if(player.username!=='Ghost'||!packet.message||packet.message.startsWith('/'))return;
  fetch('http://127.0.0.1:5050/api/mondcraft/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:packet.message})}).catch(error=>console.error('GAME_CHAT',error.message));
 });
 player.once('spawned',()=>{
  if(player.username!=='Ghost')return;
  const Item=require('prismarine-item')(server.registry);
  ['stone','oak_planks','glass','bricks','cobblestone','oak_log','oak_leaves','torch','white_wool'].forEach((name,index)=>{
   const item=new Item(server.registry.itemsByName[name].id,64);
   player.inventory.updateSlot(36+index,item);
   player._client.write('set_slot',{windowId:0,slot:36+index,item:Item.toNotch(item)});
  });
 });
});
const center=tile=>({x:(tile.x-4)*4,z:(tile.z-4)*4});

function persist(){if(!state)return;fs.mkdirSync(path.dirname(SAVE),{recursive:true});fs.writeFileSync(SAVE+'.tmp',JSON.stringify(state));fs.renameSync(SAVE+'.tmp',SAVE);}
function snapshot(){
 if(!state)return {status:'empty',minecraft:{port:MC_PORT,version:'1.16.5'},players:[],sectors:[],events:[]};
 return {...state,players:state.players.map(player=>({...player,position:bots.get(player.name)?.entity?.position||null,legal:legalTargets(state,player.name)})),scores:scores(state),minecraft:{port:MC_PORT,version:'1.16.5'}};
}
async function seedResources(){
 for(const tile of state.sectors){
  if(tile.resource)continue;
  const position=center(tile);const block=tile.terrain==='grove'?'oak_log':tile.terrain==='crystal'?'coal_ore':'stone';
  tile.resource={block,remaining:3};
  for(let level=0;level<3;level++){
   const location=new Vec3(position.x-1,5+level,position.z-1);
   if(await server.overworld.getBlockStateId(location)!==0){tile.resource.remaining=0;break;}
  }
  if(tile.resource.remaining)for(let level=0;level<3;level++)await server.setBlock(server.overworld,new Vec3(position.x-1,5+level,position.z-1),server.registry.blocksByName[block].minStateId);
 }
 for(const player of state.players){player.resources||={};player.visited||=[];}
}
async function marker(tile){
 const position=center(tile);const owner=state.players.findIndex(player=>player.name===tile.owner);
 for(let level=0;level<3;level++){
  const block=level<tile.strength&&owner>=0?server.registry.blocksByName[wool[owner]+'_wool'].minStateId:0;
  await server.setBlock(server.overworld,new Vec3(position.x+1,5+level,position.z+1),block);
 }
}
async function connect(player){
 const bot=mineflayer.createBot({host:'127.0.0.1',port:MC_PORT,version:'1.16.5',username:player.name,auth:'offline',checkTimeoutInterval:30000});
 bots.set(player.name,bot);bot.loadPlugin(pathfinder);
 bot.on('error',error=>{player.connected=false;player.lastError=error.message;persist();});
 bot.on('end',()=>{player.connected=false;persist();});
 const timer=setTimeout(()=>bot.end('spawn timeout'),25000);
 try{
  await once(bot,'spawn');
  const movement=new Movements(bot);movement.canDig=false;movement.allow1by1towers=false;movement.allowParkour=false;bot.pathfinder.setMovements(movement);bot.pathfinder.thinkTimeout=6000;
  const position=center(player);await server.getPlayer(player.name).teleport(new Vec3(position.x+0.5,5,position.z+0.5));
  server.getPlayer(player.name).sendSelfPosition(new Vec3(position.x+0.5,5,position.z+0.5));
  await bot.waitForTicks(2);
  player.connected=true;
 }finally{clearTimeout(timer);}
}
async function configure(players){
 if(busy)throw new Error('A turn is already executing');busy=true;
 try{
  await ready;
  if(state)for(const tile of state.sectors.filter(tile=>tile.owner)){tile.strength=0;await marker(tile);}
  for(const bot of bots.values())bot.quit();bots.clear();
  state=makeArena(players);state.matchId=Date.now().toString(36);state.createdAt=new Date().toISOString();
  for(const player of state.players)await connect(player);
  for(const tile of state.sectors.filter(tile=>tile.owner))await marker(tile);
  await seedResources();
  server.setTime(6000);server.doDaylightCycle=false;state.status='ready';persist();return snapshot();
 }finally{busy=false;}
}
async function move(name,decision){
 if(!state)throw new Error('No match configured');if(busy)throw new Error('Another turn is executing');
 const tile=validateMove(state,name,decision);const bot=bots.get(name);
 if(!bot?.entity||!state.players.find(player=>player.name===name)?.connected)throw new Error('Character is not connected');
 busy=true;state.active=name;state.status='moving';
 try{
  const position=center(tile);let timer;
  try{await Promise.race([bot.pathfinder.goto(new goals.GoalNear(position.x,5,position.z,1)),new Promise((_,reject)=>{timer=setTimeout(()=>{bot.pathfinder.setGoal(null);reject(new Error('Navigation timed out; no land awarded'));},12000);})]);}finally{clearTimeout(timer);}
  const actual=bot.entity.position;
  if(Math.abs(actual.x-(position.x+0.5))>1.9||Math.abs(actual.z-(position.z+0.5))>1.9)throw new Error('Character did not reach target; no land awarded');
  let harvested=null;
  if(decision.action==='gather'){
   const location=new Vec3(position.x-1,5+tile.resource.remaining-1,position.z-1);
   const block=bot.blockAt(location);
   if(!block||block.name!==tile.resource.block)throw new Error('Resource block is absent or changed; nothing awarded');
   await bot.dig(block,true);
   if(await server.overworld.getBlockStateId(location)!==0)throw new Error('Mining was not confirmed; nothing awarded');
   const player=state.players.find(row=>row.name===name);player.resources||={};
   const Item=require('prismarine-item')(server.registry);
   const itemId=server.registry.itemsByName[tile.resource.block].id;
   const inventory=server.getPlayer(name).inventory;
   const slot=inventory.slots.findIndex((item,index)=>index>=9&&index<=44&&(!item||item.type===itemId&&item.count<64));
   if(slot<0)throw new Error('Inventory is full; mined resource not credited');
   const count=(inventory.slots[slot]?.count||0)+1;const item=new Item(itemId,count);
   inventory.updateSlot(slot,item);server.getPlayer(name)._client.write('set_slot',{windowId:0,slot,item:Item.toNotch(item)});
   player.resources[tile.resource.block]=(player.resources[tile.resource.block]||0)+1;
   harvested={block:tile.resource.block,count:1,inventoryTotal:player.resources[tile.resource.block],position:location,blockRemoved:true};
  }
  const event=applyMove(state,name,decision);event.position={x:actual.x,y:actual.y,z:actual.z};
  if(harvested){tile.resource.remaining-=1;event.harvested=harvested;}
  if(decision.action==='claim'||decision.action==='fortify')await marker(tile);
  state.turn+=1;state.round=Math.floor(state.turn/state.players.length);persist();return {ok:true,event,state:snapshot()};
 }finally{busy=false;state.status='ready';state.active=null;persist();}
}
async function body(request){let raw='';for await(const chunk of request){raw+=chunk;if(raw.length>65536)throw new Error('Payload too large');}return JSON.parse(raw||'{}');}
const api=http.createServer(async(request,response)=>{
 response.setHeader('Content-Type','application/json');response.setHeader('Cache-Control','no-store');
 try{
  if(request.method==='GET'&&request.url==='/state'){response.end(JSON.stringify(snapshot()));return;}
  if(request.method==='POST'&&request.url==='/configure'){const data=await body(request);response.end(JSON.stringify(await configure(data.players)));return;}
  if(request.method==='POST'&&request.url==='/move'){const data=await body(request);response.end(JSON.stringify(await move(data.agent,data.move)));return;}
    if(request.method==='POST'&&request.url==='/say'){
     const data=await body(request);const message=`${String(data.agent||'World').slice(0,20)}: ${String(data.message||'').slice(0,600)}`;
     server.broadcast(message);if(state){state.events.push({agent:data.agent,action:'chat',reason:message,at:Date.now()});persist();}
     response.end(JSON.stringify({ok:true}));return;
    }
  if(request.method==='POST'&&request.url==='/event'){
   const data=await body(request);if(!state)throw new Error('No match');
   if(data.type==='missed'){const player=state.players.find(row=>row.name===data.agent);if(!player)throw new Error('Unknown character');player.errors+=1;state.events.push({turn:state.turn,agent:player.name,action:'missed',reason:String(data.reason||'').slice(0,300),at:Date.now()});state.turn+=1;state.round=Math.floor(state.turn/state.players.length);}
   else if(data.type==='finish'){const ranking=scores(state);const best=ranking.filter(row=>row.points===ranking[0].points&&row.tiles===ranking[0].tiles);state.status='finished';state.winner=best.map(row=>row.name);}
   else if(data.type==='thinking'){if(!state.players.some(row=>row.name===data.agent))throw new Error('Unknown character');state.active=data.agent;state.status='thinking';}
   else throw new Error('Unknown event');
   persist();response.end(JSON.stringify(snapshot()));return;
  }
  response.statusCode=404;response.end(JSON.stringify({error:'Not found'}));
 }catch(error){response.statusCode=400;response.end(JSON.stringify({error:error.message}));}
});
api.listen(PORT,'127.0.0.1',()=>console.log(`MONDCRAFT_API http://127.0.0.1:${PORT}`));
ready.then(()=>console.log(`MONDCRAFT_MINECRAFT 127.0.0.1:${MC_PORT}`));
process.on('SIGTERM',()=>{persist();for(const bot of bots.values())bot.quit();server._server.close();api.close();process.exit(0);});