const COLORS = ['#ef476f','#06d6a0','#ffd166','#118ab2','#f78c6b','#a78bfa','#54c6eb','#f284b6','#91c483','#ff9f43','#5d9cec','#dd6e42','#b9cb55','#c679d9'];

function makeArena(players, size = 9) {
  if (!Array.isArray(players) || players.length < 2 || players.length > 14) throw new Error('Choose 2 to 14 local agents');
  const seen = new Set();
  const roster = players.map((player, index) => {
    if (!/^[a-z][a-z0-9_]{1,15}$/.test(player.name) || seen.has(player.name)) throw new Error('Invalid or duplicate character');
    seen.add(player.name);
    const angle = 2 * Math.PI * index / players.length;
    return {...player, color: COLORS[index], x: Math.round((size-1)/2 + Math.cos(angle)*(size-1)/2), z: Math.round((size-1)/2 + Math.sin(angle)*(size-1)/2), connected:false, wins:0, errors:0};
  });
  const occupied = new Set();
  for (const player of roster) {
    while (occupied.has(`${player.x},${player.z}`)) { player.x=(player.x+1)%size; if (!player.x) player.z=(player.z+1)%size; }
    occupied.add(`${player.x},${player.z}`);
  }
  const sectors = Array.from({length:size*size}, (_, index) => ({id:String.fromCharCode(65+index%size)+(Math.floor(index/size)+1), x:index%size,z:Math.floor(index/size),owner:null,strength:0,terrain:(index*17+Math.floor(index/size)*7)%11===0?'crystal':(index*13)%7===0?'grove':'grass'}));
  for (const player of roster) { const home=sectors[player.z*size+player.x];home.owner=player.name;home.strength=2; }
  return {size,players:roster,sectors,turn:0,round:0,status:'ready',active:null,events:[],winner:null,seed:2718};
}

function legalTargets(state, name) {
  const player=state.players.find(row=>row.name===name);
  if (!player) throw new Error('Unknown character');
  return state.sectors.filter(tile=>Math.abs(tile.x-player.x)+Math.abs(tile.z-player.z)<=1).map(tile=>({id:tile.id,owner:tile.owner,strength:tile.strength,terrain:tile.terrain,resource:tile.resource||null}));
}

function validateMove(state, name, move) {
  if (!move || !['claim','fortify','explore','gather'].includes(move.action) || typeof move.target!=='string') throw new Error('Use action claim, fortify, explore or gather and a target sector');
  const target=legalTargets(state,name).find(tile=>tile.id===move.target);
  if (!target) throw new Error('Target must be current or orthogonally adjacent');
  if (move.action==='fortify' && target.owner!==name) throw new Error('Only fortify your own territory');
  if (move.action==='gather' && (!target.resource||target.resource.remaining<1)) throw new Error('No resources remain in that sector');
  return state.sectors.find(tile=>tile.id===move.target);
}

function applyMove(state, name, move) {
  const target=validateMove(state,name,move);
  const player=state.players.find(row=>row.name===name);
  const previous=target.owner;
  player.x=target.x;player.z=target.z;
  if(move.action==='claim'||move.action==='fortify'){
    if (target.owner===name) target.strength=Math.min(3,target.strength+1);
    else if (target.owner && target.strength>1) target.strength-=1;
    else {target.owner=name;target.strength=1;player.wins+=1;}
  }
  player.visited=Array.from(new Set([...(player.visited||[]),target.id]));
  const event={turn:state.turn,agent:name,model:player.model,action:move.action,target:target.id,previous,owner:target.owner,strength:target.strength,reason:String(move.reason||'').slice(0,180),at:Date.now()};
  state.events.push(event);return event;
}

function scores(state) {
  return state.players.map(player=>({...player,tiles:state.sectors.filter(tile=>tile.owner===player.name).length,points:state.sectors.filter(tile=>tile.owner===player.name).reduce((sum,tile)=>sum+(tile.terrain==='crystal'?3:1),0)})).sort((left,right)=>right.points-left.points || right.tiles-left.tiles || left.name.localeCompare(right.name));
}

module.exports={makeArena,legalTargets,validateMove,applyMove,scores};