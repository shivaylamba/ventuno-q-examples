# Adapted from Arduino's Smart Mirror bundle (MPL-2.0).
# SPDX-License-Identifier: MPL-2.0
import base64
import hashlib
import io
import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from urllib.parse import quote_plus


APP_ROOT = Path(__file__).resolve().parents[1]
from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

import prompt
from browser_audio import BrowserAudio
from embeddinggemma_npu import embedding_request
from presence import PersonDetector
from arduino.app_bricks.tts import TextToSpeech
from arduino.app_bricks.vlm import VisionLanguageModel
from arduino.app_bricks.web_ui import WebUI
from arduino.app_peripherals.camera import Camera
from arduino.app_utils import App, Logger
from arduino.app_utils.image import compressed_to_jpeg

logger = Logger("EmbeddingGemmaSmartMirror")
SYSTEM_PROMPT, USER_PROMPT_TEMPLATE = prompt.load_prompts()
MAX_JPEG_BYTES = 2 * 1024 * 1024
scan_lock = Lock()
inference_lock = Lock()
frame_lock = Lock()
catalog_index_lock = Lock()
current_frame: bytes | None = None
SAMPLE_CATALOG_PATH = Path(__file__).with_name("fashion-catalog.json")
AMAZON_CATALOG_PATH = APP_ROOT / "data" / "amazon-catalog.json"
VECTOR_CACHE_PATH = APP_ROOT / "data" / "embedding-vectors.json"
AMAZON_SEARCH_BASE = os.environ.get("AMAZON_SEARCH_BASE", "https://www.amazon.com/s?k=")
catalog_file = json.loads(SAMPLE_CATALOG_PATH.read_text(encoding="utf-8"))
sample_catalog = catalog_file["products"] if isinstance(catalog_file, dict) else catalog_file
sample_catalog_source = catalog_file.get("source", "Sample catalog") if isinstance(catalog_file, dict) else "Sample catalog"
sample_catalog_date = catalog_file.get("snapshot_date") if isinstance(catalog_file, dict) else None


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
    source = sample_catalog_source
    if sample_catalog_date:
        source += f" · {sample_catalog_date} snapshot"
    if amazon_catalog_stale:
        source += " · Amazon feed expired"
    return sample_catalog, source, None


catalog, catalog_source, catalog_expires_at = load_catalog()
product_text_vectors: list[list[float]] | None = None
product_image_vectors: list[list[float]] | None = None
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
    # Keep the audience estimate internal: it describes the garments' likely
    # retail audience, not the wearer's identity, and is never rendered in UI.
    raw_style = vlm.chat(
        message=prompt.build_user_prompt(USER_PROMPT_TEMPLATE), images=[frame],
    ).strip()
    tip, audience = parse_style_response(raw_style)
    if not tip:
        raise RuntimeError("The vision model returned an empty response.")
    tip = " ".join(tip.split())
    result = {"tip": tip, "audio": None, "audio_error": None}
    # Begin retrieval as soon as Qwen returns. It runs alongside speech synthesis.
    recommendation_started = time.monotonic()
    recommendation_job = embedding_executor.submit(recommend, frame, tip, audience)
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


def parse_style_response(raw: str) -> tuple[str, str]:
    """Parse Qwen's private garment-audience hint while displaying only the tip."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            tip = " ".join(str(parsed.get("tip", "")).split())
            audience = str(parsed.get("audience", "unknown")).strip().lower()
            if audience not in {"men", "women", "unisex", "unknown"}:
                audience = "unknown"
            return tip, audience
    except (json.JSONDecodeError, TypeError):
        pass
    # Graceful compatibility if the VLM returns its older plain-text answer.
    return " ".join(raw.split()), "unknown"


def normalize(vector) -> list[float]:
    values = [float(value) for value in vector]
    norm = math.sqrt(sum(value * value for value in values))
    if not norm:
        raise RuntimeError("EmbeddingGemma returned an empty vector.")
    return [value / norm for value in values]


def catalog_image_bytes(item: dict) -> bytes:
    image_ref = str(item.get("image_url", ""))
    if not image_ref.startswith("/assets/"):
        raise RuntimeError(f"Catalog image is not a local App asset: {item.get('id')}")
    image_path = APP_ROOT / "assets" / image_ref.removeprefix("/assets/")
    try:
        image_bytes = image_path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"Missing catalog image for {item.get('id')}: {image_path}") from exc
    if not image_bytes or len(image_bytes) > MAX_JPEG_BYTES:
        raise RuntimeError(f"Catalog image has an unsupported size for {item.get('id')}")
    return image_bytes


def product_image(product_id: str):
    """Serve bundled catalog photos through the app API for the browser UI."""
    item = next((entry for entry in catalog if str(entry.get("id")) == product_id), None)
    if item is None or not str(item.get("image_url", "")).startswith("/assets/"):
        raise HTTPException(404, "Product image not found.")
    try:
        image_bytes = catalog_image_bytes(item)
    except RuntimeError as exc:
        raise HTTPException(404, "Product image not found.") from exc
    return Response(image_bytes, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


def ensure_catalog_vectors() -> tuple[list[list[float]], list[list[float]]]:
    global product_text_vectors, product_image_vectors
    if product_text_vectors is not None and product_image_vectors is not None:
        return product_text_vectors, product_image_vectors
    with catalog_index_lock:
        if product_text_vectors is not None and product_image_vectors is not None:
            return product_text_vectors, product_image_vectors
        return _build_catalog_vectors()


def _build_catalog_vectors() -> tuple[list[list[float]], list[list[float]]]:
    global product_text_vectors, product_image_vectors
    if product_text_vectors is not None and product_image_vectors is not None:
        return product_text_vectors, product_image_vectors
    content_key = json.dumps(catalog, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(f"{catalog_expires_at}:{content_key}".encode()).hexdigest()
    try:
        cached = json.loads(VECTOR_CACHE_PATH.read_text(encoding="utf-8"))
        if (cached.get("version") == 2 and cached.get("fingerprint") == fingerprint and
                cached.get("expires_at") == catalog_expires_at and
                len(cached.get("text_vectors", [])) == len(catalog) and
                len(cached.get("image_vectors", [])) == len(catalog)):
            product_text_vectors = cached["text_vectors"]
            product_image_vectors = cached["image_vectors"]
            logger.info(f"Loaded cached text and product-image index: {len(catalog)} items")
            return product_text_vectors, product_image_vectors
    except (OSError, ValueError, TypeError):
        pass
    texts = [f"task: search result | text: {item['title']}. {item['description']}" for item in catalog]
    text_vectors = []
    for start in range(0, len(texts), 128):
        batch = embedding_request({"texts": texts[start:start + 128]}).get("text_embeddings", [])
        if len(batch) != len(texts[start:start + 128]):
            raise RuntimeError("NPU worker returned an incomplete text-embedding batch.")
        text_vectors.extend(normalize(vector) for vector in batch)

    partial_path = VECTOR_CACHE_PATH.with_suffix(".partial.json")
    image_vectors = []
    try:
        partial = json.loads(partial_path.read_text(encoding="utf-8"))
        if (partial.get("fingerprint") == fingerprint and
                len(partial.get("text_vectors", [])) == len(catalog)):
            image_vectors = partial.get("image_vectors", [])
    except (OSError, ValueError, TypeError):
        pass
    if len(image_vectors) > len(catalog):
        image_vectors = []
    for start in range(len(image_vectors), len(catalog), 16):
        batch_items = catalog[start:start + 16]
        image_payload = [base64.b64encode(catalog_image_bytes(item)).decode("ascii") for item in batch_items]
        batch = embedding_request({"images_b64": image_payload}).get("image_embeddings", [])
        if len(batch) != len(batch_items):
            raise RuntimeError(f"NPU worker returned {len(batch)} product-image vectors for a batch of {len(batch_items)}.")
        image_vectors.extend(normalize(vector) for vector in batch)
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        partial_temp = partial_path.with_suffix(".tmp")
        partial_temp.write_text(json.dumps({
            "fingerprint": fingerprint,
            "text_vectors": text_vectors,
            "image_vectors": image_vectors,
        }), encoding="utf-8")
        partial_temp.replace(partial_path)
        completed = min(start + len(batch_items), len(catalog))
        if completed % 64 == 0 or completed == len(catalog):
            logger.info(f"Product-image index: {completed}/{len(catalog)} images embedded on NPU")

    VECTOR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = VECTOR_CACHE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps({
        "version": 2, "fingerprint": fingerprint, "expires_at": catalog_expires_at,
        "text_vectors": text_vectors, "image_vectors": image_vectors,
    }), encoding="utf-8")
    temp_path.replace(VECTOR_CACHE_PATH)
    partial_path.unlink(missing_ok=True)
    product_text_vectors = text_vectors
    product_image_vectors = image_vectors
    return product_text_vectors, product_image_vectors


def recommend(frame: bytes, tip: str, audience: str = "unknown") -> list[dict]:
    text_vectors, image_vectors = ensure_catalog_vectors()
    audience_query = {
        "men": "The clothing appears intended for the men's clothing market.",
        "women": "The clothing appears intended for the women's clothing market.",
        "unisex": "The clothing appears to be unisex.",
    }.get(audience, "")
    query = ("task: search query | text: Find similar clothing styles to the outfit shown in this image. "
             "Match its garment types, colors, and overall look. " + tip + " " + audience_query)
    embedded = embedding_request({"texts": [query], "image_b64": base64.b64encode(frame).decode("ascii")})
    image_vector = normalize(embedded["image_embedding"])
    text_vector = normalize(embedded["text_embeddings"][0])
    ranked = sorted(
        ((0.75 * sum(image_value * product_value for image_value, product_value in zip(image_vector, image_vectors[index]))
          + 0.25 * sum(text_value * product_value for text_value, product_value in zip(text_vector, text_vectors[index]))
          + (0.035 if audience in {"men", "women"} and catalog[index].get("audience") == audience else 0.0),
          index)
         for index in range(len(catalog))),
        reverse=True,
    )
    recommendations = []
    for score, index in ranked:
        item = catalog[index]
        recommendations.append({
            "id": item["id"], "title": item["title"], "category": item["category"].title(),
            "icon": item.get("icon", "✦"), "tone": item.get("tone", "ink"), "score": round(score, 4),
            "image_url": item.get("image_url"),
            "price_usd": item.get("price_usd"),
            "url": item.get("url") or (AMAZON_SEARCH_BASE + quote_plus(item["title"])),
        })
        if len(recommendations) == 3:
            break
    return recommendations


def prewarm_catalog_index():
    """Build text and direct product-image vectors while the mirror is idle."""
    for attempt in range(30):
        try:
            with inference_lock:
                ensure_catalog_vectors()
            logger.info(f"Text and product-image index ready: {len(catalog)} items")
            return
        except Exception:
            if attempt == 29:
                logger.exception("EmbeddingGemma catalog warm-up failed; retrieval will retry on the next scan")
                return
            logger.warning(f"EmbeddingGemma worker not ready for catalog warm-up (attempt {attempt + 1}/30)")
            time.sleep(2)


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
        "embedding_ready": product_text_vectors is not None and product_image_vectors is not None,
        "embedding_model_available": True,
        "embedding_backend": "Dedicated LiteRT-LM NPU worker (QNN HTP)",
        "catalog_items": len(catalog),
        "catalog_source": catalog_source,
        "catalog_index_ready": product_text_vectors is not None and product_image_vectors is not None,
        "product_image_index_ready": product_image_vectors is not None,
        "amazon_catalog_stale": amazon_catalog_stale,
        "amazon_catalog_expires_at": catalog_expires_at,
    }


ui.expose_api("GET", "/api/status", status)
ui.expose_api("GET", "/api/catalog/{product_id}/image", product_image)
ui.expose_api("POST", "/api/scan", scan)
ui.expose_api("POST", "/api/presence", presence)
ui.expose_api("GET", "/api/camera/frame", camera_frame)
ui.expose_api("GET", "/api/camera/stream", camera_stream)
embedding_executor.submit(prewarm_catalog_index)
with camera:
    App.run(user_loop=camera_loop)
