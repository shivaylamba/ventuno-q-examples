# SPDX-License-Identifier: MPL-2.0
"""Bounded requests to Arduino's QNN object-detection brick."""
import io
import time
import requests

from arduino.app_bricks.object_detection import ObjectDetection


class PersonDetector:
    def __init__(self, confidence=0.55):
        # Instantiate the registered brick directly: its runner discovery uses
        # the brick's module location and cannot resolve an app-local subclass.
        self.client = ObjectDetection(confidence=confidence)
        self.confidence = confidence

    def infer_from_image(self, image_bytes, image_type="jpg"):
        # The SDK's default image request has no timeout. Bound it so a detector
        # outage cannot hold the shared inference lock indefinitely.
        response = requests.post(
            f"{self.client.url}/api/image",
            files={"file": ("frame.jpg", io.BytesIO(image_bytes), "image/jpeg")},
            timeout=(3, 12),
        )
        response.raise_for_status()
        return response.json()

    def people(self, frame: bytes) -> dict:
        started = time.monotonic()
        result = self.infer_from_image(frame)
        boxes = result.get("result", {}).get("bounding_boxes")
        if not isinstance(boxes, list):
            raise RuntimeError("The person detector did not return a valid result.")
        people = [item for item in boxes if item.get("label") == "person" and float(item.get("value", 0)) >= self.confidence]
        return {
            "person": bool(people), "count": len(people),
            "confidence": round(max((float(item["value"]) * 100 for item in people), default=0), 2),
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
