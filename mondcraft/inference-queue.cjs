class InferenceQueue {
 constructor(limit=2){this.limit=limit;this.active=0;this.waiters=[];}
 acquire(){
  if(this.active<this.limit&&this.waiters.length===0){this.active++;return Promise.resolve();}
  return new Promise(resolve=>this.waiters.push(resolve));
 }
 release(){
  if(this.waiters.length)this.waiters.shift()();
  else this.active=Math.max(0,this.active-1);
 }
}
module.exports={InferenceQueue};