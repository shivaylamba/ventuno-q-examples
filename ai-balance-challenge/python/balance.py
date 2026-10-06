"""Measured motion drives this game; generated text never controls the rules."""
# SPDX-License-Identifier: MPL-2.0
import math
import uuid

DIFFICULTIES=[
    {"id":"easy","name":"Easy","angle":12,"gyro":35,"motion":0.30},
    {"id":"normal","name":"Normal","angle":8,"gyro":25,"motion":0.20},
    {"id":"hard","name":"Hard","angle":5,"gyro":15,"motion":0.15},
]
GOAL=5.0
ROUND_LIMIT=25.0

def norm(v): return math.sqrt(sum(x*x for x in v))
def unit(v):
    magnitude=norm(v)
    if magnitude<0.01: raise ValueError("No gravity reference")
    return tuple(x/magnitude for x in v)
def angle(a,b):
    return math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(unit(a),unit(b)))))))
def orientation(v):
    x,y,z=v
    return math.degrees(math.atan2(y,z)),math.degrees(math.atan2(-x,math.hypot(y,z)))
def wrap(degrees): return (degrees+180)%360-180
def knob_delta(current,previous): return (current-previous+32768)%65536-32768

class BalanceGame:
    def __init__(self):
        self.phase="idle";self.difficulty_index=0;self.round_id=None
        self.sensor_ready=False;self.last_sequence=None;self.last_tick=None
        self.reference=None;self.filtered=None;self.calibration=[];self.quiet_since=None
        self.started=0;self.active_started=0;self.held=0;self.best=0;self.resets=0
        self.outside_since=None;self.last_warning=0;self.max_angle=0;self.result=None
        self.angle_error=0;self.gyro=0;self.motion=0;self.tilt_x=0;self.tilt_y=0
        self.steady=False;self.reason="";self.calibration_progress=0;self.rules=None
        self.events=[];self.completion=None

    def start(self,now):
        if not self.sensor_ready: raise ValueError("Movement is not ready. Check its Qwiic connection.")
        if self.phase in ("calibrating","active"): raise RuntimeError("A round is already running.")
        self.round_id=uuid.uuid4().hex;self.phase="calibrating";self.started=now
        self.rules=dict(DIFFICULTIES[self.difficulty_index]);self.reference=None
        self.filtered=None;self.calibration=[];self.quiet_since=None
        self.held=0;self.best=0;self.resets=0;self.result=None;self.completion=None
        self.max_angle=0;self.outside_since=None;self.last_tick=None
        self.calibration_progress=0;self.reason="Hold the module still to set your starting position."
        self.events.append((660,80))

    def cancel(self):
        self.phase="idle";self.round_id=None;self.result=None;self.completion=None
        self.held=0;self.reference=None;self.reason="";self.calibration_progress=0

    def finish(self,won,now,reason):
        elapsed=max(0,now-self.active_started) if self.phase=="active" else 0
        self.phase="result";self.reason=reason
        self.result={"id":self.round_id,"won":won,"difficulty":self.rules["name"],
                     "seconds":round(elapsed,1),
                     "best_hold":round(self.best,2),"resets":self.resets,
                     "max_angle":round(self.max_angle,1),"reason":reason,
                     "score":max(10,100-7*self.resets-2*int(max(0,elapsed-GOAL))) if won else 0}
        self.completion=dict(self.result)
        self.events.append((1047 if won else 220,180))

    def tick(self,sequence,age,accel,gyro,ready,now):
        valid=ready and age<300 and all(math.isfinite(x) for x in (*accel,*gyro)) and 0.1<norm(accel)<4.5
        self.sensor_ready=bool(valid)
        if not valid:
            if self.phase in ("calibrating","active"):
                self.finish(False,now,"Movement connection lost. Reconnect it and try again.")
            return
        if sequence==self.last_sequence: return
        self.last_sequence=sequence
        dt=min(0.12,max(0,now-self.last_tick)) if self.last_tick is not None else 0
        self.last_tick=now
        self.filtered=tuple(accel) if self.filtered is None else tuple(.55*a+.45*b for a,b in zip(accel,self.filtered))
        self.gyro=norm(gyro);self.motion=abs(norm(accel)-1)
        baseline=self.reference or (0,0,1)
        current_roll,current_pitch=orientation(self.filtered)
        base_roll,base_pitch=orientation(baseline)
        self.tilt_x=wrap(current_roll-base_roll);self.tilt_y=wrap(current_pitch-base_pitch)
        self.angle_error=angle(self.filtered,baseline)

        if self.phase=="calibrating":
            if now-self.started>15:
                self.active_started=now
                self.finish(False,now,"Could not calibrate. Rest the module flat and try again.")
                return
            average=tuple(sum(v[i] for v in self.calibration)/len(self.calibration) for i in range(3)) if self.calibration else accel
            quiet=self.gyro<15 and self.motion<.2 and angle(accel,average)<3
            if not quiet:
                self.calibration=[];self.quiet_since=None;self.calibration_progress=0
                self.reason="A little movement detected. Hold still for two seconds."
            else:
                if self.quiet_since is None:self.quiet_since=now
                self.calibration.append(tuple(accel))
                self.calibration_progress=min(1,(now-self.quiet_since)/2)
                self.reason="Hold still… setting your starting position."
                if self.calibration_progress>=1 and len(self.calibration)>=20:
                    self.reference=unit(tuple(sum(v[i] for v in self.calibration)/len(self.calibration) for i in range(3)))
                    self.phase="active";self.active_started=now;self.held=0
                    self.reason="Keep the dragon egg steady for five seconds."
                    self.events.append((880,90))
            return

        if self.phase=="active":
            self.max_angle=max(self.max_angle,self.angle_error)
            self.steady=(self.angle_error<=self.rules["angle"] and self.gyro<=self.rules["gyro"] and self.motion<=self.rules["motion"])
            if self.steady:
                self.outside_since=None;self.held+=dt;self.best=max(self.best,self.held)
                self.reason="Steady… the egg is getting warmer."
            else:
                if self.outside_since is None:self.outside_since=now
                if now-self.outside_since>=.15 and self.held>0:
                    self.resets+=1;self.held=0
                self.reason="Too much movement. Settle the egg and start the hold again."
                if now-self.last_warning>=.8:
                    self.last_warning=now;self.events.append((330,60))
            if self.held>=GOAL:self.finish(True,now,"You kept the egg steady. Your dragon has hatched!")
            elif now-self.active_started>=ROUND_LIMIT:self.finish(False,now,"The egg needs another try. Your best hold was %.1f seconds."%self.best)

    def snapshot(self,now):
        return {"phase":self.phase,"round_id":self.round_id,"difficulty":DIFFICULTIES[self.difficulty_index]["id"],
                "difficulties":DIFFICULTIES,"round_difficulty":self.rules["name"] if self.rules else None,
                "sensor_ready":self.sensor_ready,"held":round(min(GOAL,self.held),2),"goal":GOAL,
                "remaining":round(max(0,ROUND_LIMIT-(now-self.active_started)),1) if self.phase=="active" else ROUND_LIMIT,
                "calibration_progress":round(self.calibration_progress,2),"angle":round(self.angle_error,1),
                "gyro":round(self.gyro,1),"motion":round(self.motion,3),
                "tilt_x":round(self.tilt_x,1),"tilt_y":round(self.tilt_y,1),
                "steady":self.steady,"resets":self.resets,"best_hold":round(self.best,2),
                "reason":self.reason,"result":dict(self.result) if self.result else None}
