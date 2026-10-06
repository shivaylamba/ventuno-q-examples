# SPDX-License-Identifier: MPL-2.0
import time
import uuid
from threading import Lock, Thread

from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from arduino.app_utils import App, Bridge, Logger
from arduino.app_utils.image import compressed_to_jpeg
from arduino.app_peripherals.camera import Camera
from arduino.app_bricks.web_ui import WebUI
from arduino.app_bricks.vlm import VisionLanguageModel
from arduino.app_bricks.tts import TextToSpeech
from browser_audio import BrowserAudio
from story import MODES, SYSTEM_PROMPT, build_prompt, knob_delta

logger = Logger("ObjectStoryBooth")
ui = WebUI()
vlm = VisionLanguageModel(system_prompt=SYSTEM_PROMPT, temperature=0.65, max_tokens=160, timeout=180)
tts = TextToSpeech(speaker=BrowserAudio())
camera = Camera(fps=30, adjustments=compressed_to_jpeg())
state_lock, frame_lock, bridge_lock = Lock(), Lock(), Lock()
current_frame = None
frame_time = 0.0
mode_index = 0
hardware = {"bridge": False, "knob": False, "buzzer": False, "position": 0, "presses": 0,
            "knob_address": None, "buzzer_address": None}
job = None
job_frame = None
job_audio = None


def camera_loop():
    global current_frame, frame_time
    frame = camera.capture()
    if frame is not None:
        with frame_lock:
            current_frame = frame.tobytes()
            frame_time = time.monotonic()


def latest_frame():
    with frame_lock:
        frame, age = current_frame, time.monotonic() - frame_time
    if frame is None or age > 5:
        raise HTTPException(503, "The board webcam is not ready. Check its USB host connection.")
    return frame


def camera_stream():
    def frames():
        while True:
            with frame_lock:
                frame = current_frame
            if frame is not None:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(0.1)
    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


def tone(frequency, duration=80):
    try:
        with bridge_lock:
            return bool(Bridge.call("booth_tone", frequency, duration))
    except Exception:
        return False  # Story generation still works if the buzzer is disconnected.


def update_job(**fields):
    with state_lock:
        job.update(fields)


def run_story(selected_mode):
    global job_frame, job_audio
    started = time.monotonic()
    try:
        for number in (3, 2, 1):
            update_job(phase="countdown", countdown=number)
            tone(660, 65)
            time.sleep(1)
        frame = latest_frame()
        with state_lock:
            job_frame = frame
        update_job(phase="thinking", countdown=0)
        tone(1047, 100)
        inference_started = time.monotonic()
        text = " ".join(vlm.chat(message=build_prompt(selected_mode), images=[frame]).split())
        if not text:
            raise RuntimeError("The vision model returned an empty story")
        vision_seconds = round(time.monotonic() - inference_started, 1)
        update_job(phase="voicing", story=text, vision_seconds=vision_seconds)
        audio_error = None
        try:
            audio = tts.synthesize_wav(text)
            with state_lock:
                job_audio = audio
        except Exception:
            logger.exception("Speech synthesis failed")
            audio_error = "Your story is ready. Speech could not be created; try another story."
        update_job(phase="ready", elapsed_seconds=round(time.monotonic() - started - 3, 1),
                   audio_ready=job_audio is not None, audio_error=audio_error)
        tone(784, 90)
        time.sleep(0.13)
        tone(1047, 140)
        logger.info(f"Story complete: {vision_seconds}s vision, audio={job_audio is not None}")
    except Exception:
        logger.exception("Story generation failed")
        update_job(phase="error", countdown=0, error="The story could not finish. Check App Lab's logs, then press to try again.")
        tone(220, 160)


def start_story(trigger="screen"):
    global job, job_frame, job_audio
    latest_frame()  # Refuse to start with an unavailable or stale camera.
    with state_lock:
        if job and job["phase"] in ("countdown", "thinking", "voicing"):
            raise HTTPException(409, "The booth is finishing a story. Please wait.")
        selected = MODES[mode_index]
        job_frame = job_audio = None
        job = {"id": uuid.uuid4().hex, "phase": "countdown", "countdown": 3,
               "mode": selected["id"], "mode_name": selected["name"], "trigger": trigger,
               "story": "", "audio_ready": False, "error": None, "audio_error": None}
        result = dict(job)
    Thread(target=run_story, args=(selected["id"],), daemon=True, name="story-generation").start()
    return result


def controller_loop():
    global mode_index
    previous_position = previous_presses = None
    reported_error = None
    while True:
        try:
            with bridge_lock:
                values = Bridge.call("booth_status")
            if not isinstance(values, list) or len(values) != 6:
                raise ValueError("Unexpected MCU controller response")
            position, presses, knob_ok, buzzer_ok, knob_address, buzzer_address = map(int, values)
            if reported_error is not None:
                logger.info("Modulino bridge connected")
                reported_error = None
            with state_lock:
                hardware.update(bridge=True, knob=bool(knob_ok), buzzer=bool(buzzer_ok),
                                position=position, presses=presses,
                                knob_address=hex(knob_address) if knob_ok else None,
                                buzzer_address=hex(buzzer_address) if buzzer_ok else None)
                if knob_ok and previous_position is not None:
                    mode_index = (mode_index + knob_delta(position, previous_position)) % len(MODES)
            if knob_ok and previous_presses is not None and presses > previous_presses:
                try:
                    start_story("knob")
                except HTTPException:
                    pass  # Repeated presses while busy are consumed, never queued.
            previous_position = position if knob_ok else None
            previous_presses = presses if knob_ok else None
        except Exception as error:
            description = str(error)
            if reported_error != description:
                logger.warning(f"Modulino controller unavailable: {description}")
                reported_error = description
            with state_lock:
                hardware.update(bridge=False, knob=False, buzzer=False)
            previous_position = previous_presses = None
        time.sleep(0.15)


def status():
    with state_lock:
        data = {"ready": True, "app": "AI Object Story Booth", "app_id": "ai-object-story-booth", "version": "1.0.0",
                "hardware": dict(hardware), "mode": MODES[mode_index]["id"], "modes": MODES,
                "job": dict(job) if job else None}
    with frame_lock:
        data["camera_ready"] = current_frame is not None and time.monotonic() - frame_time < 5
    data["busy"] = bool(data["job"] and data["job"]["phase"] in ("countdown", "thinking", "voicing"))
    return data


class ModeRequest(BaseModel):
    mode: str


def select_mode(request: ModeRequest):
    global mode_index
    identifiers = [item["id"] for item in MODES]
    if request.mode not in identifiers:
        raise HTTPException(400, "Choose Detective, Alien Scientist or Fairy Tale.")
    with state_lock:
        mode_index = identifiers.index(request.mode)
    return {"mode": request.mode}


def audio_response(story_id: str):
    with state_lock:
        if not job or job["id"] != story_id or job_audio is None:
            raise HTTPException(404, "Speech is not available for this story.")
        audio = job_audio
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})


def photo_response(story_id: str):
    with state_lock:
        if not job or job["id"] != story_id or job_frame is None:
            raise HTTPException(404, "This capture is no longer available.")
        frame = job_frame
    return Response(frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


ui.expose_api("GET", "/api/status", status)
ui.expose_api("GET", "/api/camera/stream", camera_stream)
ui.expose_api("GET", "/api/camera/frame", lambda: Response(latest_frame(), media_type="image/jpeg", headers={"Cache-Control":"no-store"}))
ui.expose_api("POST", "/api/mode", select_mode)
ui.expose_api("POST", "/api/story", start_story)
ui.expose_api("GET", "/api/story/{story_id}/audio", audio_response)
ui.expose_api("GET", "/api/story/{story_id}/photo", photo_response)
with camera:
    Thread(target=controller_loop, daemon=True, name="modulino-controller").start()
    App.run(user_loop=camera_loop)
