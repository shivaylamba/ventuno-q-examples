import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def embedding_request(payload: dict) -> dict:
    """Send an embedding request to this Brick's board-local NPU worker."""
    url = os.environ.get("EMBEDDING_WORKER_URL", "http://embedding-npu-worker:7010")
    request = Request(
        url + "/embed",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=900.0) as response:
            return json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"EmbeddingGemma NPU worker is unavailable: {exc}") from exc
