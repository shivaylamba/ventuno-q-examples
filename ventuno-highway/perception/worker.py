"""Board-only camera/inference service. Frames remain in memory."""
from collections import deque
from dataclasses import asdict
from pathlib import Path
import json
import os
import signal
import threading
import time
import cv2
import yaml
from flask import Flask, Response, request, jsonify
from waitress import serve
from gestures.state import GestureEngine
from perception.pipeline import Capture, Perception
from perception.arduino_adapter import ArduinoTracker
from telemetry.metrics import Metrics, RunLog

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 8192
lock = threading.Lock()
state = {}
events = deque(maxlen=128)
jpeg = None
client = {}
reset_requested = threading.Event()
stop = threading.Event()
metrics = Metrics()

@app.get('/health')
def health():
    return jsonify(ready=bool(state), camera_error=state.get('error', 'Starting')), 200 if state else 503

@app.get('/state')
def status():
    try: after = int(request.args.get('after', -1))
    except ValueError: return jsonify(error='Invalid event cursor'), 400
    with lock:
        result = dict(state)
        result['events'] = [e for e in events if e['id'] > after]
    result['board_sent_at'] = time.monotonic()
    return jsonify(result)

@app.post('/reset')
def reset():
    reset_requested.set()
    return jsonify(ok=True)

@app.post('/client-metrics')
def client_metrics():
    incoming = request.get_json(silent=True) or {}
    if not isinstance(incoming, dict): return jsonify(error='Expected object'), 400
    clean = {}
    for key in ('render_fps', 'frame_ms_p95', 'pipeline_ms', 'event_latency_ms_median', 'event_latency_ms_p95', 'clock_uncertainty_ms', 'particles'):
        value = incoming.get(key)
        if isinstance(value, (int, float)) and 0 <= value <= 100000: clean[key] = value
    for key in ('scene', 'renderer', 'quality', 'visibility', 'source'):
        if isinstance(incoming.get(key), str): clean[key] = incoming[key][:160]
    with lock:
        client.clear()
        client.update(clean)
    return jsonify(ok=True)

@app.get('/frame.jpg')
def frame():
    with lock: value = jpeg
    return Response(value or b'', status=200 if value else 503, mimetype='image/jpeg', headers={'Cache-Control':'no-store'})

@app.get('/stream')
def stream():
    def frames():
        previous = None
        while not stop.is_set():
            with lock: value = jpeg
            if value and value is not previous:
                previous = value
                yield b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(value)).encode()+b'\r\n\r\n'+value+b'\r\n'
            stop.wait(.04)
    return Response(frames(), mimetype='multipart/x-mixed-replace; boundary=frame', headers={'Cache-Control':'no-store'})

def run():
    global jpeg
    config = yaml.safe_load(Path('/engine/config/default.yaml').read_text())
    config['perception']['provider'] = os.getenv('REALITY_PROVIDER', 'auto')
    tracker = ArduinoTracker(config['perception'], metrics)
    print(json.dumps(metrics.metadata), flush=True)
    camera = Capture(config['camera'], metrics)
    perception = Perception(camera, tracker, metrics)
    engine = GestureEngine(config['gestures'])
    log = RunLog(Path('/engine'), 'applab')
    camera.start()
    perception.start()
    event_id = 0
    previous_frame = -1
    sample_at = encode_at = 0
    measured = metrics.snapshot()
    thermal_limited = False
    try:
        while not stop.is_set():
            now = time.monotonic()
            packet = perception.packets.get()
            emitted = engine.update(packet, now)
            if reset_requested.is_set():
                engine.reset()
                reset_requested.clear()
                from gestures.state import Event
                emitted.append(Event('reset', .5, .5, now, now, -1))
            for event in emitted:
                event_id += 1
                with lock: events.append(dict(asdict(event), id=event_id))
                log.event(event, None)
            frame = camera.frames.get()
            if frame and frame.sequence != previous_frame and now-encode_at >= .067:
                ok, encoded = cv2.imencode('.jpg', frame.image, [cv2.IMWRITE_JPEG_QUALITY, 72])
                if ok:
                    with lock: jpeg = encoded.tobytes()
                previous_frame, encode_at = frame.sequence, now
            elif frame is None:
                with lock: jpeg = None
            fresh = packet and now-packet.captured_at <= config['gestures']['max_packet_age']
            error = camera.error or (packet.error if packet else '')
            with lock:
                state.update(protocol_version=1, sequence=packet.sequence if packet else -1,
                             captured_at=packet.captured_at if packet else None,
                             completed_at=packet.completed_at if packet else None,
                             hands=[asdict(h) for h in packet.hands] if fresh else [],
                             palm=engine.predicted_palm(now), velocity=engine.velocity,
                             state=engine.state.value, error=error,
                             provider=tracker.provider, conditions=metrics.metadata,
                             metrics=measured, client=dict(client), event_id=event_id)
            if now-sample_at >= .5:
                measured = metrics.snapshot()
                temperature = measured.get('temperature_c') or 0
                if temperature >= config['graphics']['thermal_limit_c']: thermal_limited = True
                elif temperature < config['graphics']['thermal_limit_c']-5: thermal_limited = False
                tracker.config['max_fps'] = 10 if thermal_limited else config['camera']['fps']
                metrics.metadata['thermal_limited'] = thermal_limited
                row = dict(measured)
                with lock:
                    row.update(state=engine.state.value, hands=len(state['hands']), error=error,
                               client_json=json.dumps(client))
                log.sample(row)
                sample_at = now
            stop.wait(.016)
    finally:
        perception.close()
        camera.close()
        log.close(metrics)

if __name__ == '__main__':
    def exit_handler(*args):
        stop.set()
        thread.join(timeout=8)
        raise SystemExit()
    signal.signal(signal.SIGTERM, exit_handler)
    signal.signal(signal.SIGINT, exit_handler)
    def guarded():
        try: run()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            os._exit(1)
    thread = threading.Thread(target=guarded, daemon=True)
    thread.start()
    serve(app, host='0.0.0.0', port=7011, threads=8)
