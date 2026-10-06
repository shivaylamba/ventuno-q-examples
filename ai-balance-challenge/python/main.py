# SPDX-License-Identifier: MPL-2.0
import math
import time
import uuid
from queue import Queue, Empty, Full
from threading import Lock, Thread

from fastapi import HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from arduino.app_utils import App, Bridge, Logger
from arduino.app_bricks.web_ui import WebUI
from arduino.app_bricks.vlm import VisionLanguageModel
from arduino.app_bricks.tts import TextToSpeech
from browser_audio import BrowserAudio
from balance import BalanceGame, DIFFICULTIES, knob_delta
from egg_art import EGG_ART

logger=Logger("BalanceChallenge")
ui=WebUI()
vlm=VisionLanguageModel(system_prompt="""You are the warm, witty narrator of a fictional dragon egg balancing game.
Write plain English spoken flavor text only, one short sentence, at most 24 words.
Use only supplied round facts. Do not invent scores or claim to see the player.
The actual game controls movement instructions; you describe its fictional adventure.
Never give physical movement advice. Never suggest shaking, tilting, dropping, or moving the module.
For a failed round, acknowledge its actual result and offer encouragement to try again.
No headings, markdown or stage directions.""",temperature=.75,max_tokens=90,timeout=180)
tts=TextToSpeech(speaker=BrowserAudio())
game=BalanceGame()
state_lock=Lock();bridge_lock=Lock()
hardware={"bridge":False,"movement":False,"sensor_ready":False,"knob":False,"buzzer":False,"sequence":0,"age_ms":None}
ai={"phase":"warming","mission":None,"reaction":None,"error":None}
audio={}
tasks=Queue(maxsize=1)
threads_started=False

def enqueue_reaction(result):
    with state_lock:
        ai["phase"]="queued";ai["reaction"]=None;ai["error"]=None
    try:tasks.put_nowait(("reaction",result))
    except Full:
        try:tasks.get_nowait()
        except Empty:pass
        tasks.put_nowait(("reaction",result))

def narrate():
    while True:
        kind,result=tasks.get()
        with state_lock:ai["phase"]="thinking";ai["error"]=None
        started=time.monotonic()
        try:
            if kind=="mission":
                prompt="Introduce a tiny fantasy mission about carrying a dragon egg safely to its nest. The game asks for a steady five-second hold. Give one whimsical sentence under 24 words."
            else:
                prompt=("Give one playful, encouraging dragon-egg reaction under 24 words to these measured facts: "
                        f"won={result['won']}; difficulty={result['difficulty']}; best steady hold={result['best_hold']} seconds; "
                        f"restarts={result['resets']}; score={result['score']}; result={result['reason']}. "
                        "If the round failed due to a connection or calibration problem, acknowledge that rather than blaming the player's movement. "
                        "Give encouragement only; do not give physical movement instructions or suggest shaking.")
            text=" ".join(vlm.chat(message="The image is our game's illustrated egg. "+prompt,images=[EGG_ART]).split())
            if not text:raise RuntimeError("The model returned no narration")
            # Bound speech length even when the model exceeds the requested length.
            if len(text.split())>40:text=" ".join(text.split()[:40]).rstrip(",;:")+"."
            with state_lock:ai["phase"]="voicing"
            speech=None;speech_error=None
            try:speech=tts.synthesize_wav(text)
            except Exception:
                logger.exception("Speech synthesis failed")
                speech_error="The AI text is ready, but speech could not be created."
            with state_lock:
                if kind=="reaction" and (game.round_id!=result["id"] or game.phase!="result"):
                    ai["phase"]="ready";continue
                audio_id=uuid.uuid4().hex if speech else None
                if audio_id:audio[audio_id]=speech
                item={"text":text,"audio_id":audio_id,"seconds":round(time.monotonic()-started,1),"audio_error":speech_error}
                if kind=="reaction":item["round_id"]=result["id"]
                ai["mission" if kind=="mission" else "reaction"]=item
                ai["phase"]="ready"
                keep={v["audio_id"] for k in ("mission","reaction") if (v:=ai.get(k)) and v.get("audio_id")}
                for key in list(audio):
                    if key not in keep:audio.pop(key,None)
            logger.info(f"AI {kind} ready in {time.monotonic()-started:.1f}s; audio={speech is not None}")
        except Exception:
            logger.exception("Local AI narration failed")
            with state_lock:
                ai["phase"]="error";ai["error"]="Local AI narration is unavailable. The motion game still works; finish another round to retry."

def start_round():
    with state_lock:
        try:game.start(time.monotonic())
        except ValueError as error:raise HTTPException(503,str(error))
        except RuntimeError as error:raise HTTPException(409,str(error))
        old=ai["reaction"]
        if old and old.get("audio_id"):audio.pop(old["audio_id"],None)
        ai["reaction"]=None;ai["error"]=None
        result=game.snapshot(time.monotonic())
    return result

def controller_loop():
    previous_position=previous_presses=None
    last_error=None;scheduled=[]
    while True:
        loop_started=time.monotonic()
        try:
            with bridge_lock:values=Bridge.call("balance_status",timeout=1)
            if not isinstance(values,list) or len(values)!=13:raise ValueError("Unexpected Movement controller packet")
            sequence,age,*rest=map(float,values)
            accel=rest[:3];gyro=rest[3:6]
            position,presses,knob_ok,buzzer_ok,movement_ok=map(int,rest[6:])
            if last_error is not None:logger.info("Movement controller connected");last_error=None
            now=time.monotonic()
            with state_lock:
                game.tick(int(sequence),age,accel,gyro,bool(movement_ok and sequence>0),now)
                hardware.update(bridge=True,movement=bool(movement_ok),sensor_ready=game.sensor_ready,
                                knob=bool(knob_ok),buzzer=bool(buzzer_ok),sequence=int(sequence),age_ms=round(age))
                if knob_ok and previous_position is not None:
                    game.difficulty_index=(game.difficulty_index+knob_delta(position,previous_position))%len(DIFFICULTIES)
                completion=game.completion;game.completion=None
                events=game.events[:];game.events.clear()
            if knob_ok and previous_presses is not None and presses>previous_presses:
                try:start_round()
                except HTTPException:pass
            previous_position=position if knob_ok else None;previous_presses=presses if knob_ok else None
            if completion:
                enqueue_reaction(completion)
                if completion["won"]:scheduled.extend([(now+.2,1319,100),(now+.4,1568,180)])
            scheduled.extend((now,f,d) for f,d in events)
            due=[(f,d) for t,f,d in scheduled if t<=now]
            scheduled=[item for item in scheduled if item[0]>now]
            if buzzer_ok:
                for frequency,duration in due:
                    with bridge_lock:Bridge.call("balance_tone",frequency,duration,timeout=1)
        except Exception as error:
            if str(error)!=last_error:logger.warning(f"Movement controller unavailable: {error}");last_error=str(error)
            with state_lock:
                game.tick(0,1000,(0,0,0),(0,0,0),False,time.monotonic())
                hardware.update(bridge=False,movement=False,sensor_ready=False,knob=False,buzzer=False)
                completion=game.completion;game.completion=None
            if completion:enqueue_reaction(completion)
            previous_position=previous_presses=None;scheduled=[]
        time.sleep(max(.01,.04-(time.monotonic()-loop_started)))

def status():
    with state_lock:
        return {"app":"AI Balance Challenge","app_id":"ai-balance-challenge","version":"1.0.0",
                "hardware":dict(hardware),"game":game.snapshot(time.monotonic()),
                "ai":{"phase":ai["phase"],"mission":dict(ai["mission"]) if ai["mission"] else None,
                      "reaction":dict(ai["reaction"]) if ai["reaction"] else None,"error":ai["error"]}}

class DifficultyRequest(BaseModel):difficulty:str
def set_difficulty(request:DifficultyRequest):
    identifiers=[d["id"] for d in DIFFICULTIES]
    if request.difficulty not in identifiers:raise HTTPException(400,"Choose Easy, Normal or Hard.")
    with state_lock:game.difficulty_index=identifiers.index(request.difficulty)
    return {"difficulty":request.difficulty}

def cancel_round():
    with state_lock:game.cancel();ai["reaction"]=None
    return {"phase":"idle"}

def get_audio(audio_id:str):
    with state_lock:data=audio.get(audio_id)
    if data is None:raise HTTPException(404,"This narration is no longer available.")
    return Response(data,media_type="audio/wav",headers={"Cache-Control":"no-store"})

def on_tick():
    global threads_started
    if not threads_started:
        threads_started=True;tasks.put(("mission",None))
        Thread(target=controller_loop,daemon=True,name="movement-controller").start()
        Thread(target=narrate,daemon=True,name="local-ai-narrator").start()
    time.sleep(.01)

ui.expose_api("GET","/api/status",status)
ui.expose_api("POST","/api/start",start_round)
ui.expose_api("POST","/api/cancel",cancel_round)
ui.expose_api("POST","/api/difficulty",set_difficulty)
ui.expose_api("GET","/api/audio/{audio_id}",get_audio)
App.run(user_loop=on_tick)
