# Adapted from Arduino's Smart Mirror bundle (MPL-2.0).
# SPDX-License-Identifier: MPL-2.0
import base64
import hashlib
import io
import json
import math
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from urllib.parse import quote_plus

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

try:
    from litert_lm import Backend, Content, EmbeddingEngine
except ImportError:
    Backend = Content = EmbeddingEngine = None

logger = Logger("EmbeddingGemmaSmartMirror")
SYSTEM_PROMPT, USER_PROMPT_TEMPLATE = prompt.load_prompts()
MAX_JPEG_BYTES = 2 * 1024 * 1024
scan_lock = Lock()
inference_lock = Lock()
frame_lock = Lock()
current_frame: bytes | None = None
APP_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = Path(os.environ.get(
    "EMBEDDINGGEMMA_MODEL_PATH",
    str(APP_ROOT / "data" / "models" / "embeddinggemma-2-740m.litertlm"),
))
SAMPLE_CATALOG_PATH = Path(__file__).with_name("catalog.json")
AMAZON_CATALOG_PATH = APP_ROOT / "data" / "amazon-catalog.json"
VECTOR_CACHE_PATH = APP_ROOT / "data" / "embedding-vectors.json"
AMAZON_SEARCH_BASE = os.environ.get("AMAZON_SEARCH_BASE", "https://www.amazon.com/s?k=")
sample_catalog = json.loads(SAMPLE_CATALOG_PATH.read_text(encoding="utf-8"))


def load_catalog():
    global amazon_catalog_stale
    amazon_catalog_stale = False
    try:
        saved = json.loads(AMAZON_CATALOG_PATH.read_text(encoding="utf-8"))
        expiry = datetime.fromisoformat(saved["expires_at"])
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry > datetime.now(timezone.utc) and len(saved.get("products", [])) >= 100:
            return saved["products"], "Amazon Creators API", saved["expires_at"]
        amazon_catalog_stale = True
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return sample_catalog, "Sample catalog" + (" · refresh Amazon data" if amazon_catalog_stale else ""), None


catalog, catalog_source, catalog_expires_at = load_catalog()
embedding_engine = None
embedding_backend = None
embedding_lock = Lock()
product_vectors: list[list[float]] | None = None
embedding_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="embeddinggemma")

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
    # Begin retrieval as soon as Qwen returns. It runs alongside speech synthesis.
    recommendation_started = time.monotonic()
    recommendation_job = embedding_executor.submit(recommend, frame, tip)
    try:
        wav = tts.synthesize_wav(tip)
        result["audio"] = base64.b64encode(wav).decode("ascii")
    except Exception:
        logger.exception("Speech synthesis failed")
        result["audio_error"] = "Speech is unavailable. Your style tip is still shown below."
    try:
        result["recommendations"] = recommendation_job.result()
        result["retrieval_error"] = None
    except Exception as exc:
        logger.exception("EmbeddingGemma retrieval failed")
        result["recommendations"] = []
        result["retrieval_error"] = str(exc)
    result["retrieval_seconds"] = round(time.monotonic() - recommendation_started, 2)
    result["catalog_source"] = catalog_source
    result["catalog_items"] = len(catalog)
    result["elapsed_seconds"] = round(time.monotonic() - started, 1)
    # Log metrics only; do not log photographs or the user's outfit description.
    logger.info(f"Scan complete: {result['elapsed_seconds']} seconds, audio={bool(result['audio'])}")
    return result


def get_embedding_engine():
    global embedding_engine, embedding_backend
    if not MODEL_PATH.is_file():
        raise RuntimeError("EmbeddingGemma weights are missing. Install the generic LiteRT-LM model using this app's README instructions.")
    if EmbeddingEngine is None:
        raise RuntimeError("LiteRT-LM is not installed. App Lab must install python/requirements.txt, then restart this app.")
    if embedding_engine is not None:
        return embedding_engine
    with embedding_lock:
        if embedding_engine is not None:
            return embedding_engine
        requested_backend = os.environ.get("EMBEDDING_BACKEND", "CPU").strip().upper()
        if requested_backend == "NPU":
            dispatch_dir = os.environ.get("LITERT_DISPATCH_LIB_DIR", "").strip()
            if not dispatch_dir:
                raise RuntimeError("LiteRT-LM needs LITERT_DISPATCH_LIB_DIR for its NPU backend on Linux; use the generic CPU/GPU model otherwise.")
            backend = vision_backend = Backend.NPU(litert_dispatch_lib_dir=dispatch_dir)
        elif requested_backend == "GPU":
            backend = vision_backend = Backend.GPU()
        else:
            requested_backend = "CPU"
            backend = vision_backend = Backend.CPU()
        try:
            engine = EmbeddingEngine(str(MODEL_PATH), backend=backend, vision_backend=vision_backend)
            engine.compute_embedding("task: search query | text: outfit styling")
            embedding_engine, embedding_backend = engine, requested_backend + " / LiteRT-LM"
        except Exception as exc:
            raise RuntimeError(f"EmbeddingGemma could not initialize on {requested_backend}: {exc}") from exc
    return embedding_engine


def normalize(vector) -> list[float]:
    values = [float(value) for value in vector]
    norm = math.sqrt(sum(value * value for value in values))
    if not norm:
        raise RuntimeError("EmbeddingGemma returned an empty vector.")
    return [value / norm for value in values]


def ensure_product_vectors(engine) -> list[list[float]]:
    global product_vectors
    if product_vectors is not None:
        return product_vectors
    with embedding_lock:
        if product_vectors is not None:
            return product_vectors
        content_key = json.dumps(catalog, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(
            f"{MODEL_PATH.stat().st_size}:{MODEL_PATH.stat().st_mtime_ns}:{catalog_expires_at}:{content_key}".encode()
        ).hexdigest()
        try:
            cached = json.loads(VECTOR_CACHE_PATH.read_text(encoding="utf-8"))
            if (cached.get("fingerprint") == fingerprint and
                    cached.get("expires_at") == catalog_expires_at and
                    len(cached.get("vectors", [])) == len(catalog)):
                product_vectors = cached["vectors"]
                return product_vectors
        except (OSError, ValueError, TypeError):
            pass
        vectors = []
        for item in catalog:
            text = f"task: search result | text: {item['title']}. {item['description']}"
            vectors.append(normalize(engine.compute_embedding(text).embedding))
        VECTOR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path = VECTOR_CACHE_PATH.with_suffix(".tmp")
        temp_path.write_text(json.dumps({
            "fingerprint": fingerprint, "expires_at": catalog_expires_at, "vectors": vectors,
        }), encoding="utf-8")
        temp_path.replace(VECTOR_CACHE_PATH)
        product_vectors = vectors
    return product_vectors


def recommend(frame: bytes, tip: str) -> list[dict]:
    engine = get_embedding_engine()
    indexed_vectors = ensure_product_vectors(engine)
    # Keep the camera frame temporary: it is never written to the app's data folder.
    with tempfile.NamedTemporaryFile(prefix="mirror-frame-", suffix=".jpg", delete=False) as image_file:
        image_file.write(frame)
        image_path = image_file.name
    try:
        image_vector = normalize(engine.compute_embedding(Content.ImageFile(image_path)).embedding)
    finally:
        Path(image_path).unlink(missing_ok=True)
    query = "task: search query | text: Find similar clothing styles to the outfit shown in this image. Match its colors, garment style, and overall look. " + tip
    text_vector = normalize(engine.compute_embedding(query).embedding)
    mixed_query = normalize([(image_value + text_value) / 2 for image_value, text_value in zip(image_vector, text_vector)])
    ranked = sorted(
        ((sum(query_value * product_value for query_value, product_value in zip(mixed_query, vector)), index)
         for index, vector in enumerate(indexed_vectors)),
        reverse=True,
    )
    recommendations = []
    for score, index in ranked:
        item = catalog[index]
        recommendations.append({
            "id": item["id"], "title": item["title"], "category": item["category"].title(),
            "icon": item.get("icon", "✦"), "tone": item.get("tone", "ink"), "score": round(score, 4),
            "image_url": item.get("image_url"),
            "url": item.get("url") or (AMAZON_SEARCH_BASE + quote_plus(item["title"])),
        })
        if len(recommendations) == 3:
            break
    return recommendations


def prewarm_catalog_index():
    """Build catalog vectors while the mirror is idle, not on the first scan."""
    if not MODEL_PATH.is_file() or EmbeddingEngine is None:
        return
    try:
        ensure_product_vectors(get_embedding_engine())
        logger.info(f"Dress index ready: {len(catalog)} items")
    except Exception:
        logger.exception("EmbeddingGemma catalog warm-up failed; retrieval will retry on the next scan")


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
        "ready": True, "busy": scan_lock.locked(), "app": "Smart Mirror • EmbeddingGemma 2",
        "app_id": "smart-mirror-embeddinggemma",
        "vision_model": "Qwen 2.5-VL-7B", "speech_model": "Piper English",
        "presence_model": "YOLOX-Nano QNN", "presence_backend": "NPU / QNN HTP",
        "processing": "VENTUNO Q", "version": "1.2.0",
        "camera_source": "VENTUNO Q USB webcam", "camera_ready": current_frame is not None,
        "embedding_model": "EmbeddingGemma 2 740M",
        "embedding_ready": MODEL_PATH.is_file() and EmbeddingEngine is not None,
        "embedding_backend": embedding_backend or (os.environ.get("EMBEDDING_BACKEND", "CPU").upper() + " / LiteRT-LM (not initialized)" if MODEL_PATH.is_file() else "Model file required"),
        "catalog_items": len(catalog),
        "catalog_source": catalog_source,
        "catalog_index_ready": product_vectors is not None,
        "amazon_catalog_stale": amazon_catalog_stale,
        "amazon_catalog_expires_at": catalog_expires_at,
    }


ui.expose_api("GET", "/api/status", status)
ui.expose_api("POST", "/api/scan", scan)
ui.expose_api("POST", "/api/presence", presence)
ui.expose_api("GET", "/api/camera/frame", camera_frame)
ui.expose_api("GET", "/api/camera/stream", camera_stream)
embedding_executor.submit(prewarm_catalog_index)
with camera:
    App.run(user_loop=camera_loop)
