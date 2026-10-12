(function(root){
'use strict';
const caps=[0,45,75,105,135,165,195], clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
function curve(z){return .38*Math.sin(z/520)+.22*Math.sin(z/1700);}
class Ride{
  constructor(){this.reset();}
  reset(){this.x=0;this.z=0;this.speed=0;this.gear=1;this.damage=0;this.score=0;this.elapsed=0;this.invincible=0;this.countdown=3;this.goTime=0;this.crashTime=0;this.impactId=0;this.passed=new Set();this.hit=new Set();this.state='ready';this.reason='';this.traffic=Array.from({length:12},(_,i)=>({id:i,z:8+Math.floor(i/2)*5,x:i%2?.35:-.35,color:['#dd7349','#c3d9d9','#639eaa','#e7b958'][i%4],speed:0,targetSpeed:25+(i%5)*3}));}
  start(){if(this.state==='ready')this.state='countdown';}
  update(dt,input){
    dt=clamp(dt,0,.05);
    this.crashTime=Math.max(0,this.crashTime-dt);
    if(this.state==='countdown'){
      if(input.valid){this.countdown-=dt;if(this.countdown<=0){this.state='running';this.goTime=.75;}}
      return;
    }
    if(this.state!=='running')return;
    if(!input.valid){this.reason='tracking';return;}
    const throttle=Number.isFinite(input.throttle)?clamp(input.throttle,0,1):1;
    this.reason='';this.goTime=Math.max(0,this.goTime-dt);this.gear=input.automatic?clamp(1+Math.floor(this.speed/33),1,6):clamp(Math.round(input.gear),1,6);this.elapsed+=dt;this.invincible=Math.max(0,this.invincible-dt);
    if(this.crashTime>0){this.speed=Math.max(0,this.speed-110*dt);this.z+=this.speed/3.6*dt;for(const car of this.traffic)car.z+=car.speed*dt;return;}
    const brake=clamp(Number(input.brake)||0,0,1);
    const off=Math.abs(this.x)>.95;
    if(input.incremental){
      // Wrist input is acceleration, not a requested speed. Neutral retains
      // momentum; the opposite wrist twist explicitly supplies the brake.
      const acceleration=brake>.05?-100*brake:throttle>.04?48*throttle:0;
      const limit=input.automatic?195:caps[this.gear];
      this.speed=clamp(this.speed+acceleration*dt,0,limit);
      if(off)this.speed=Math.max(0,this.speed-25*dt);
    }else{
      const target=(input.automatic?195:caps[this.gear])*throttle*(off?.48:1)*(brake>.05?0:1);
      this.speed+=clamp(target-this.speed,-(8+92*brake)*dt,32*dt);
    }
    this.x=clamp(this.x+input.steer*(.34+this.speed/165)*dt-curve(this.z)*this.speed*.0018*dt,-1.32,1.32);
    this.z+=this.speed/3.6*dt;
    for(const car of this.traffic){
      if(car.targetSpeed!==undefined)car.speed+=clamp(car.targetSpeed-car.speed,-10*dt,4.8*dt);
      car.z+=car.speed*dt;
      if(Math.abs(car.z-this.z)<4.5&&Math.abs(car.x-this.x)<.19&&this.invincible===0&&!this.hit.has(car.id)){
        this.damage++;this.speed*=.55;this.invincible=3;this.crashTime=2;this.impactId++;this.hit.add(car.id);
      }
      if(car.z<this.z-5&&!this.passed.has(car.id)){this.passed.add(car.id);this.score+=this.hit.has(car.id)?10:100;}
    }
    if(this.damage>=3)this.state='crashed';
    else if(this.z>=3000){this.state='finished';this.score+=Math.max(0,Math.round(3000-this.elapsed*10));}
  }
}
const api={Ride,curve,caps,clamp};if(typeof module!=='undefined')module.exports=api;else root.Highway=api;
})(typeof window!=='undefined'?window:globalThis);
