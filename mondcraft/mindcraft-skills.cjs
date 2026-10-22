const path=require('node:path');
const os=require('node:os');
const {pathToFileURL}=require('node:url');
let runtime;

async function loadMindcraft(){
 if(!runtime)runtime=(async()=>{
  const root=process.env.MONDCRAFT_MINDCRAFT_ROOT||path.join(os.homedir(),'.local/share/mondcraft/mindcraft');
  const moduleUrl=name=>pathToFileURL(path.join(root,name)).href;
  const {setSettings}=await import(moduleUrl('src/agent/settings.js'));
    setSettings({minecraft_version:'1.16.5',host:'127.0.0.1',port:Number(process.env.MONDCRAFT_MC_PORT||55916),auth:'offline',allow_insecure_coding:false,narrate_behavior:true,block_place_delay:100});
  const skills=await import(moduleUrl('src/agent/library/skills.js'));
  const world=await import(moduleUrl('src/agent/library/world.js'));
  const mc=await import(moduleUrl('src/utils/mcdata.js'));
  return {skills,world,mc,root};
 })();
 return runtime;
}

async function createAgentBot(name){
 const {mc}=await loadMindcraft();
 const bot=mc.initBot(name);
 bot.output='';bot.interrupt_code=false;bot.restrict_to_inventory=true;
 const paused=new Set();
 bot.modes={isOn:()=>false,pause:name=>paused.add(name),unpause:name=>paused.delete(name),behavior_log:''};
 return bot;
}

function inventory(bot){return Object.fromEntries(bot.inventory.items().reduce((items,item)=>items.set(item.name,(items.get(item.name)||0)+item.count),new Map()));}
function count(value){if(!Number.isInteger(value)||value<1||value>16)throw Error('Quantity must be 1 to 16');return value;}
function item(value){if(typeof value!=='string'||!/^[a-z][a-z0-9_]{0,60}$/.test(value))throw Error('Invalid Minecraft item name');return value;}
function movementDistance(value){return Number.isFinite(value)?Math.min(6,Math.max(0.5,value)):2;}
function verifySkillResult(action,args,success,before,after,blockAtTarget){
 if(!success)return false;
 if(action==='collect'){
  const drop=({coal_ore:'coal',redstone_ore:'redstone',lapis_ore:'lapis_lazuli',diamond_ore:'diamond',emerald_ore:'emerald',nether_quartz_ore:'quartz'})[args.item]||args.item;
  return (after[drop]||0)-(before[drop]||0)>=(args.count||1);
 }
 if(action==='craft')return (after[args.item]||0)-(before[args.item]||0)>=(args.count||1);
 if(action==='place')return blockAtTarget===args.item;
 return true;
}
function verifyTransfer(itemName,count,before,after,observedByRecipient=false){return observedByRecipient||(after[itemName]||0)-(before[itemName]||0)>=count;}
async function placeVerifiedBlock(bot,blockType,x,y,z){
 if(!Number.isInteger(x)||!Number.isInteger(y)||!Number.isInteger(z)||y<1||y>128||Math.hypot(x-bot.entity.position.x,z-bot.entity.position.z)>32)throw Error('Placement must target a nearby block coordinate');
 const {Vec3}=require('vec3');const target=new Vec3(x,y,z);const current=bot.blockAt(target);
 if(!current||current.name!=='air')throw Error('Build only into air; never replace existing blocks');
 const stack=bot.inventory.items().find(row=>row.name===blockType);
 if(!stack)throw Error('Building material is not in inventory');
 const offsets=[new Vec3(0,-1,0),new Vec3(0,1,0),new Vec3(0,0,-1),new Vec3(0,0,1),new Vec3(-1,0,0),new Vec3(1,0,0)];
 const errors=[];
 for(const offset of offsets){
  const support=bot.blockAt(target.plus(offset));
  if(!support||support.boundingBox!=='block'||bot.entity.position.distanceTo(support.position)>4.5)continue;
  try{
   await bot.equip(stack,'hand');
   await bot.lookAt(support.position.offset(0.5,0.5,0.5));
   await bot.placeBlock(support,new Vec3(-offset.x,-offset.y,-offset.z));
   await new Promise(resolve=>setTimeout(resolve,200));
   const placed=bot.blockAt(target);
   if(placed?.name===blockType){bot.output+=`Placed ${blockType} at (${x}, ${y}, ${z}) and verified it.\n`;return true;}
   if(!placed||placed.name!=='air')throw Error(`Target changed to ${placed?.name||'unavailable'}`);
  }catch(error){errors.push(String(error.message||error).slice(0,100));}
 }
 bot.output+=`Placement at (${x}, ${y}, ${z}) not verified${errors.length?': '+errors.join('; '):': no reachable solid support face'}.\n`;
 return false;
}

async function executeSkill(bot,action,args={}){
 const {skills}=await loadMindcraft();
 const before=inventory(bot);bot.output='';bot.interrupt_code=false;
 let success;
 switch(action){
  case 'say':if(typeof args.message!=='string'||!args.message.trim()||args.message.startsWith('/')||args.message.length>240)throw Error('Use a short Minecraft message, not a slash command');bot.chat(args.message);success=true;bot.output+='Minecraft chat sent.\n';break;
  case 'move':{
   if(['x','y','z'].some(key=>!Number.isFinite(args[key]))||args.y<1||args.y>128||Math.hypot(args.x-bot.entity.position.x,args.z-bot.entity.position.z)>96)throw Error('Move to a nearby valid world coordinate');
  success=await skills.goToPosition(bot,args.x,args.y,args.z,movementDistance(args.distance));break;
  }
  case 'collect':success=await skills.collectBlock(bot,item(args.item),count(args.count||1));break;
  case 'craft':success=await skills.craftRecipe(bot,item(args.item),count(args.count||1));break;
  case 'smelt':success=await skills.smeltItem(bot,item(args.item),count(args.count||1));break;
  case 'equip':if(!bot.inventory.items().some(row=>row.name===args.item))throw Error('Item must already be in inventory');success=await skills.equip(bot,item(args.item));break;
  case 'eat':success=await skills.consume(bot,item(args.item));break;
  case 'defend':success=await skills.defendSelf(bot,8);bot.output+=success?'Nearby hostiles repelled.\n':'No hostile mobs within guard range.\n';break;
  case 'sleep':success=await skills.goToBed(bot);break;
  case 'visit':if(typeof args.player!=='string'||!bot.players[args.player])throw Error('Player is not in this world');success=await skills.goToPlayer(bot,args.player,3);break;
  case 'give':{
   if(typeof args.player!=='string'||!bot.players[args.player]?.entity)throw Error('Player is not in this world');
   const quantity=count(args.count||1);const itemName=item(args.item);
   await skills.goToPlayer(bot,args.player,1);
   const recipient=bot.players[args.player]?.entity;
   if(!recipient||bot.entity.position.distanceTo(recipient.position)>1.5){bot.output+='Could not reach pickup range for '+args.player+'.\n';success=false;break;}
   await bot.lookAt(recipient.position);
   success=await skills.discard(bot,itemName,quantity);
   break;
  }
  case 'place':{
   const location=['x','y','z'].map(key=>args[key]);
   if(location.some(value=>!Number.isInteger(value))||Math.hypot(args.x-bot.entity.position.x,args.z-bot.entity.position.z)>32||args.y<1||args.y>128)throw Error('Placement must be a nearby valid block coordinate');
  success=await placeVerifiedBlock(bot,item(args.item),args.x,args.y,args.z);break;
  }
  default:throw Error('Unsupported action; no host-code or cheat execution is available');
 }
 const after=inventory(bot);
 const targetBlock=action==='place'?bot.blockAt(new (require('vec3').Vec3)(args.x,args.y,args.z))?.name:null;
 const verified=verifySkillResult(action,args,success!==false,before,after,targetBlock);
 if(!verified)bot.output+='Backend readback did not verify the requested item/count/block; action is recorded as unsuccessful.\n';
 return {action,args,success:verified,before,after,targetBlock,output:bot.output,health:bot.health,food:bot.food,position:bot.entity.position};
}

module.exports={loadMindcraft,createAgentBot,executeSkill,inventory,verifySkillResult,verifyTransfer,placeVerifiedBlock,movementDistance};