"""Pure steering and rotary-encoder interpretation, independent of hardware."""
import math
import statistics
import time
from collections import deque

def clamp(value, low, high):
    return max(low, min(high, value))

def hand_signal(hands):
    valid = []
    for hand in hands:
        try:
            x, y, confidence = float(hand['x']), float(hand['y']), float(hand['confidence'])
            if all(math.isfinite(v) for v in (x, y, confidence)) and confidence >= .65:
                valid.append((1 - x, y))  # Mirror to match the player's preview.
        except (KeyError, TypeError, ValueError):
            continue
    if len(valid) >= 2:
        left, right = min(valid), max(valid)
        width = right[0] - left[0]
        if width >= .12:
            angle = math.atan2(right[1] - left[1], width)
            return angle, 'handlebars', True
    if valid:
        return (valid[0][0] - .5) * 2, 'one hand', True
    return 0., 'no hands', False

def steering(signal, mode, neutral):
    value = (signal - neutral) / (.48 if mode == 'handlebars' else .7)
    if abs(value) < .07:
        return 0.
    # Physical steering must follow the rider, not the mirrored preview axes.
    return -clamp(value, -1., 1.)

class Gearbox:
    def __init__(self):
        self.gear = 1
        self.position = self.presses = None

    def update(self, position, presses):
        position = int(position)
        pressed = self.presses is not None and int(presses) != self.presses
        if self.position is not None:
            delta = (position - self.position + 32768) % 65536 - 32768
            if abs(delta) <= 12:
                self.gear = int(clamp(self.gear + delta, 1, 6))
        self.position, self.presses = position, int(presses)
        return pressed

    def disconnect(self):
        self.position = self.presses = None


def wrist_roll(hand):
    """Palm-width depth angle: unchanged by translation or in-plane steering tilt.

    The inherited tracker normalizes x/y, but leaves landmark z in pixels.
    Restore the 640x480 camera units before computing the angle.
    """
    try:
        if float(hand['confidence']) < .65 or not math.isfinite(float(hand['x'])):
            return None
        points = hand['landmarks']
        if len(points) != 21:
            return None
        a, b = points[5], points[17]
        dx, dy, dz = (float(a[0])-float(b[0]))*640, (float(a[1])-float(b[1]))*480, float(a[2])-float(b[2])
        if not all(math.isfinite(v) for v in (dx, dy, dz)) or math.hypot(dx, dy, dz) < 8:
            return None
        return math.atan2(dz, math.hypot(dx, dy))
    except (KeyError, TypeError, ValueError, IndexError):
        return None


class WristThrottle:
    def __init__(self):
        self.samples = deque(maxlen=30)
        self.rest = self.full = None
        self.hand_label = None
        self.value = 0.
        self.valid = False
        self.angle = None
        self.last_at = None
        self.automatic = False
        self.hand_x = None
        self.brake = 0.
        self.direction = None
        self.direction_candidate = None
        self.direction_count = 0

    @property
    def ready(self):
        return self.rest is not None and self.full is not None

    def update(self, hands, now=None):
        now = time.monotonic() if now is None else now
        candidates = [(hand, wrist_roll(hand)) for hand in hands]
        candidates = [(hand, angle) for hand, angle in candidates if angle is not None]
        # x already mirrors the camera in decode_hand: the rider's right is max x.
        if self.automatic and self.hand_x is not None:
            candidates = [(hand, angle) for hand, angle in candidates if abs(float(hand['x'])-self.hand_x)<.3]
        elif self.hand_label and not self.automatic:
            candidates = [(hand, angle) for hand, angle in candidates if hand.get('handedness') == self.hand_label]
        if not candidates:
            self.valid = False
            self.angle = None
            self.value = 0.
            self.brake = 0.
            self.last_at = None
            self.hand_x = None
            return
        hand, self.angle = max(candidates, key=lambda pair: float(pair[0]['x']))
        self.hand_x = float(hand['x'])
        self.valid = True
        self.samples.append((now, self.angle, hand.get('handedness')))
        if self.automatic and not self.ready and len(self.samples)>=3:
            self.rest = statistics.median(sample[1] for sample in list(self.samples)[-3:])
            self.full = self.rest+.25
            self.hand_label = hand.get('handedness')
        if self.ready:
            delta = self.angle-self.rest
            if self.automatic and self.direction is None:
                candidate = (1 if delta>0 else -1) if abs(delta)>.04 else None
                self.direction_count = self.direction_count+1 if candidate and candidate==self.direction_candidate else (1 if candidate else 0)
                self.direction_candidate = candidate
                if self.direction_count>=3:
                    self.direction = candidate
            signed = (delta*(self.direction or 0)/.25) if self.automatic else delta/(self.full-self.rest)
            target = clamp(signed, 0., 1.)
            target = 0. if target < .07 else (target-.07)/.93
            brake_target = clamp(-signed, 0., 1.)
            brake_target = 0. if brake_target<.07 else (brake_target-.07)/.93
            dt = .1 if self.last_at is None else clamp(now-self.last_at, 0, .2)
            self.value += (target-self.value)*(1-math.exp(-dt/.12))
            self.brake += (brake_target-self.brake)*(1-math.exp(-dt/.09))
            if brake_target>0:
                self.value = 0.
            elif target>0:
                self.brake = 0.
        else:
            self.value = 0.
            self.brake = 0.
        self.last_at = now

    def auto_calibrate(self, now=None):
        now = time.monotonic() if now is None else now
        recent = [sample for sample in self.samples if now-sample[0] <= .75]
        # Starting must never require a second pose or reject a small wrist twist.
        self.rest = statistics.median(s[1] for s in recent) if recent and self.valid else None
        self.full = self.rest+.25 if self.rest is not None else None
        self.hand_label = recent[-1][2] if recent else None
        self.value = 0.
        self.automatic = True
        self.brake = 0.
        self.direction = None
        self.direction_candidate = None
        self.direction_count = 0
        if self.rest is None:
            self.samples.clear()
            self.hand_x = None

    def calibrate(self, pose, now=None):
        self.automatic = False
        now = time.monotonic() if now is None else now
        if not self.valid:
            raise ValueError('Hold your right hand in view before saving the pose.')
        recent = [sample for sample in self.samples if now-sample[0] <= .75]
        if len(recent) < 3:
            raise ValueError('Hold the pose steady for one second, then try again.')
        label = recent[-1][2]
        recent = [sample for sample in recent if sample[2] == label]
        if len(recent) < 3:
            raise ValueError('Keep the same right hand visible for one second.')
        angle = statistics.median(sample[1] for sample in recent)
        if pose == 'rest':
            self.rest, self.full, self.hand_label = angle, None, label
            self.samples.clear()
        elif pose == 'full':
            if self.rest is None:
                raise ValueError('Save the relaxed wrist pose first.')
            if abs(angle-self.rest) < .12:
                raise ValueError('Twist your wrist further: the camera saw almost no change from relaxed. Keep your palm or thumb visible.')
            self.full = angle
        else:
            raise ValueError('Unknown throttle pose.')
        self.value = 0.

    def status(self):
        return {'throttle': round(self.value, 3), 'brake': round(self.brake, 3),
                'wrist_direction_ready': self.direction is not None, 'throttle_valid': self.valid,
                'throttle_ready': self.ready, 'throttle_rest_saved': self.rest is not None,
                'throttle_hand': self.hand_label or 'right', 'wrist_angle': self.angle}
