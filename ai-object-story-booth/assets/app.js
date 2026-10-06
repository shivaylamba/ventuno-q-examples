// SPDX-License-Identifier: MPL-2.0
'use strict';
const $ = id => document.getElementById(id);
let opened=false, cameraLive=false, connected=false, latest=null, pending=false;
let currentJob=null, handledAudio=null, audioContext=null, audioBuffer=null, audioSource=null;
let audioLoading=false, modePending=false, statusStarted=0;
let firstStatus=true, previousFinishedJob=null;
document.body.classList.add('welcome-open');

// A new page starts fresh rather than replaying the board's last finished visit.
// An in-progress story can still be resumed after a refresh.
function visibleJob(){return latest?.job?.id===previousFinishedJob?null:latest?.job;}

function message(text=''){$('message').textContent=text;}
async function unlockAudio(){audioContext??=new(window.AudioContext||window.webkitAudioContext)();if(audioContext.state==='suspended')await audioContext.resume();}
function stopAudio(){if(audioSource){audioSource.onended=null;try{audioSource.stop();}catch(_){}audioSource=null;}}
async function playStory(){if(!audioBuffer)return;await unlockAudio();stopAudio();const source=audioContext.createBufferSource();source.buffer=audioBuffer;source.connect(audioContext.destination);audioSource=source;source.onended=()=>{if(audioSource===source){audioSource=null;$('audio-status').textContent='Story played on laptop';}};source.start();$('audio-status').textContent='Telling your story…';}
function enter(){opened=true;$('welcome').hidden=true;$('app').inert=false;$('app').removeAttribute('aria-hidden');document.body.classList.remove('welcome-open');$('app').classList.add('arrival');$('capture').focus({preventScroll:true});}
function startPreview(){if(!opened||cameraLive||!latest?.camera_ready)return;cameraLive=true;$('camera').src='/api/camera/stream?preview='+Date.now();$('preview-retry').hidden=true;}
function renderMode(mode){document.querySelectorAll('.mode').forEach(button=>{const selected=button.dataset.mode===mode;button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));});}
function renderJob(job){
  if(!job){
    if(currentJob){currentJob=null;handledAudio=null;audioBuffer=null;stopAudio();message();$('audio-status').textContent='';$('photo').removeAttribute('src');}
    $('story-card').setAttribute('aria-busy','false');$('story-idle').hidden=false;$('story-progress').hidden=true;$('story-result').hidden=true;
    $('countdown').hidden=true;$('photo').hidden=true;$('camera').hidden=false;$('preview-label').textContent='LIVE PREVIEW';
    $('story-label').textContent='THE ADVENTURE AWAITS';$('visit-status').textContent='Or press the knob. You’ll have three seconds to get ready.';
    return;
  }
  if(currentJob!==job.id){currentJob=job.id;handledAudio=null;audioBuffer=null;stopAudio();statusStarted=Date.now();message();$('audio-status').textContent='';$('replay').disabled=true;$('photo').removeAttribute('src');}
  const working=['countdown','thinking','voicing'].includes(job.phase);
  $('story-card').setAttribute('aria-busy',String(working));
  $('story-idle').hidden=true;$('story-progress').hidden=!working;$('story-result').hidden=job.phase!=='ready';
  $('story-label').textContent=job.mode_name.toUpperCase()+(job.phase==='ready'?' / YOUR OBJECT’S STORY':' / A STORY IN THE MAKING');
  $('countdown').hidden=job.phase!=='countdown';$('countdown').textContent=job.countdown||'';
  if(job.phase==='countdown'){$('progress-title').textContent='Hold your object steady.';$('progress-copy').textContent='A little adventure starts in '+job.countdown+'…';$('photo').hidden=true;$('camera').hidden=false;$('preview-label').textContent='LIVE PREVIEW';}
  if(['thinking','voicing'].includes(job.phase)){const source='/api/story/'+job.id+'/photo';if($('photo').getAttribute('src')!==source){$('photo').src=source;$('capture-flash').hidden=false;setTimeout(()=>$('capture-flash').hidden=true,550);}$('photo').hidden=false;$('camera').hidden=true;$('preview-label').textContent='THE HERO OF YOUR STORY';}
  if(job.phase==='ready'){$('photo').hidden=true;$('photo').removeAttribute('src');$('camera').hidden=false;$('preview-label').textContent='LIVE PREVIEW';}
  if(job.phase==='thinking'){$('progress-title').textContent='Finding a little wonder…';$('progress-copy').textContent='Your storyteller is imagining an adventure. '+Math.floor((Date.now()-statusStarted)/1000)+'s';}
  if(job.phase==='voicing'){$('progress-title').textContent='Giving your story a voice…';$('progress-copy').textContent='Almost ready.';$('story').textContent=job.story;}
  if(job.phase==='ready'){$('story').textContent=job.story;$('timing').textContent=job.elapsed_seconds+'s · on your board';if(job.audio_error)message(job.audio_error);if(job.audio_ready&&handledAudio!==job.id&&!audioLoading&&opened)loadAudio(job.id);}
  if(job.phase==='error'){$('story-idle').hidden=false;$('story-label').textContent='LET’S TRY THAT AGAIN';message(job.error);$('photo').hidden=true;$('camera').hidden=false;$('preview-label').textContent='LIVE PREVIEW';}
  $('visit-status').textContent=working?'One story at a time. Turn the knob to choose the next storyteller.':'Show another object, then press the knob for a new story.';
}
async function loadAudio(id){
  audioLoading=true;
  try{await unlockAudio();const response=await fetch('/api/story/'+id+'/audio',{cache:'no-store',signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error('Speech is unavailable.');const decoded=await audioContext.decodeAudioData(await response.arrayBuffer());if(currentJob!==id)return;audioBuffer=decoded;handledAudio=id;$('replay').disabled=false;$('audio-status').textContent='Story ready to play';if($('speech').checked)await playStory();}
  catch(_){if(currentJob===id){handledAudio=id;message('Your story is ready. Select Hear it again to enable laptop speech.');$('replay').disabled=false;}}
  finally{audioLoading=false;}
}
function updateControls(){$('capture').disabled=!connected||!latest?.camera_ready||latest.busy;$('enter').disabled=!connected;$('replay').disabled=!audioBuffer&&!visibleJob()?.audio_ready;}
async function poll(){
  if(pending)return;pending=true;
  try{const response=await fetch('/api/status',{cache:'no-store',signal:AbortSignal.timeout(4000)});if(!response.ok)throw new Error();const state=await response.json();if(state.app_id!=='ai-object-story-booth')throw new Error();latest=state;connected=true;$('connection').textContent='● VENTUNO Q · connected';$('connection').classList.add('online');
    for(const name of ['knob','buzzer']){$(name+'-status').textContent=(state.hardware[name]?'● ':'○ ')+(name==='knob'?'Knob':'Buzzer')+(state.hardware[name]?' connected':' not detected');$(name+'-status').classList.toggle('connected',state.hardware[name]);}
    $('welcome-status').textContent=state.camera_ready?(state.hardware.knob?'Your camera and controller are ready.':'Camera ready. Checking the Knob connection…'):'Waiting for the board webcam…';
    if(firstStatus){firstStatus=false;if(state.job&&!['countdown','thinking','voicing'].includes(state.job.phase))previousFinishedJob=state.job.id;}
    if(!modePending)renderMode(state.mode);startPreview();renderJob(visibleJob());
  }catch(_){connected=false;$('connection').textContent='Board disconnected · run the booth in App Lab';$('connection').classList.remove('online');$('welcome-status').textContent='Run AI Object Story Booth in App Lab to begin.';}
  finally{pending=false;updateControls();}
}
async function capture(){if($('capture').disabled)return;stopAudio();message();try{await unlockAudio();const response=await fetch('/api/story',{method:'POST',signal:AbortSignal.timeout(6000)});const data=await response.json();if(!response.ok)throw new Error(data.detail||'The story could not start.');renderJob(data);latest.busy=true;updateControls();}catch(error){message(error.message);}await poll();}
$('enter').addEventListener('click',async()=>{try{await unlockAudio();}catch(_){}enter();startPreview();renderJob(visibleJob());});
$('capture').addEventListener('click',capture);
document.querySelectorAll('.mode').forEach(button=>button.addEventListener('click',async()=>{modePending=true;message();try{const response=await fetch('/api/mode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:button.dataset.mode}),signal:AbortSignal.timeout(4000)});if(!response.ok)throw new Error('The storyteller could not be changed.');renderMode(button.dataset.mode);}catch(error){message(error.message);}finally{modePending=false;await poll();}}));
$('replay').addEventListener('click',async()=>{try{await unlockAudio();const job=visibleJob();if(!audioBuffer&&job?.audio_ready){handledAudio=null;await loadAudio(job.id);}else await playStory();}catch(_){message('Check your laptop’s audio output, then try again.');}});
$('speech').addEventListener('change',()=>{if(!$('speech').checked)stopAudio();else unlockAudio().catch(()=>{});});
$('preview-retry').addEventListener('click',()=>{cameraLive=false;startPreview();});
$('camera').addEventListener('load',()=>{$('camera-empty').hidden=true;});
$('camera').addEventListener('error',()=>{cameraLive=false;$('preview-retry').hidden=false;if(opened)message('Camera preview interrupted. Reconnect the board, then select Reconnect preview.');});
$('fullscreen').addEventListener('click',async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch(_){message('Use your browser’s full-screen shortcut.');}});
document.addEventListener('fullscreenchange',()=>{$('fullscreen').textContent=document.fullscreenElement?'Exit full screen':'Full screen';});
window.addEventListener('beforeunload',()=>{$('camera').removeAttribute('src');stopAudio();});
poll();setInterval(poll,500);
