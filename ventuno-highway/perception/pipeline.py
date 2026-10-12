"""Capture and inference threads use one slot each, never a backlog."""
import glob
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from gestures.state import Hand, Packet
from perception.mp_palmdet import MPPalmDet
from perception.mp_handpose import MPHandPose


@dataclass
class Frame:
    sequence: int
    captured_at: float
    image: np.ndarray


class LatestSlot:
    def __init__(self):
        self.lock = threading.Lock()
        self.value = None

    def set(self, value):
        with self.lock:
            self.value = value

    def get(self):
        with self.lock:
            return self.value


def camera_devices():
    """Prefer actual USB video nodes, not the Qualcomm codec devices."""
    devices = []
    for node in sorted(glob.glob("/dev/video*"), key=lambda s: int(s.removeprefix("/dev/video"))):
        name = Path("/sys/class/video4linux") / Path(node).name / "name"
        text = name.read_text().strip() if name.exists() else ""
        if text:
            devices.append((node, text))
    return devices


class Capture:
    def __init__(self, config, metrics):
        self.config, self.metrics = config, metrics
        self.frames = LatestSlot()
        self.stop = threading.Event()
        self.error = "Connecting camera"
        self.device = ""
        self.thread = threading.Thread(target=self.run, daemon=True, name="camera")

    def start(self):
        self.thread.start()

    def run(self):
        sequence = 0
        while not self.stop.is_set():
            devices = camera_devices() if self.config["device"] == "auto" else [(str(self.config["device"]), "selected")]
            cap = None
            for node, name in devices:
                candidate = cv2.VideoCapture(node, cv2.CAP_V4L2)
                if not candidate.isOpened():
                    candidate.release()
                    continue
                candidate.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                candidate.set(cv2.CAP_PROP_FRAME_WIDTH, self.config["width"])
                candidate.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config["height"])
                candidate.set(cv2.CAP_PROP_FPS, self.config["fps"])
                candidate.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                ok, image = candidate.read()
                if ok:
                    cap, self.device = candidate, f"{name} {node}"
                    self.metrics.metadata["camera"] = {"device": node, "name": name, "actual_width": image.shape[1], "actual_height": image.shape[0], "reported_fps": candidate.get(cv2.CAP_PROP_FPS), "fourcc": int(candidate.get(cv2.CAP_PROP_FOURCC))}
                    break
                candidate.release()
            if cap is None:
                self.error = "Camera unavailable. Connect a USB webcam; retrying automatically."
                self.frames.set(None)
                self.stop.wait(self.config["retry_seconds"])
                continue
            self.error = ""
            try:
                while not self.stop.is_set():
                    ok, image = cap.read()
                    captured = time.monotonic()  # host dequeue time, not sensor exposure time
                    if not ok:
                        break
                    sequence += 1
                    self.frames.set(Frame(sequence, captured, image))
                    self.metrics.mark("capture", captured)
            finally:
                cap.release()
                self.frames.set(None)
                self.error = "Camera disconnected. Reconnecting…"
            self.stop.wait(self.config["retry_seconds"])

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)


def decode_hand(result, width, height):
    landmarks = result[4:67].reshape(21, 3).copy()
    landmarks[:, 0] = 1.0 - landmarks[:, 0] / width  # mirror exactly once
    landmarks[:, 1] /= height
    wrist = landmarks[0, :2]
    extended = sum(np.linalg.norm(landmarks[tip, :2] - wrist) > 1.12 * np.linalg.norm(landmarks[pip, :2] - wrist) for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)])
    scale = max(.015, float(np.linalg.norm(landmarks[5, :2] - landmarks[17, :2])))
    pinch = float(np.linalg.norm(landmarks[4, :2] - landmarks[8, :2])) / scale
    palm = np.mean(landmarks[[0, 5, 9, 13, 17], :2], axis=0)
    return Hand(float(np.clip(palm[0], 0, 1)), float(np.clip(palm[1], 0, 1)), float(result[131]), bool(extended >= 3), pinch, bool(extended <= 1),
                "right" if result[130] > .5 else "left", landmarks.tolist())


class Tracker:
    def __init__(self, root, config, metrics):
        self.config, self.metrics = config, metrics
        cv2.setNumThreads(config["cpu_threads"])
        for name in ("palm", "hand"):
            if not (root / "models" / (name + ".onnx")).is_file():
                raise FileNotFoundError("Hand model missing. Run scripts/setup.sh; simulation is available with --simulate.")
        self.palm = MPPalmDet(str(root / "models/palm.onnx"), scoreThreshold=config["palm_confidence"])
        self.hand = MPHandPose(str(root / "models/hand.onnx"), confThreshold=config["hand_confidence"])
        self.provider = "OpenCV DNN / CPU"
        self.fallback_reason = ""
        if config["provider"] != "cpu":
            from perception.qnn import install_qnn
            try:
                install_qnn(self, root, config, metrics)
            except Exception as exc:
                self.fallback_reason = str(exc)
                if config["provider"] == "qnn":
                    raise RuntimeError(f"Strict QNN mode failed: {exc}") from exc
        self.metrics.metadata.update(provider=self.provider, fallback_reason=self.fallback_reason)

    def infer(self, frame):
        start = time.monotonic()
        palms = self.palm.infer(frame.image)
        hands = []
        for palm in sorted(palms, key=lambda p: -p[-1])[:self.config["max_hands"]]:
            if np.any(palm[:4] < -max(frame.image.shape[:2])):
                continue
            try:
                result = self.hand.infer(frame.image, palm)
            except cv2.error:
                continue  # degenerate edge crop; try again on the next frame
            if result is not None:
                hands.append(decode_hand(result, frame.image.shape[1], frame.image.shape[0]))
        completed = time.monotonic()
        duration = 1000 * (completed - start)
        self.metrics.mark("inference", completed)
        self.metrics.add("inference_ms", duration)
        return Packet(frame.sequence, frame.captured_at, completed, hands, self.provider, duration)


class Perception:
    def __init__(self, capture, tracker, metrics):
        self.capture, self.tracker, self.metrics = capture, tracker, metrics
        self.packets = LatestSlot()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name="perception")

    def start(self):
        self.thread.start()

    def run(self):
        sequence = -1
        while not self.stop.is_set():
            start = time.monotonic()
            frame = self.capture.frames.get()
            if frame is None or frame.sequence == sequence:
                self.stop.wait(.004)
                continue
            self.metrics.dropped += max(0, frame.sequence - sequence - 1) if sequence >= 0 else 0
            sequence = frame.sequence
            try:
                packet = self.tracker.infer(frame)
                self.packets.set(packet)
            except Exception as exc:
                self.packets.set(Packet(sequence, frame.captured_at, time.monotonic(), [], self.tracker.provider, error=str(exc)))
                self.stop.wait(.2)
            self.stop.wait(max(0, 1 / self.tracker.config["max_fps"] - (time.monotonic() - start)))

    def close(self):
        self.stop.set()
        self.thread.join(timeout=4)
