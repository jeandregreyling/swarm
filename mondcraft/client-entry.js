window.addEventListener('load',async()=>{
  const Hotbar=customElements.get('pmui-hotbar');
  if(Hotbar){
    const original=Hotbar.prototype.reloadHotbarSelected;
    Hotbar.prototype.reloadHotbarSelected=function(slot){
      if(!Number.isInteger(slot)||slot<0||slot>8)return;
      return original.call(this,slot);
    };
  }
  const panel=document.createElement('div');
  panel.style.cssText='position:fixed;right:12px;top:12px;z-index:10000;display:flex;gap:6px;align-items:center;padding:8px;background:#14251de8;border:1px solid #607b55;border-radius:4px;color:#eaf4df;font:12px monospace';
  for(const event of ['pointerdown','mousedown','click','wheel'])panel.addEventListener(event,message=>message.stopPropagation());
  const selector=document.createElement('select');selector.setAttribute('aria-label','Find local agent');
  selector.style.cssText='max-width:140px;padding:6px;background:#263c29;color:white;border:1px solid #607b55;border-radius:3px';
  const button=document.createElement('button');button.textContent='Find Agent';
  button.style.cssText='padding:7px;background:#c6dd92;border:0;border-radius:3px;color:#18251b;cursor:pointer';
  const status=document.createElement('span');status.style.fontSize='10px';
  panel.append(selector,button,status);document.body.append(panel);
  let roster='';
  let observedBot;
  let intentionalDisconnect=false;
  setInterval(()=>{
    const gameBot=window.bot;
    if(!gameBot)return;
    if(gameBot!==observedBot){
      observedBot=gameBot;
      gameBot.on('spawn',()=>{intentionalDisconnect=false;sessionStorage.removeItem('mondcraft-next-reconnect');});
      gameBot.on('end',reason=>{intentionalDisconnect=/another location|logged in from another/i.test(String(reason));});
    }
    if(gameBot.entity&&gameBot._client?.socket&&!gameBot._client.socket.destroyed){sessionStorage.removeItem('mondcraft-next-reconnect');}
    if(!intentionalDisconnect&&gameBot.entity&&gameBot._client?.socket?.destroyed){
      const retryAt=Number(sessionStorage.getItem('mondcraft-next-reconnect')||0);
      if(Date.now()>=retryAt){sessionStorage.setItem('mondcraft-next-reconnect',String(Date.now()+10000));status.textContent='Connection lost; reconnecting...';setTimeout(()=>location.reload(),1000);}
    }
    if(!gameBot.players)return;
    const names=Object.keys(gameBot.players).filter(name=>name!=='Ghost').sort();
    if(names.join(',')===roster)return;roster=names.join(',');const previous=selector.value;
    selector.replaceChildren(...names.map(name=>{const option=document.createElement('option');option.value=name;option.textContent=name;return option;}));
    selector.value=names.includes(previous)?previous:names.includes('seven')?'seven':names[0]||'';
  },1000);
  button.onclick=async()=>{
    const target=window.bot?.players[selector.value]?.entity;
    if(!target){status.textContent='Character not visible yet';return;}
    button.disabled=true;status.textContent='Walking to '+selector.value;
    try{
      if(!window.bot.pathfinder)window.bot.loadPlugin(window.pathfinder.pathfinder);
      const movement=new window.pathfinder.Movements(window.bot);movement.canDig=false;movement.allow1by1towers=false;window.bot.pathfinder.setMovements(movement);
      let timer;
      try{await Promise.race([window.bot.pathfinder.goto(new window.pathfinder.goals.GoalNear(target.position.x,target.position.y,target.position.z,2)),new Promise((_,reject)=>{timer=setTimeout(()=>{window.bot.pathfinder.stop();reject(Error('Path not reachable'));},20000);})]);}finally{clearTimeout(timer);}
      await window.bot.lookAt(target.position.offset(0,1.5,0));status.textContent='At '+selector.value;
    }catch(error){status.textContent=error.message;}finally{button.disabled=false;}
  };
  if(new URLSearchParams(location.search).has('address'))return;
  await customElements.whenDefined('pmui-playscreen');
  const menu=document.getElementById('play-screen');
  menu.server='127.0.0.1';menu.serverport=55917;menu.proxy='';menu.proxyport='';menu.username='Ghost';menu.version='1.16.5';
  const title=document.getElementById('title-screen');if(title)title.style.display='none';
  menu.onConnectPress();
});