"""Bounded metrics; no frames or visitor profiles are written."""
from collections import defaultdict, deque
import csv
import json
import resource
import threading
import time
from pathlib import Path

import numpy as np


class Metrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.times = defaultdict(lambda: deque(maxlen=180))
        self.samples = defaultdict(lambda: deque(maxlen=2400))
        self.metadata = {}
        self.dropped = 0
        self.events = deque(maxlen=300)
        self.start = time.monotonic()
        self.cpu_last = (time.monotonic(), time.process_time())

    def mark(self, key, timestamp):
        with self.lock:
            self.times[key].append(timestamp)

    def add(self, key, value):
        with self.lock:
            self.samples[key].append(float(value))

    def rate(self, key, now):
        data = [t for t in self.times[key] if now - t <= 3]
        return (len(data) - 1) / (data[-1] - data[0]) if len(data) > 1 else 0.

    def snapshot(self):
        now, cpu = time.monotonic(), time.process_time()
        cpu_percent = 100 * (cpu - self.cpu_last[1]) / max(.001, now - self.cpu_last[0])
        self.cpu_last = (now, cpu)
        result = {"elapsed_s": round(now - self.start, 3), "dropped_frames": self.dropped,
                  "cpu_percent_process": round(cpu_percent, 1), "rss_mb": 0.0, "temperature_c": temperature()}
        try:
            for line in Path("/proc/self/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    result["rss_mb"] = int(line.split()[1]) / 1024
        except OSError:
            result["rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        with self.lock:
            for name in ("capture", "inference", "render"):
                result[name + "_fps"] = round(self.rate(name, now), 2)
            for name in ("inference_ms", "motion_latency_ms", "event_latency_ms", "gpu_frame_ms"):
                data = self.samples[name]
                result[name + "_median"] = round(float(np.median(data)), 2) if data else None
                result[name + "_p95"] = round(float(np.percentile(data, 95)), 2) if data else None
        return result


def temperature():
    values = []
    for path in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        try:
            value = int(path.read_text()) / 1000
            if 0 < value < 150:
                values.append(value)
        except (OSError, ValueError):
            pass
    return max(values) if values else None


class RunLog:
    def __init__(self, root, label):
        self.directory = root / "runs" / (time.strftime("%Y%m%d-%H%M%S") + "-" + label)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.file = (self.directory / "samples.csv").open("w", newline="")
        self.writer = None
        self.event_file = (self.directory / "events.jsonl").open("w")

    def sample(self, row):
        if self.writer is None:
            self.writer = csv.DictWriter(self.file, fieldnames=list(row))
            self.writer.writeheader()
        self.writer.writerow(row)
        self.file.flush()

    def event(self, event, rendered_at):
        row = dict(event.__dict__, rendered_at=rendered_at, protocol_version=1)
        self.event_file.write(json.dumps(row) + "\n")
        self.event_file.flush()

    def close(self, metrics):
        (self.directory / "summary.json").write_text(json.dumps({"metrics": metrics.snapshot(), "conditions": metrics.metadata}, indent=2))
        self.file.close()
        self.event_file.close()
