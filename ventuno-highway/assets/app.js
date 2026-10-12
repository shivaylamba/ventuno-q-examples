'use strict';
const $=id=>document.getElementById(id), canvas=$('game'), ctx=canvas.getContext('2d'), handCanvas=$('hands'), hc=handCanvas.getContext('2d');
const {Ride,curve,clamp}=Highway, ride=new Ride();
let w=0,h=0,dpr=1,controls={},received=0,steer=0,keys=new Set(),keyboardGear=1,lastPress=null,paused=false,last=performance.now(),frames=0,fpsAt=last,sound=false,audio=null,osc=null,gain=null,preview=true,raceView=null;
function resize(){dpr=Math.min(devicePixelRatio||1,1.6);w=innerWidth;h=innerHeight;canvas.width=w*dpr;canvas.height=h*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);handCanvas.width=640;handCanvas.height=480;raceView?.resize();}
addEventListener('resize',resize);resize();
import('./race3d.js?v=2').then(({CircuitView})=>{raceView=new CircuitView($('race3d'));$('race3d').hidden=false;canvas.hidden=true;$('graphics').textContent='3D CIRCUIT';}).catch(error=>{console.warn('3D unavailable; using lightweight road renderer:',error);$('graphics').textContent='2D FALLBACK';});
const isKeyboard=()=>$('mode').value==='keyboard';
const wristMode=()=>!isKeyboard()&&$('speed-mode').value==='wrist';
let throttleMessageUntil=0;
async function poll(){
  try{
    const response=await fetch('/api/controls',{cache:'no-store',signal:AbortSignal.timeout(2500)});
    if(!response.ok)throw Error();controls=await response.json();received=performance.now();
    if(lastPress!==null&&controls.press_id!==lastPress&&controls.knob_ready){
      if(ride.state==='ready')start();else if(['countdown','running'].includes(ride.state))paused=!paused;
    }
    lastPress=controls.press_id;
    $('tracking').textContent=controls.tracking?'HANDS TRACKED · '+controls.mode.toUpperCase():'RAISE HANDS INTO VIEW';
    $('tracking').classList.toggle('warning',!controls.tracking);
    $('hardware').textContent=wristMode()&&$('auto-gears').checked?'AUTOMATIC GEARS · reverse wrist to brake':controls.knob_ready?'KNOB CONNECTED · Gear '+controls.gear+' · Press to pause':'Knob unavailable · ↑ / ↓ shift gears';
    $('provider').textContent=controls.provider||controls.error||'Board hand tracker starting';
    $('start-status').textContent=isKeyboard()?'Keyboard test drive ready':controls.tracking?'Ready — hold your hands comfortably and press Start':controls.error||'Press Start, then raise your hands into view';
    const braking=(controls.brake||0)>.03,meter=braking?controls.brake:controls.throttle||0;
    $('throttle-label').textContent=braking?'WRIST BRAKE':'WRIST THROTTLE';$('throttle-value').textContent=Math.round(meter*100)+'%';$('throttle-fill').style.width=(meter*100)+'%';$('throttle-fill').style.background=braking?'#ef8c72':'#d8f586';
    if(performance.now()>throttleMessageUntil)$('throttle-status').textContent=controls.throttle_ready?(controls.throttle_valid?'Wrist throttle ready · twist to accelerate':'Throttle hand lost · show your right hand'):controls.throttle_rest_saved?'Now twist your right wrist and save the full-throttle pose':'Save relaxed wrist, then twist and save full throttle';
    drawHands(controls.hands||[]);
  }catch(_){controls.tracking=false;$('tracking').textContent='BOARD CONNECTION LOST';$('start-status').textContent='Waiting for board connection · keyboard test available';}
  setTimeout(poll,65);
}
poll();
function drawHands(hands){hc.clearRect(0,0,640,480);hc.strokeStyle='#d8f586';hc.fillStyle='#e8ffb2';hc.lineWidth=3;
  const lines=[[0,1,2,3,4],[0,5,6,7,8],[5,9,10,11,12],[9,13,14,15,16],[13,17,18,19,20],[0,17]];
  for(const hand of hands){const points=hand.landmarks||[];if(points.length!==21)continue;const pixel=points.some(p=>p[0]>2||p[1]>2);const p=points.map(v=>[640-(pixel?v[0]:v[0]*640),pixel?v[1]:v[1]*480]);for(const chain of lines){hc.beginPath();chain.forEach((i,j)=>j?hc.lineTo(...p[i]):hc.moveTo(...p[i]));hc.stroke();}for(const v of p){hc.beginPath();hc.arc(...v,3,0,Math.PI*2);hc.fill();}}
}
async function calibrate(){
  try{const r=await fetch('/api/calibrate',{method:'POST'});const d=await r.json();if(!r.ok)throw Error(d.error);$('start-status').textContent='Straight-ahead position set';$('calibrate').textContent='Calibrated ✓';setTimeout(()=>$('calibrate').textContent='Set hands as straight ahead',1800);return true;}
  catch(e){$('start-status').textContent=e.message||'Calibration failed';return false;}
}
let starting=false;
async function start(){if(starting)return;starting=true;try{if(!isKeyboard()){try{const response=await fetch('/api/start',{method:'POST',signal:AbortSignal.timeout(3000)});if(response.ok)Object.assign(controls,await response.json());}catch(_){}}ride.start();paused=false;$('welcome').hidden=true;$('finish').hidden=true;if(sound)await enableAudio();}finally{starting=false;}}
async function saveThrottle(pose){
  throttleMessageUntil=performance.now()+4500;
  try{const response=await fetch('/api/throttle/'+pose,{method:'POST'}),data=await response.json();if(!response.ok)throw Error(data.error||'Could not save wrist pose');Object.assign(controls,data);$('throttle-status').textContent=pose==='rest'?'Relaxed pose saved. Twist your right wrist, hold one second, then save full throttle.':'Full throttle saved. Relax your wrist and start the race.';}
  catch(error){$('throttle-status').textContent=error.message;}
}
$('throttle-rest').onclick=()=>saveThrottle('rest');$('throttle-full').onclick=()=>saveThrottle('full');
$('start').onclick=start;$('calibrate').onclick=calibrate;
$('again').onclick=()=>{ride.reset();keyboardGear=1;paused=false;$('finish').hidden=true;$('welcome').hidden=false;};
$('mode').onchange=()=>{$('start-status').textContent=isKeyboard()?'Keyboard test drive ready':'Hold hands up to steer';};
$('pause').onclick=()=>{if(['countdown','running'].includes(ride.state))paused=!paused;};
$('fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch(_){}};
$('camera-toggle').onclick=()=>{preview=!preview;$('camera-body').hidden=!preview;$('camera-toggle').textContent=preview?'−':'+';};
async function enableAudio(){audio??=new(window.AudioContext||window.webkitAudioContext)();await audio.resume();if(!osc){osc=audio.createOscillator();gain=audio.createGain();osc.type='sawtooth';gain.gain.value=0;osc.connect(gain);gain.connect(audio.destination);osc.start();}}
$('sound').onclick=async()=>{sound=!sound;if(sound)await enableAudio();$('sound').textContent=sound?'Sound on':'Sound off';};
addEventListener('keydown',e=>{if(['SELECT','INPUT'].includes(e.target.tagName))return;if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Space'].includes(e.code))e.preventDefault();keys.add(e.code);if(!e.repeat){if(e.code==='ArrowUp')keyboardGear=clamp(keyboardGear+1,1,6);if(e.code==='ArrowDown')keyboardGear=clamp(keyboardGear-1,1,6);if(e.code==='KeyP'&&['countdown','running'].includes(ride.state))paused=!paused;if(e.code==='Enter'&&ride.state==='ready')start();}});
addEventListener('keyup',e=>keys.delete(e.code));addEventListener('blur',()=>keys.clear());document.addEventListener('visibilitychange',()=>{if(document.hidden)keys.clear();});
function poly(points,color){ctx.fillStyle=color;ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.closePath();ctx.fill();}
function round(x,y,ww,hh,r,color){ctx.fillStyle=color;ctx.beginPath();ctx.roundRect(x,y,ww,hh,r);ctx.fill();}
function project(distance){const horizon=h*.34, depth=1/(1+distance/35);return {y:horizon+(h-horizon)*depth,half:w*.52*depth,x:w*.5-ride.x*w*.52*depth+(curve(ride.z+distance)-curve(ride.z))*w*.32*(1-depth)};}
function scenery(){
  const sky=ctx.createLinearGradient(0,0,0,h*.7);sky.addColorStop(0,'#81b5c6');sky.addColorStop(.55,'#d3d6bb');sky.addColorStop(1,'#cfb98d');ctx.fillStyle=sky;ctx.fillRect(0,0,w,h);
  ctx.fillStyle='#f5e6ae';ctx.beginPath();ctx.arc(w*.76,h*.22,h*.055,0,Math.PI*2);ctx.fill();
  for(let layer=0;layer<3;layer++){const baseline=h*(.34+layer*.017),amp=h*(.1-layer*.024);ctx.fillStyle=['#879e9a','#748b81','#627d69'][layer];ctx.beginPath();ctx.moveTo(0,baseline);for(let x=0;x<=w+10;x+=10){const yy=baseline-Math.abs(Math.sin(x/w*8.3+layer*2.1+curve(ride.z)*.2)+.4*Math.sin(x/w*23+layer))*amp;ctx.lineTo(x,yy);}ctx.lineTo(w,h);ctx.lineTo(0,h);ctx.fill();}
  ctx.fillStyle='#819564';ctx.fillRect(0,h*.38,w,h*.62);
}
function road(){
  for(let i=100;i>=0;i--){const far=project((i+1)*7),near=project(i*7),z=ride.z+i*7, stripe=Math.floor(z/14)%2;
    poly([[far.x-far.half*5,far.y],[far.x+far.half*5,far.y],[near.x+near.half*5,near.y],[near.x-near.half*5,near.y]],stripe?'#839566':'#7d9061');
    poly([[far.x-far.half*1.08,far.y],[far.x+far.half*1.08,far.y],[near.x+near.half*1.08,near.y],[near.x-near.half*1.08,near.y]],stripe?'#dedec5':'#c0644e');
    poly([[far.x-far.half,far.y],[far.x+far.half,far.y],[near.x+near.half,near.y],[near.x-near.half,near.y]],stripe?'#465056':'#444e54');
    for(const lane of [-.5,0,.5])if(Math.floor(z/11)%3!==0)poly([[far.x+far.half*(lane-.006),far.y],[far.x+far.half*(lane+.006),far.y],[near.x+near.half*(lane+.006),near.y],[near.x+near.half*(lane-.006),near.y]],'#d4d9c7');
  }
  for(let distance=600;distance>8;distance-=25){const dd=distance-(ride.z%25),p=project(dd),s=p.half*.11;for(const side of [-1,1]){const x=p.x+side*p.half*1.2;round(x-s*.08,p.y-s,s*.16,s,1,'#d7ddd0');round(x-s*.2,p.y-s*.9,s*.4,s*.23,1,'#627575');}}
}
function car(car){const distance=car.z-ride.z;if(distance<2||distance>650)return;const p=project(distance),s=p.half*.36,x=p.x+p.half*car.x,y=p.y;
  ctx.fillStyle='#172d3480';ctx.beginPath();ctx.ellipse(x,y,s*.65,s*.16,0,0,7);ctx.fill();
  round(x-s*.48,y-s*.16,s*.12,s*.35,2,'#17282e');round(x+s*.36,y-s*.16,s*.12,s*.35,2,'#17282e');
  poly([[x-s*.44,y],[x+s*.44,y],[x+s*.37,y-s*.58],[x-s*.37,y-s*.58]],car.color);
  poly([[x-s*.3,y-s*.35],[x+s*.3,y-s*.35],[x+s*.25,y-s*.77],[x-s*.25,y-s*.77]],car.color);
  poly([[x-s*.23,y-s*.42],[x+s*.23,y-s*.42],[x+s*.19,y-s*.65],[x-s*.19,y-s*.65]],'#244651');
  round(x-s*.34,y-s*.12,s*.16,s*.06,1,'#f89880');round(x+s*.18,y-s*.12,s*.16,s*.06,1,'#f89880');round(x-s*.4,y-s*.025,s*.8,s*.055,1,'#b8c6bb');
}
function bike(){
 const scale=Math.min(w/1300,h/820)*1.15;ctx.save();ctx.translate(w*.5,h*.88);ctx.scale(scale,scale);ctx.rotate(steer*.18);
 if(ride.invincible>0&&Math.floor(ride.invincible*12)%2)ctx.globalAlpha=.4;
 ctx.fillStyle='#102b3480';ctx.beginPath();ctx.ellipse(0,45,60,16,0,0,7);ctx.fill();
 round(-14,-37,28,102,12,'#152a32');round(-9,-33,18,90,8,'#273d45');
 poly([[-37,14],[37,14],[29,-80],[17,-106],[-17,-106],[-29,-80]],'#b8df72');
 poly([[-37,14],[-14,30],[-10,-51],[-24,-74]],'#718b46');poly([[37,14],[14,30],[10,-51],[24,-74]],'#718b46');
 round(-20,-5,40,13,4,'#ee765d');round(-25,16,50,9,4,'#c0ccba');
 ctx.strokeStyle='#1b2d36';ctx.lineWidth=13;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-19,-66);ctx.lineTo(-34,-27);ctx.lineTo(-38,10);ctx.moveTo(19,-66);ctx.lineTo(34,-27);ctx.lineTo(38,10);ctx.stroke();
 ctx.strokeStyle='#b4c8c7';ctx.lineWidth=5;ctx.beginPath();ctx.moveTo(-47,-103);ctx.lineTo(47,-103);ctx.stroke();
 ctx.strokeStyle='#2c444e';ctx.lineWidth=13;ctx.beginPath();ctx.moveTo(-19,-81);ctx.lineTo(-35,-94);ctx.lineTo(-46,-103);ctx.moveTo(19,-81);ctx.lineTo(35,-94);ctx.lineTo(46,-103);ctx.stroke();
 poly([[-22,-93],[22,-93],[27,-49],[-27,-49]],'#304b59');poly([[-7,-88],[7,-88],[10,-50],[-10,-50]],'#486473');
 ctx.fillStyle='#edf3dd';ctx.beginPath();ctx.ellipse(0,-111,21,25,0,0,7);ctx.fill();round(-15,-119,30,7,3,'#93b65a');ctx.restore();
}
function draw(dt){if(raceView){raceView.render(ride,steer,dt);return;}scenery();road();[...ride.traffic].sort((a,b)=>b.z-a.z).forEach(car);bike();if(Math.abs(ride.x)>.95&&ride.state==='running'){ctx.fillStyle='#de974617';ctx.fillRect(0,0,w,h);}}
function tick(now){const dt=Math.min(.05,(now-last)/1000);last=now;const fresh=now-received<500;
 let valid=isKeyboard()||(fresh&&controls.tracking),target=isKeyboard()?((keys.has('ArrowRight')?1:0)-(keys.has('ArrowLeft')?1:0)):(fresh?controls.steer||0:0);
 steer+=(target-steer)*(1-Math.exp(-dt/.08));const gear=isKeyboard()||!controls.knob_ready?keyboardGear:controls.gear;
 const throttle=wristMode()?(fresh&&controls.throttle_valid?controls.throttle||0:0):1;
 const brake=keys.has('Space')?1:wristMode()&&fresh&&controls.throttle_valid?controls.brake||0:0;
 // Hidden tabs temporarily suspend simulation; returning resumes automatically.
 // Only the explicit Pause button, P, or Knob sets a persistent manual pause.
 if(!paused&&!document.hidden)ride.update(dt,{valid,steer,gear,throttle,incremental:wristMode(),automatic:wristMode()&&$('auto-gears').checked,brake});
 $('steer-dot').style.left=(50+steer*45)+'%';$('speed').innerHTML=Math.round(ride.speed)+'<span>km/h</span>';$('gear').textContent=ride.gear;$('distance').innerHTML=(ride.z/1000).toFixed(2)+'<span>/ 3 km</span>';$('health').textContent='● '.repeat(3-ride.damage)+'○ '.repeat(ride.damage);$('score').textContent=ride.score;$('position').textContent=Math.min(13,1+ride.traffic.filter(r=>r.z>ride.z).length)+'/13';
 const active=['countdown','running'].includes(ride.state),message=paused?'Paused · press P or the Knob to resume':!valid?'Hands lost — raise your hands to continue.':ride.state==='countdown'?String(Math.max(1,Math.ceil(ride.countdown))):ride.goTime>0?'GO!':ride.crashTime>0?'CRASH!':null;
 $('notice').hidden=(!active||!message)&&ride.crashTime===0;$('notice').textContent=message||'CRASH!';$('notice').classList.toggle('race-number',valid&&!paused&&(ride.state==='countdown'||ride.goTime>0));$('pause').textContent=paused?'Resume':'Pause';
 if((ride.state==='crashed'||ride.state==='finished')&&ride.crashTime===0&&$('finish').hidden){$('finish').hidden=false;$('finish-label').textContent=ride.state==='finished'?'3 KM COMPLETE':'THREE COLLISIONS';$('finish-title').textContent=ride.state==='finished'?'Nice ride.':'Try another line.';$('finish-stats').textContent=`${(ride.z/1000).toFixed(2)} km · ${Math.round(ride.elapsed)} seconds · ${ride.score} points`;$('notice').hidden=true;}
 if(osc){osc.frequency.setTargetAtTime(35+ride.speed*1.4+(ride.gear?ride.speed/ride.gear:0),audio.currentTime,.08);gain.gain.setTargetAtTime(sound&&ride.state==='running'&&!paused&&valid?.025:0,audio.currentTime,.05);}
 draw(dt);frames++;if(now-fpsAt>=1000){$('fps').textContent=Math.round(frames*1000/(now-fpsAt))+' FPS';frames=0;fpsAt=now;}requestAnimationFrame(tick);
}
requestAnimationFrame(tick);
