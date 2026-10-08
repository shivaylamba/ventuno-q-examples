# Dedicated process for EmbeddingGemma. Keep this container free of the host's
# broad /dev bind mount so QNN can open an NPU session reliably.
import base64
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


APP_ROOT = Path(os.environ.get("APP_ROOT", "/app"))
MODEL_PATH = APP_ROOT / "data/models/embeddinggemma-2-740m_Qualcomm_QCS8275.litertlm"
RUNTIME_ROOT = APP_ROOT / "runtime/npu"
LIBRARY_DIR = Path(os.environ.get("LITERT_DISPATCH_LIB_DIR", str(RUNTIME_ROOT / "lib")))
DSP_DIR = RUNTIME_ROOT / "dsp"

os.environ["LITERT_DISPATCH_LIB_DIR"] = str(LIBRARY_DIR)
for variable, paths in {
    "LD_LIBRARY_PATH": [str(LIBRARY_DIR)],
    "ADSP_LIBRARY_PATH": [str(LIBRARY_DIR), str(DSP_DIR)],
}.items():
    old_paths = os.environ.get(variable, "").split(os.pathsep)
    os.environ[variable] = os.pathsep.join(dict.fromkeys(path for path in paths + old_paths if path))

from litert_lm import Backend, Content, EmbeddingEngine


_engine = None
_engine_lock = threading.Lock()
_inference_lock = threading.Lock()


def get_engine():
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                if not MODEL_PATH.is_file():
                    raise RuntimeError(f"Missing model file: {MODEL_PATH}")
                npu = Backend.NPU(litert_dispatch_lib_dir=str(LIBRARY_DIR))
                _engine = EmbeddingEngine(
                    str(MODEL_PATH), backend=npu, vision_backend=npu,
                    audio_backend=Backend.CPU(),
                )
                _engine.compute_embedding("task: search query | text: initialization")
    return _engine


def embedding_values(content):
    return [float(value) for value in get_engine().compute_embedding(content).embedding]


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path != "/health":
            return self.send_json(404, {"error": "not found"})
        try:
            get_engine()
            self.send_json(200, {"ready": True, "model": MODEL_PATH.name, "backend": "QNN HTP"})
        except Exception as exc:
            self.send_json(503, {"ready": False, "error": str(exc)})

    def do_POST(self):
        if self.path != "/embed":
            return self.send_json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 16 * 1024 * 1024:
                return self.send_json(413, {"error": "request must be between 1 byte and 16 MiB"})
            request = json.loads(self.rfile.read(length))
            texts = request.get("texts", [])
            if not isinstance(texts, list) or len(texts) > 256 or any(not isinstance(text, str) for text in texts):
                return self.send_json(400, {"error": "texts must be a list of at most 256 strings"})
            image_b64 = request.get("image_b64")
            images_b64 = request.get("images_b64", [])
            if not isinstance(images_b64, list) or len(images_b64) > 64 or any(not isinstance(value, str) for value in images_b64):
                return self.send_json(400, {"error": "images_b64 must be a list of at most 64 base64 strings"})
            with _inference_lock:
                text_embeddings = [embedding_values(text) for text in texts]
                result = {"text_embeddings": text_embeddings}
                if image_b64:
                    image_bytes = base64.b64decode(image_b64, validate=True)
                    if len(image_bytes) > 2 * 1024 * 1024:
                        return self.send_json(413, {"error": "image exceeds 2 MiB"})
                    with tempfile.NamedTemporaryFile(prefix="embeddinggemma-frame-", suffix=".jpg") as file:
                        file.write(image_bytes)
                        file.flush()
                        result["image_embedding"] = embedding_values(Content.ImageFile(file.name))
                if images_b64:
                    image_bytes_list = [base64.b64decode(value, validate=True) for value in images_b64]
                    if any(len(image_bytes) > 2 * 1024 * 1024 for image_bytes in image_bytes_list):
                        return self.send_json(413, {"error": "an image exceeds 2 MiB"})
                    if sum(map(len, image_bytes_list)) > 12 * 1024 * 1024:
                        return self.send_json(413, {"error": "image batch exceeds 12 MiB decoded"})
                    image_embeddings = []
                    for image_bytes in image_bytes_list:
                        with tempfile.NamedTemporaryFile(prefix="embeddinggemma-product-", suffix=".jpg") as file:
                            file.write(image_bytes)
                            file.flush()
                            image_embeddings.append(embedding_values(Content.ImageFile(file.name)))
                    result["image_embeddings"] = image_embeddings
            self.send_json(200, result)
        except Exception as exc:
            self.send_json(503, {"error": str(exc)})

    def log_message(self, fmt, *args):
        # Avoid logging request bodies or outfit text.
        print("embedding worker:", fmt % args, flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "7010"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
