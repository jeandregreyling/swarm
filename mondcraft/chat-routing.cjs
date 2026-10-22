const STATUS_ACTIONS='collect|craft|smelt|place|equip|eat|sleep|visit|give|move|say|idle';
const STATUS_BROADCAST=new RegExp(`^\\[[\\w-]+\\] (?:failed )?(?:${STATUS_ACTIONS}): `);

function routeAgentChat(agent,username,message){
 if(!message||username===agent.name||STATUS_BROADCAST.test(message))return false;
 if(username!=='Ghost'&&!new RegExp(`(?:^|\\s)@${agent.name}(?=$|\\s|[.,!?;:])`).test(message))return false;
 agent.messages.push({from:username,text:message.slice(0,500)});
 return true;
}

function hasAgentRecipient(agent,message,agentNames){
 const available=new Set(agentNames);
 const recipients=new Set([...String(message||'').matchAll(/(?:^|\s)@([a-z0-9_-]+)(?=$|\s|[.,!?;:])/gi)]
	.map(match=>match[1].toLowerCase())
	.filter(name=>name!==agent.name.toLowerCase()&&available.has(name)));
 return String(message||'').length<=180&&recipients.size===1;
}

function studioTravelTarget(role,builderPosition,site={x:48,y:5,z:0},position=null,agentName='agent'){
 if(role==='builder')return site;
 if(role==='site scout'){
  const {houseStagingTarget}=require('./studio-house.cjs');
  return houseStagingTarget(site,agentName);
 }
 if(role==='log supplier'||role==='plank supplier')return builderPosition||null;
 if(role==='house spectator'&&position){
  const {houseFootprintContains,houseStagingTarget}=require('./studio-house.cjs');
  if(houseFootprintContains(position,site))return houseStagingTarget(site,agentName);
 }
 return null;
}

function survivalRoleTarget(role,home,agentName='agent',position=null,stock={}){
 if(!home)return null;
 const gathered=(stock.oak_log||0)+(stock.oak_planks||0);
 if(role==='defender')return home;
 if(role==='builder')return (stock.oak_log||0)>=15||(stock.oak_planks||0)>=54?home:roleGatherTarget('gatherer',home,agentName);
 if(!['gatherer','scout','explorer'].includes(role))return null;
 if(role==='gatherer'&&gathered>=10)return home;
 return roleGatherTarget(role,home,agentName);
}

function roleGatherTarget(role,home,agentName){
 const hash=[...agentName].reduce((value,char)=>(value*31+char.charCodeAt(0))>>>0,7);
 const angle=(hash%360)*Math.PI/180;const distance=role==='gatherer'?12:role==='scout'?24:40;
 return {x:Math.round(home.x+Math.cos(angle)*distance),y:home.y,z:Math.round(home.z+Math.sin(angle)*distance)};
}

module.exports={routeAgentChat,hasAgentRecipient,studioTravelTarget,survivalRoleTarget};