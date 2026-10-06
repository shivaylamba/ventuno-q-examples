# Adapted from Arduino's Smart Mirror bundle (MPL-2.0).
# SPDX-License-Identifier: MPL-2.0
import base64
import io
import time
from threading import Lock

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

import prompt
from browser_audio import BrowserAudio
from presence import PersonDetector
from arduino.app_bricks.tts import TextToSpeech
from arduino.app_bricks.vlm import VisionLanguageModel
from arduino.app_bricks.web_ui import WebUI
from arduino.app_peripherals.camera import Camera
from arduino.app_utils import App, Logger
from arduino.app_utils.image import compressed_to_jpeg

logger = Logger("LaptopSmartMirror")
SYSTEM_PROMPT, USER_PROMPT_TEMPLATE = prompt.load_prompts()
MAX_JPEG_BYTES = 2 * 1024 * 1024
scan_lock = Lock()
inference_lock = Lock()
frame_lock = Lock()
current_frame: bytes | None = None

ui = WebUI()
detector = PersonDetector(confidence=0.55)
vlm = VisionLanguageModel(
    system_prompt=SYSTEM_PROMPT, temperature=0.4, max_tokens=160, timeout=180,
)
tts = TextToSpeech(speaker=BrowserAudio())
camera = Camera(fps=30, adjustments=compressed_to_jpeg())


def latest_frame():
    with frame_lock:
        frame = current_frame
    if frame is None:
        raise HTTPException(503, "The board webcam is not ready. Check its USB host connection.")
    return frame


def camera_frame():
    return Response(latest_frame(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


def stream_frames():
    while True:
        with frame_lock:
            frame = current_frame
        if frame is not None:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        time.sleep(0.1)


def camera_stream():
    return StreamingResponse(stream_frames(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


def camera_loop():
    global current_frame
    frame = camera.capture()
    if frame is not None:
        with frame_lock:
            current_frame = frame.tobytes()


def analyze(frame: bytes, automatic: bool = False) -> dict:
    with inference_lock:
        if automatic and not detector.people(frame)["person"]:
            raise HTTPException(422, "Step back into view. The mirror will scan when you are visible again.")
        return generate_tip(frame)


def generate_tip(frame: bytes) -> dict:
    started = time.monotonic()
    # No persistent memory: each person's scan is a separate request.
    tip = vlm.chat(
        message=prompt.build_user_prompt(USER_PROMPT_TEMPLATE), images=[frame],
    ).strip()
    if not tip:
        raise RuntimeError("The vision model returned an empty response.")
    tip = " ".join(tip.split())
    result = {"tip": tip, "audio": None, "audio_error": None}
    try:
        wav = tts.synthesize_wav(tip)
        result["audio"] = base64.b64encode(wav).decode("ascii")
    except Exception:
        logger.exception("Speech synthesis failed")
        result["audio_error"] = "Speech is unavailable. Your style tip is still shown below."
    result["elapsed_seconds"] = round(time.monotonic() - started, 1)
    # Log metrics only; do not log photographs or the user's outfit description.
    logger.info(f"Scan complete: {result['elapsed_seconds']} seconds, audio={bool(result['audio'])}")
    return result


async def read_frame(request: Request, max_bytes: int = MAX_JPEG_BYTES) -> bytes:
    if request.headers.get("content-type", "").split(";")[0] != "image/jpeg":
        raise HTTPException(415, "The camera must send a JPEG image.")
    frame = bytearray()
    async for chunk in request.stream():
        frame.extend(chunk)
        if len(frame) > max_bytes:
            raise HTTPException(413, "The captured image is too large. Try reconnecting the camera.")
    try:
        with Image.open(io.BytesIO(frame)) as image:
            if image.format != "JPEG" or image.width * image.height > 4000000:
                raise ValueError("Unsupported camera image")
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(400, "The camera image could not be read. Please try again.")
    return bytes(frame)


async def presence(request: Request):
    if scan_lock.locked() or not inference_lock.acquire(blocking=False):
        return {"busy": True}
    try:
        frame = latest_frame() if request.headers.get("x-mirror-camera") == "board" else await read_frame(request, 512 * 1024)
        try:
            return await run_in_threadpool(detector.people, frame)
        except Exception:
            logger.exception("Person detection failed")
            raise HTTPException(503, "Person detection is unavailable. You can still use Scan my outfit.")
    finally:
        inference_lock.release()


async def scan(request: Request):
    if not scan_lock.acquire(blocking=False):
        raise HTTPException(409, "The mirror is finishing another scan. Please wait a moment.")
    try:
        frame = await read_frame(request)
        try:
            return await run_in_threadpool(analyze, frame, request.headers.get("x-mirror-trigger") == "automatic")
        except HTTPException:
            raise
        except Exception:
            logger.exception("Outfit analysis failed")
            raise HTTPException(503, "Outfit analysis could not finish. Please try again.")
    finally:
        scan_lock.release()


def status():
    return {
        "ready": True, "busy": scan_lock.locked(), "app": "Smart Mirror • Laptop",
        "app_id": "smart-mirror-laptop",
        "vision_model": "Qwen 2.5-VL-7B", "speech_model": "Piper English",
        "presence_model": "YOLOX-Nano QNN", "presence_backend": "NPU / QNN HTP",
        "processing": "VENTUNO Q", "version": "1.2.0",
        "camera_source": "VENTUNO Q USB webcam", "camera_ready": current_frame is not None,
    }


ui.expose_api("GET", "/api/status", status)
ui.expose_api("POST", "/api/scan", scan)
ui.expose_api("POST", "/api/presence", presence)
ui.expose_api("GET", "/api/camera/frame", camera_frame)
ui.expose_api("GET", "/api/camera/stream", camera_stream)
with camera:
    App.run(user_loop=camera_loop)
