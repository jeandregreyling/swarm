const {Vec3}=require('vec3');

const AIR=new Set(['air','cave_air','void_air']);

function starterHouseBlocks(x,y,z){
 const blocks=[];
 const floor=[];
 for(let dx=0;dx<4;dx++)for(let dz=0;dz<4;dz++)floor.push({item:'oak_planks',x:x+dx,y,z:z+dz});
 floor.sort((left,right)=>Math.hypot(left.x-(x+1.5),left.z-(z+3.5))-Math.hypot(right.x-(x+1.5),right.z-(z+3.5)));
 blocks.push(...floor);
 const walls=new Map();
 for(let height=1;height<=2;height++){
  for(let offset=0;offset<4;offset++){
   for(const [blockX,blockZ] of [[x+offset,z],[x+offset,z+3],[x,z+offset],[x+3,z+offset]]){
    if(height<=2&&blockX===x+1&&blockZ===z)continue;
     const block={item:'oak_planks',x:blockX,y:y+height,z:blockZ};
     walls.set(`${block.x},${block.y},${block.z}`,block);
   }
  }
 }
 blocks.push(...walls.values());
 for(let dx=0;dx<4;dx++)for(let dz=0;dz<4;dz++)blocks.push({item:'oak_planks',x:x+dx,y:y+3,z:z+dz});
 blocks.push({item:'crafting_table',x:x+2,y:y+1,z:z+2});
 return blocks;
}

function createStarterHousePlan(bot,center={x:48,y:5,z:0}){
 const starts=[];
 for(let x=Math.round(center.x)-5;x<=Math.round(center.x)+3;x++){
  for(let z=Math.round(center.z)-5;z<=Math.round(center.z)+3;z++)starts.push({x,z,distance:Math.hypot(x+1.5-center.x,z+1.5-center.z)});
 }
 starts.sort((left,right)=>left.distance-right.distance);
 const heights=[Math.round(center.y)-1,Math.round(center.y),Math.round(center.y)-2,Math.round(center.y)+1];
 for(const floorY of heights){
  for(const start of starts){
   let supported=true;
   for(let dx=0;dx<4&&supported;dx++)for(let dz=0;dz<4;dz++){
    const support=bot.blockAt(new Vec3(start.x+dx,floorY-1,start.z+dz));
    if(!support||support.boundingBox!=='block'){supported=false;break;}
   }
   if(!supported)continue;
   const blocks=starterHouseBlocks(start.x,floorY,start.z);
   if(blocks.every(target=>{const block=bot.blockAt(new Vec3(target.x,target.y,target.z));return block&&AIR.has(block.name);}))return {site:{x:start.x,y:floorY,z:start.z},blocks};
  }
 }
 return null;
}

function houseFootprintContains(position,site){
 if(!position||!site)return false;
 const x=Math.floor(position.x),y=Math.floor(position.y),z=Math.floor(position.z);
 return x>=site.x&&x<site.x+4&&z>=site.z&&z<site.z+4&&y>=site.y-1&&y<=site.y+3;
}

function houseStagingTarget(site,name='agent'){
 const index=[...name].reduce((sum,char)=>sum+char.charCodeAt(0),0)%8;
 const ring=[[-3,6],[-1,7],[2,7],[4,5],[4,2],[2,-4],[-2,-4],[-4,1]];
 const [dx,dz]=ring[index];
 return {x:site.x+2+dx,y:site.y+1,z:site.z+2+dz};
}

function placementStandTargets(block){
 return [
  {x:block.x-1,y:block.y+1,z:block.z+1},
  {x:block.x+2,y:block.y+1,z:block.z+1},
  {x:block.x+2,y:block.y+1,z:block.z-2},
  {x:block.x-1,y:block.y+1,z:block.z-2},
 ];
}

module.exports={createStarterHousePlan,starterHouseBlocks,houseFootprintContains,houseStagingTarget,placementStandTargets};