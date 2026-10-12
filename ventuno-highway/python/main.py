"""App Lab gateway: board hand inference, MCU knob, browser racing graphics."""
import json
import threading
import time
from urllib.request import urlopen
from fastapi import Response
from fastapi.responses import StreamingResponse
from arduino.app_bricks.web_ui import WebUI
from arduino.app_utils import App, Bridge
from control import Gearbox, WristThrottle, hand_signal, steering

ui = WebUI()
BASE = 'http://highway-perception:7011'
lock = threading.Lock()
gearbox = Gearbox()
throttle = WristThrottle()
last_sequence = None
hardware = {'knob_ready': False, 'gear': 1, 'press_id': 0, 'knob_error': 'Waiting for Modulino Knob'}
tracking_state = {'hands': [], 'tracking': False, 'steer': 0, 'mode': 'no hands', 'error': 'Starting hand tracker'}
neutral = {}

def get_json(path):
    with urlopen(BASE + path, timeout=2) as response:
        return json.loads(response.read())

def tracking_loop():
    global last_sequence
    while True:
        try:
            data = get_json('/state')
            hands = data.get('hands', []) if not data.get('error') else []
            signal, mode, valid = hand_signal(hands)
            with lock:
                if data.get('sequence') != last_sequence:
                    throttle.update(hands)
                    last_sequence = data.get('sequence')
                value = steering(signal, mode, neutral.get(mode, 0)) if valid else 0.
                tracking_state.update(hands=hands, tracking=valid, steer=value, signal=signal, mode=mode,
                    error=data.get('error', ''), provider=data.get('provider', 'Starting'),
                    inference_ms=data.get('metrics', {}).get('inference_ms', {}),
                    sequence=data.get('sequence'), received_at=time.monotonic())
        except Exception as exc:
            with lock:
                throttle.update([])
                tracking_state.update(hands=[], tracking=False, steer=0, error='Hand worker unavailable: ' + str(exc)[:100])
        time.sleep(.045)

def knob_loop():
    while True:
        try:
            values = Bridge.call('highway_controls')
            with lock:
                if values and len(values) >= 3 and values[2]:
                    if gearbox.update(values[0], values[1]):
                        hardware['press_id'] += 1
                    hardware.update(knob_ready=True, gear=gearbox.gear, knob_error='')
                else:
                    gearbox.disconnect()
                    hardware.update(knob_ready=False, knob_error='Connect Modulino Knob to the MCU Qwiic port')
        except Exception:
            with lock:
                gearbox.disconnect()
                hardware.update(knob_ready=False, knob_error='MCU/Knob is not responding; keyboard gears are available')
        time.sleep(.06)

def controls():
    with lock:
        result = {**tracking_state, **hardware, **throttle.status()}
        if time.monotonic() - result.get('received_at', 0) > .5:
            result.update(tracking=False, steer=0, throttle_valid=False, throttle=0)
        result.pop('received_at', None)
        return result

def calibrate():
    with lock:
        if not tracking_state.get('tracking'):
            return Response(json.dumps({'error': 'Hold your hands in view first'}), status_code=409, media_type='application/json')
        neutral[tracking_state['mode']] = tracking_state['signal']
        return {'ok': True, 'mode': tracking_state['mode']}

def throttle_pose(pose):
    with lock:
        try:
            if not tracking_state.get('tracking') or time.monotonic()-tracking_state.get('received_at', 0) > .5:
                raise ValueError('Camera tracking is not fresh. Hold your right hand in view.')
            throttle.calibrate(pose)
            return {'ok': True, **throttle.status()}
        except ValueError as exc:
            return Response(json.dumps({'error': str(exc)}), status_code=409, media_type='application/json')

def throttle_rest(): return throttle_pose('rest')
def throttle_full(): return throttle_pose('full')

def quick_start():
    with lock:
        throttle.auto_calibrate()
        if tracking_state.get('tracking'):
            neutral[tracking_state['mode']] = tracking_state['signal']
        return {'ok': True, **throttle.status()}

def stream():
    def chunks():
        try:
            with urlopen(BASE + '/stream', timeout=8) as response:
                while True:
                    chunk = response.read(16384)
                    if not chunk: return
                    yield chunk
        except OSError:
            return
    return StreamingResponse(chunks(), media_type='multipart/x-mixed-replace; boundary=frame')

ui.expose_api('GET', '/api/controls', controls)
ui.expose_api('GET', '/api/status', controls)
ui.expose_api('POST', '/api/calibrate', calibrate)
ui.expose_api('POST', '/api/throttle/rest', throttle_rest)
ui.expose_api('POST', '/api/throttle/full', throttle_full)
ui.expose_api('POST', '/api/start', quick_start)
ui.expose_api('GET', '/api/camera/stream', stream)
threading.Thread(target=tracking_loop, daemon=True).start()
threading.Thread(target=knob_loop, daemon=True).start()
App.run()
