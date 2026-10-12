"""Deterministic gesture FSM. All timing is monotonic and replayable."""
from dataclasses import dataclass, field
from enum import Enum
import math


class State(str, Enum):
    IDLE = "IDLE"
    TRACKING = "TRACKING"
    ORB_ACTIVE = "ORB_ACTIVE"
    PROJECTILE = "PROJECTILE"
    PORTAL = "PORTAL"


@dataclass
class Hand:
    x: float
    y: float
    confidence: float = 1.0
    open: bool = True
    pinch: float = 1.0
    fist: bool = False
    handedness: str = "unknown"
    landmarks: list = field(default_factory=list)


@dataclass
class Packet:
    sequence: int
    captured_at: float
    completed_at: float
    hands: list[Hand]
    provider: str
    inference_ms: float = 0.0
    error: str = ""
    simulated: bool = False


@dataclass
class Event:
    kind: str
    x: float
    y: float
    created_at: float
    captured_at: float
    sequence: int


class GestureEngine:
    def __init__(self, config):
        self.config = config
        self.reset()

    def reset(self):
        self.state = State.IDLE
        self.open_since = self.release_since = self.two_since = None
        self.last_seen = None
        self.last_action = -1e9
        self.state_since = 0.0
        self.palm = (0.5, 0.5)
        self.velocity = (0.0, 0.0)
        self.last_sample = None
        self.pinched = False

    def update(self, packet, now):
        c, events = self.config, []
        hands = [] if packet is None or now - packet.captured_at > c["max_packet_age"] else [h for h in packet.hands if h.confidence >= c["confidence"]]
        if self.state == State.PORTAL:
            if now - self.state_since < c["portal_duration"]:
                return events
            self.state = State.TRACKING if hands else State.IDLE
            self.open_since = self.two_since = None
            self.last_action = now
        if not hands:
            self.open_since = self.release_since = self.two_since = None
            if self.last_seen is not None and now - self.last_seen > c["tracking_loss_seconds"]:
                self.reset()
                events.append(Event("reset", .5, .5, now, now, -1))
            return events
        self.last_seen = now
        if self.state == State.IDLE:
            self.state = State.TRACKING
        # Match the existing orb to the nearest hand so handedness flips do not jump it.
        hand = min(hands, key=lambda h: math.hypot(h.x - self.palm[0], h.y - self.palm[1]))
        if self.last_sample != packet.sequence:
            previous = self.palm
            dt = max(1e-3, min(.15, packet.completed_at - getattr(self, "previous_time", packet.completed_at - .03)))
            alpha = 1 - math.exp(-dt / .035)
            self.palm = (previous[0] + alpha * (hand.x - previous[0]), previous[1] + alpha * (hand.y - previous[1]))
            self.velocity = tuple(max(-2., min(2., (self.palm[i] - previous[i]) / dt)) for i in range(2))
            self.previous_time, self.last_sample = packet.completed_at, packet.sequence
        self.pinched = hand.pinch < (c["pinch_exit"] if self.pinched else c["pinch_enter"])
        two_raised = len(hands) >= 2 and all(h.open and h.y < c["raised_y"] for h in hands[:2])
        self.two_since = (self.two_since if self.two_since is not None else now) if two_raised else None
        if self.two_since is not None and now - self.two_since >= c["portal_seconds"] and now - self.last_action >= c["launch_cooldown"]:
            self.state, self.state_since, self.last_action = State.PORTAL, now, now
            events.append(self._event("portal", packet, now))
            self.open_since = self.release_since = self.two_since = None
            return events
        if self.state == State.PROJECTILE and now - self.state_since >= .65:
            self.state = State.TRACKING
            self.open_since = None
        if self.state == State.TRACKING:
            eligible = hand.open and not self.pinched and hand.y < c["raised_y"]
            self.open_since = (self.open_since if self.open_since is not None else now) if eligible else None
            if self.open_since is not None and now - self.open_since >= c["summon_seconds"] and now - self.last_action >= c["launch_cooldown"]:
                self.state = State.ORB_ACTIVE
                events.append(self._event("summon", packet, now))
        elif self.state == State.ORB_ACTIVE:
            releasing = self.pinched or hand.fist or hand.y > .84
            self.release_since = (self.release_since if self.release_since is not None else now) if releasing else None
            if self.release_since is not None and now - self.release_since >= c["release_seconds"]:
                self.state, self.state_since, self.last_action = State.PROJECTILE, now, now
                events.append(self._event("launch", packet, now))
                self.release_since = self.open_since = None
        return events

    def predicted_palm(self, now):
        horizon = max(0., min(.05, now - getattr(self, "previous_time", now)))
        return tuple(max(0., min(1., self.palm[i] + self.velocity[i] * horizon)) for i in range(2))

    def _event(self, kind, packet, now):
        return Event(kind, *self.palm, now, packet.captured_at, packet.sequence)
