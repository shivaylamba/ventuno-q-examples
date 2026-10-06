// SPDX-License-Identifier: MPL-2.0
'use strict';
const $=id=>document.getElementById(id);
let opened=false,connected=false,latest=null,pending=false,modePending=false,starting=false;
let context=null,source=null,buffer=null,bufferId=null,loading=false,handled=null,firstStatus=true;
let targetX=0,targetY=0,drawX=0,drawY=0,previousRound=null;
document.body.classList.add('welcome-open');
function message(text=''){$('message').textContent=text;}
async function unlock(){context??=new(window.AudioContext||window.webkitAudioContext)();if(context.state==='suspended')await context.resume();}
function stopAudio(){if(source){source.onended=null;try{source.stop();}catch(_){}source=null;}}
function audioItem(){if(!latest)return null;return latest.game.phase==='result'?latest.ai.reaction:latest.game.phase==='idle'?latest.ai.mission:null;}
async function play(){if(!buffer)return;await unlock();stopAudio();const playing=context.createBufferSource();playing.buffer=buffer;playing.connect(context.destination);source=playing;playing.onended=()=>{if(source===playing){source=null;$('audio-status').textContent='Adventure played on laptop';}};playing.start();$('audio-status').textContent='Your narrator is speaking…';}
async function loadAudio(item,auto=true){
  if(!item?.audio_id||loading)return;loading=true;
  try{await unlock();const response=await fetch('/api/audio/'+item.audio_id,{cache:'no-store',signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error();const decoded=await context.decodeAudioData(await response.arrayBuffer());if(audioItem()?.audio_id!==item.audio_id)return;buffer=decoded;bufferId=item.audio_id;handled=item.audio_id;$('audio-status').textContent='Narration ready';if(auto&&$('speech').checked)await play();}
  catch(_){handled=item.audio_id;$('audio-status').textContent='Select Hear it again to retry laptop speech.';}
  finally{loading=false;}
}
function renderGame(g){
  const busy=['calibrating','active'].includes(g.phase);
  if(previousRound!==g.round_id){previousRound=g.round_id;stopAudio();buffer=null;bufferId=null;handled=null;$('audio-status').textContent='';}
  targetX=Math.max(-22,Math.min(22,g.tilt_x));targetY=Math.max(-22,Math.min(22,g.tilt_y));
  $('angle').textContent=g.sensor_ready?g.angle.toFixed(1)+'°':'—';$('gyro').textContent=g.sensor_ready?g.gyro.toFixed(1)+'°/s':'—';$('best').textContent=g.best_hold.toFixed(1)+'s';
  $('stage').classList.toggle('warning',g.phase==='active'&&!g.steady);$('stage').classList.toggle('hatched',g.phase==='result'&&g.result?.won);
  const hatched=g.phase==='result'&&Boolean(g.result?.won);
  $('egg').toggleAttribute('hidden',hatched);$('dragon').toggleAttribute('hidden',!hatched);
  $('score-row').hidden=g.phase!=='result';$('cancel').hidden=!busy;
  $('start').disabled=!connected||!g.sensor_ready||busy||starting;
  $('start').innerHTML=(g.phase==='result'?'Try another egg':'Start a round')+' <span>↗</span>';
  $('time-left').textContent=g.phase==='active'?g.remaining.toFixed(0)+' seconds left · '+g.round_difficulty+' · '+g.resets+' hold restarts':'';
  $('held').textContent=g.held.toFixed(1)+' / 5.0s';$('hold-fill').style.width=(g.phase==='calibrating'?g.calibration_progress:g.held/5)*100+'%';
  $('progress-label').textContent=g.phase==='calibrating'?'SETTING YOUR STARTING POSITION':'FIVE SECONDS TO A LITTLE WONDER';
  $('round-label').textContent={idle:'READY TO HATCH',calibrating:'HOLD STILL',active:'KEEP IT STEADY',result:g.result?.won?'WELCOME, LITTLE DRAGON':'ANOTHER EGG, ANOTHER TRY'}[g.phase];
  $('phase-label').textContent={idle:'THE CHALLENGE',calibrating:'GETTING READY',active:'YOUR FIVE-SECOND CHALLENGE',result:'ROUND COMPLETE'}[g.phase];
  if(g.phase==='idle'){$('phase-title').innerHTML='A tiny egg.<br><em>A steady hand.</em>';$('instruction').textContent='Rest the Movement module flat, then press Start. Hold still for calibration, then keep it steady for five seconds.';$('stage-badge').textContent=g.sensor_ready?'Move the module. Meet your egg.':'Connect Modulino Movement to begin.';}
  if(g.phase==='calibrating'){$('phase-title').textContent='Hold still for a moment.';$('instruction').textContent=g.reason;$('stage-badge').textContent='Calibrating · '+Math.round(g.calibration_progress*100)+'%';}
  if(g.phase==='active'){$('phase-title').textContent=g.steady?'Steady… almost there.':'A little less wobble.';$('instruction').textContent=g.reason;$('stage-badge').textContent=g.steady?(5-g.held).toFixed(1)+' seconds to a tiny dragon':'Gently settle the module';}
  if(g.phase==='result'){$('phase-title').textContent=g.result.won?'Your dragon has hatched!':'Let’s try another egg.';$('instruction').textContent=g.result.reason;$('stage-badge').textContent=g.result.won?'A little dragon says hello.':'Every dragon keeper starts somewhere.';$('score').textContent=g.result.won?g.result.score+' / 100':'Best '+g.result.best_hold.toFixed(1)+'s';$('result-detail').textContent=g.result.difficulty+' · '+g.result.resets+' restarts · '+g.result.seconds.toFixed(1)+'s';}
  if(!modePending)document.querySelectorAll('[data-difficulty]').forEach(b=>{const selected=b.dataset.difficulty===g.difficulty;b.classList.toggle('selected',selected);b.setAttribute('aria-pressed',String(selected));});
}
function renderAI(ai){
  $('ai-phase').textContent={warming:'WAKING UP',queued:'WAITING TO NARRATE',thinking:'IMAGINING',voicing:'FINDING ITS VOICE',ready:'ON YOUR BOARD',error:'NARRATOR UNAVAILABLE'}[ai.phase]||ai.phase;
  $('mission').textContent=ai.mission?.text||'Carry the dragon egg gently to its nest. Your AI narrator is waking up.';
  const reaction=ai.reaction&&ai.reaction.round_id===latest.game.round_id?ai.reaction:null;
  $('reaction').hidden=!reaction;$('reaction').textContent=reaction?.text||'';
  $('ai-note').textContent=ai.error||(reaction?.audio_error||ai.mission?.audio_error)||(ai.phase==='thinking'&&!ai.mission?'The first AI response loads the model. You can play while it wakes up.':'Motion responds immediately. AI imagines and speaks between rounds.');
  const item=audioItem();$('replay').disabled=!item?.audio_id;
  if(opened&&item?.audio_id&&handled!==item.audio_id&&!loading)loadAudio(item);
}
async function poll(){
  if(pending)return;pending=true;
  try{const response=await fetch('/api/status',{cache:'no-store',signal:AbortSignal.timeout(2500)});if(!response.ok)throw new Error();const state=await response.json();if(state.app_id!=='ai-balance-challenge')throw new Error();latest=state;connected=true;
    $('connection').textContent='● VENTUNO Q · connected';$('connection').classList.add('online');$('enter').disabled=false;
    for(const key of ['movement','knob','buzzer']){const name=key[0].toUpperCase()+key.slice(1);$(key+'-status').textContent=(state.hardware[key]?'● ':'○ ')+name+(state.hardware[key]?' connected':' unavailable');$(key+'-status').classList.toggle('connected',state.hardware[key]);}
    $('welcome-status').textContent=state.game.sensor_ready?'Your Movement module is ready. Let’s hatch a dragon.':state.hardware.movement?'Movement found; waiting for fresh sensor samples. Keep it connected and level.':'Waiting for Modulino Movement. Check its Qwiic connection to the MCU.';
    renderGame(state.game);
    if(firstStatus){firstStatus=false;handled=audioItem()?.audio_id||null;}
    renderAI(state.ai);
  }catch(_){connected=false;$('connection').textContent='Run AI Balance Challenge in App Lab';$('connection').classList.remove('online');$('enter').disabled=true;$('start').disabled=true;$('welcome-status').textContent='Waiting for the board…';}
  finally{pending=false;}
}
async function request(path,body){const response=await fetch(path,{method:'POST',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(4000)});const data=await response.json();if(!response.ok)throw new Error(data.detail||'The board could not finish that request.');return data;}
$('enter').addEventListener('click',async()=>{try{await unlock();}catch(_){}opened=true;$('welcome').hidden=true;$('app').inert=false;$('app').removeAttribute('aria-hidden');document.body.classList.remove('welcome-open');handled=null;if(latest)renderAI(latest.ai);$('start').focus({preventScroll:true});});
$('start').addEventListener('click',async()=>{if($('start').disabled)return;starting=true;$('start').disabled=true;stopAudio();message();try{await unlock();await request('/api/start');}catch(error){message(error.message);}finally{starting=false;await poll();}});
$('cancel').addEventListener('click',async()=>{message();try{await request('/api/cancel');stopAudio();}catch(error){message(error.message);}await poll();});
document.querySelectorAll('[data-difficulty]').forEach(button=>button.addEventListener('click',async()=>{modePending=true;message();try{await request('/api/difficulty',{difficulty:button.dataset.difficulty});}catch(error){message(error.message);}finally{modePending=false;await poll();}}));
$('replay').addEventListener('click',async()=>{const item=audioItem();if(!item?.audio_id)return;try{await unlock();if(bufferId===item.audio_id&&buffer)await play();else await loadAudio(item);}catch(_){message('Check the laptop audio output and try again.');}});
$('speech').addEventListener('change',()=>{if(!$('speech').checked)stopAudio();else unlock().catch(()=>{});});
$('fullscreen').addEventListener('click',async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch(_){message('Use your browser’s full-screen shortcut.');}});
document.addEventListener('fullscreenchange',()=>{$('fullscreen').textContent=document.fullscreenElement?'Exit full screen':'Full screen';});
window.addEventListener('beforeunload',stopAudio);
function animate(){drawX+=(targetX-drawX)*.2;drawY+=(targetY-drawY)*.2;$('egg-wrap').style.transform='translate('+drawX*2+'px,'+drawY*.6+'px) rotate('+drawX+'deg)';requestAnimationFrame(animate);}
animate();poll();setInterval(poll,100);
