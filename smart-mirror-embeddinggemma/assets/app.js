// SPDX-FileCopyrightText: Copyright (C) ARDUINO SRL (http://www.arduino.cc)
// SPDX-License-Identifier: MPL-2.0
// Adapted for laptop display with the webcam on VENTUNO Q.
'use strict';
const $ = id => document.getElementById(id);
const video = $('camera');
const welcome = $('welcome-screen');
const appSurface = document.querySelector('.app');
let stream = null, cameraStarting = false, boardReady = false, boardBusy = false;
let scanning = false, audioContext = null, audioBuffer = null, audioSource = null;
let resultResetTimer = null;
let snapshotURL = null;
let presencePending = false, cameraGeneration = 0;
let presenceGate = new PresenceGate();
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

function message(text = '') { $('message').textContent = text; }
function showWelcome() {
  welcome.hidden = false; appSurface.inert = true; appSurface.setAttribute('aria-hidden','true');
  document.body.classList.add('welcome-open');
  $('welcome-hint').textContent = stream && $('automatic').checked
    ? 'Step into view. Your mirror will welcome you automatically.'
    : 'A little style inspiration, just for you.';
  $('welcome-start').focus({preventScroll:true});
}
function clearResultReset() {
  if (resultResetTimer !== null) { clearTimeout(resultResetTimer); resultResetTimer = null; }
}
function resetToWelcome() {
  clearResultReset(); stopAudio(); audioBuffer = null;
  presenceGate.rearm();
  $('result').hidden = true; $('idle').hidden = false; $('tip').textContent = '';
  $('recommendations-panel').hidden = true; $('recommendations').replaceChildren(); $('retrieval-note').textContent = '';
  $('timing').textContent = ''; $('audio-status').textContent = ''; message();
  showLive(); updateControls(); showWelcome();
}
function scheduleResultReset() {
  clearResultReset();
  resultResetTimer = setTimeout(resetToWelcome, 20000);
}
function enterMirror() {
  welcome.hidden = true; appSurface.inert = false; appSurface.removeAttribute('aria-hidden');
  document.body.classList.remove('welcome-open');
  appSurface.classList.remove('mirror-arrival');
  requestAnimationFrame(()=>appSurface.classList.add('mirror-arrival'));
  $('scan').focus({preventScroll:true});
}
function updateControls() {
  const live = !!stream && video.naturalWidth > 0;
  $('scan').disabled = !live || !boardReady || boardBusy || scanning || cameraStarting;
  $('camera-select').disabled = true;
  $('toggle-camera').disabled = !stream || scanning || cameraStarting;
  $('enable-camera').disabled = cameraStarting || scanning;
  $('replay').disabled = !audioBuffer || scanning;
  $('automatic').disabled = scanning;
  $('welcome-start').disabled = !boardReady || scanning || cameraStarting;
  $('show-welcome').disabled = scanning;
}
function stopAudio() {
  if (audioSource) {
    audioSource.onended = null;
    try { audioSource.stop(); } catch (_) {}
    audioSource = null; $('audio-status').textContent = 'Speech stopped';
  }
}
async function unlockAudio() {
  audioContext ??= new (window.AudioContext || window.webkitAudioContext)();
  if (audioContext.state === 'suspended') await audioContext.resume();
}
async function playTip() {
  if (!audioBuffer) return;
  await unlockAudio(); stopAudio();
  audioSource = audioContext.createBufferSource(); audioSource.buffer = audioBuffer;
  const source = audioSource;
  source.onended = () => {
    if (audioSource === source) {
      audioSource = null; $('audio-status').textContent = 'Speech played on laptop';
    }
  };
  audioSource.connect(audioContext.destination); audioSource.start();
  $('audio-status').textContent = 'Speaking on laptop…';
}
function showLive() {
  $('snapshot').hidden = true; video.hidden = false;
  $('preview-label').textContent = 'LIVE PREVIEW';
  if (snapshotURL) { URL.revokeObjectURL(snapshotURL); snapshotURL = null; }
}
function renderRecommendations(items = [], retrievalError = null, elapsed = null, catalogSource = 'Sample catalog', catalogCount = 0) {
  const panel = $('recommendations-panel');
  const grid = $('recommendations');
  grid.replaceChildren();
  panel.hidden = false;
  const liveAmazonCatalog = catalogSource.includes('Amazon Creators API');
  const livostyleCatalog = catalogSource.includes('Livostyle');
  $('retrieval-note').textContent = retrievalError
    ? `Dress matching is unavailable: ${retrievalError}`
    : `On-device vector search · ${elapsed ?? 0}s · ${catalogSource} (${catalogCount} items)` +
      (liveAmazonCatalog ? ' · current price and availability on Amazon'
        : livostyleCatalog ? ' · product photos and listings open at Livostyle; prices and stock may change'
          : ' · illustrative styles; Amazon search links');
  for (const item of items) {
    const card = document.createElement('article');
    card.className = `recommendation-card tone-${item.tone || 'ink'}`;
    const artwork = document.createElement('div'); artwork.className = 'recommendation-art';
    const icon = document.createElement('span'); icon.textContent = item.icon || '✦'; icon.setAttribute('aria-hidden','true'); artwork.append(icon);
    if (item.image_url) {
      const image = document.createElement('img'); image.src = item.image_url; image.alt = item.title; image.loading = 'lazy';
      image.referrerPolicy = 'no-referrer'; image.onerror = () => { image.remove(); };
      artwork.append(image);
    }
    const category = document.createElement('p'); category.className = 'recommendation-category'; category.textContent = item.category;
    const title = document.createElement('h3'); title.textContent = item.title;
    const link = document.createElement('a'); link.href = item.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = liveAmazonCatalog ? 'View Amazon listing ↗' : livostyleCatalog ? 'View product ↗' : 'Search Amazon ↗';
    card.append(artwork, category, title);
    if (Number.isFinite(Number(item.price_usd))) {
      const price = document.createElement('p'); price.className = 'recommendation-price';
      price.textContent = new Intl.NumberFormat('en-US', {style:'currency',currency:'USD'}).format(Number(item.price_usd));
      card.append(price);
    }
    card.append(link); grid.append(card);
  }
}
function stopCamera() {
  clearResultReset();
  cameraGeneration++; presenceGate = new PresenceGate();
  stream = null; video.removeAttribute('src');
  $('presence-status').textContent = 'Enable the camera preview to begin';
  showLive(); $('camera-placeholder').hidden = false; $('preview-label').hidden = true;
  updateControls();
}
async function startCamera() {
  if (cameraStarting) return;
  cameraStarting = true; cameraGeneration++; presenceGate = new PresenceGate(); message(); updateControls();
  try {
    if ($('speech').checked) { try { await unlockAudio(); } catch (_) {} }
    const response = await fetch('/api/status', {cache:'no-store',signal:AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error('Start Smart Mirror · EmbeddingGemma 2 in App Lab first.');
    const data = await response.json();
    if (!data.camera_ready) throw new Error('The board webcam is not ready. Check its USB host connection.');
    stream = true;
    video.src = '/api/camera/stream?preview=' + cameraGeneration;
    showLive(); $('camera-placeholder').hidden = true; $('preview-label').hidden = false;
    $('presence-status').textContent = $('automatic').checked ? 'Waiting for someone to step into view' : 'Automatic scan is off';
  } catch (error) { stopCamera(); message(error.message); }
  finally { cameraStarting = false; updateControls(); }
}
async function checkBoard() {
  try {
    const response = await fetch('/api/status', {cache:'no-store',signal:AbortSignal.timeout(4000)});
    if (!response.ok) throw new Error('Unavailable');
    const data = await response.json(); boardReady = data.ready; boardBusy = data.busy;
    $('connection').textContent = boardBusy ? 'VENTUNO Q · analyzing' : data.embedding_ready ? 'VENTUNO Q · connected' : 'VENTUNO Q · embedding model setup needed';
    $('connection').classList.add('online');
    $('welcome-connection').textContent = boardBusy ? 'Finding a little inspiration…' : data.embedding_ready ? 'Your mirror is ready' : 'Mirror tips ready · install EmbeddingGemma for matches';
  } catch (_) {
    boardReady = false; $('connection').textContent = 'Board disconnected · reconnect USB';
    $('connection').classList.remove('online');
    $('welcome-connection').textContent = 'Connect your mirror to begin';
  }
  updateControls();
}
async function capture(maxEdge = 960) {
  if (!stream || !video.naturalWidth) throw new Error('Your camera is not ready. Enable it and try again.');
  const canvas = document.createElement('canvas');
  const scale = Math.min(1, maxEdge / Math.max(video.naturalWidth,video.naturalHeight));
  canvas.width = Math.round(video.naturalWidth * scale); canvas.height = Math.round(video.naturalHeight * scale);
  canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);
  const image = await new Promise(resolve => canvas.toBlob(resolve,'image/jpeg',0.85));
  if (!image) throw new Error('The camera image could not be captured. Try again.');
  return image;
}
async function scan(automatic = false) {
  if ($('scan').disabled) return;
  clearResultReset();
  presenceGate.consume();
  scanning = true; audioBuffer = null; stopAudio(); $('audio-status').textContent = ''; message(); showLive(); updateControls();
  $('idle').hidden = true; $('result').hidden = true; $('recommendations-panel').hidden = true; $('analyzing').hidden = false;
  $('tip-card').setAttribute('aria-busy','true');
  $('scan').textContent = 'Getting ready…'; $('scan-status').textContent = 'Get into position. Look at the preview.';
  $('presence-status').textContent = automatic ? 'Welcome! Hold your pose…' : 'Preparing your scan…';
  let timer;
  try {
    if ($('speech').checked) { try { await unlockAudio(); } catch (_) {} }
    $('countdown').hidden = false;
    for (let n=3;n>0;n--) { $('countdown').textContent = n; await pause(1000); }
    $('countdown').hidden = true;
    const image = await capture();
    snapshotURL = URL.createObjectURL(image); $('snapshot').src = snapshotURL;
    $('snapshot').hidden = false; video.hidden = true;
    $('preview-label').textContent = 'YOUR SCAN';
    $('scan-overlay').hidden = false;
    $('scan').textContent = 'Analyzing…'; $('scan-status').textContent = 'Your mirror is finding a style tip…';
    const started = Date.now();
    timer = setInterval(() => {
      const seconds = Math.floor((Date.now()-started)/1000);
      $('scan-status').textContent = `Your mirror is finding a style tip… ${seconds}s`;
    },1000);
    const response = await fetch('/api/scan', {method:'POST',headers:{'Content-Type':'image/jpeg','X-Mirror-Trigger':automatic?'automatic':'manual'},body:image,signal:AbortSignal.timeout(240000)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'The scan could not finish. Please try again.');
    if (!data.tip) throw new Error('No style tip was returned. Please try again.');
    $('tip').textContent = data.tip; $('timing').textContent = `${data.elapsed_seconds}s · on your board`;
    renderRecommendations(data.recommendations, data.retrieval_error, data.retrieval_seconds, data.catalog_source, data.catalog_items);
    $('analyzing').hidden = true; $('result').hidden = false;
    if (data.audio) {
      try {
        await unlockAudio();
        const bytes = Uint8Array.from(atob(data.audio),char=>char.charCodeAt(0));
        audioBuffer = await audioContext.decodeAudioData(bytes.buffer);
        $('audio-status').textContent = 'Speech ready';
        if ($('speech').checked) await playTip();
      } catch (_) {
        message(audioBuffer ? 'Your tip is ready. Select Hear it again to play the audio.' : 'Your tip is ready, but the laptop could not decode the speech audio. Check your audio output and try another scan.');
      }
    }
    if (data.audio_error) message(data.audio_error);
    scheduleResultReset();
  } catch (error) {
    presenceGate.rearm();
    $('analyzing').hidden = true; $('idle').hidden = false;
    message(error.name === 'TimeoutError' ? 'This scan took too long. Wait for the board to finish, then try again.' : error.message === 'Failed to fetch' ? 'The board connection was interrupted. Reconnect USB and run the laptop launcher again.' : error.message);
    showLive();
  } finally {
    clearInterval(timer); $('countdown').hidden = true; $('scan-overlay').hidden = true; scanning = false;
    $('presence-status').textContent = $('automatic').checked ? 'Watching for the next automatic scan' : 'Automatic scan is off';
    showLive();
    $('tip-card').setAttribute('aria-busy','false'); $('scan').innerHTML = 'Scan my outfit <span aria-hidden="true">↗</span>';
    await checkBoard(); updateControls();
  }
}
async function checkPresence() {
  if (!stream || cameraStarting || scanning || audioSource || !boardReady || boardBusy || !$('automatic').checked || !video.naturalWidth || presencePending) return;
  presencePending = true;
  const generation = cameraGeneration;
  try {
    const response = await fetch('/api/presence', {method:'POST',headers:{'X-Mirror-Camera':'board'},signal:AbortSignal.timeout(16000)});
    if (generation !== cameraGeneration || scanning || !$('automatic').checked) return;
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Person detection is unavailable. You can still use Scan my outfit.');
    if (data.busy) { presenceGate.clearCandidate(); return; }
    const phase = presenceGate.update(data.person, Date.now());
    $('presence-status').textContent = {
      waiting:'Waiting for someone to step into view',
      holding:'Someone is in view · hold your pose',
      blocked:'Your next automatic scan will start when this tip clears',
      ready:'Welcome! Starting your scan…',
    }[phase];
    if (!welcome.hidden && phase === 'holding') $('welcome-hint').textContent = 'Welcome. Hold your pose for a moment.';
    if (phase === 'ready') { enterMirror(); await scan(true); }
  } catch (error) {
    if (generation !== cameraGeneration || scanning) return;
    presenceGate.clearCandidate();
    $('presence-status').textContent = 'Person detection paused · manual Scan is available';
  } finally { presencePending = false; }
}
$('enable-camera').addEventListener('click',()=>startCamera());
$('welcome-start').addEventListener('click',async()=>{
  if (scanning || cameraStarting) return;
  enterMirror();
  if (!stream) await startCamera();
});
$('show-welcome').addEventListener('click',resetToWelcome);
$('toggle-camera').addEventListener('click',()=>{stopCamera();message();});
$('scan').addEventListener('click',()=>scan(false));
$('replay').addEventListener('click',()=>playTip().catch(()=>message('Audio playback could not start. Check your laptop audio output.')));
$('speech').addEventListener('change',()=>{if(!$('speech').checked)stopAudio();else unlockAudio().catch(()=>{});});
$('automatic').addEventListener('change',()=>{
  cameraGeneration++; presenceGate.clearCandidate();
  $('idle').querySelector('.idle-copy').textContent = $('automatic').checked ? 'Stand in view and hold your pose. Your mirror will start automatically.' : 'Frame your outfit, then press Scan. You’ll have three seconds to get into position.';
  $('presence-status').textContent = $('automatic').checked ? 'Waiting for someone to step into view' : 'Automatic scan is off';
});
$('fullscreen').addEventListener('click',async()=>{
  try {if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch(_){message('Use your browser’s full-screen shortcut if full screen is unavailable.');}
});
document.addEventListener('fullscreenchange',()=>{$('fullscreen').textContent=document.fullscreenElement?'Exit full screen':'Full screen';});
document.addEventListener('keydown',event=>{if(event.key==='Enter'&&event.target===document.body){event.preventDefault();if(!welcome.hidden)$('welcome-start').click();else scan(false);}});
video.addEventListener('load',updateControls);
video.addEventListener('error',()=>{if(stream){stopCamera();message('Camera preview disconnected. Check the board, then enable camera again.');}});
window.addEventListener('beforeunload',()=>video.removeAttribute('src'));
checkBoard(); setInterval(checkBoard,5000);
setInterval(checkPresence,1000);
