// SPDX-License-Identifier: MPL-2.0
#include <Arduino_Modulino.h>
#include <Arduino_RouterBridge.h>
#include <vector>

ModulinoMovement movement;
ModulinoKnob knob;
ModulinoBuzzer buzzer;
bool movementReady=false, knobReady=false, buzzerReady=false, lastPressed=false;
uint8_t knobAddress=0;
int position=0, presses=0;
unsigned long sequence=0, lastSample=0, lastPoll=0, lastProbe=0, lastPress=0;
float ax=0, ay=0, az=0, gx=0, gy=0, gz=0;

bool responds(uint8_t address) {
  Wire1.beginTransmission(address);
  return Wire1.endTransmission()==0;
}

bool readKnob(int &next, bool &pressed) {
  if (Wire1.requestFrom(knobAddress,(uint8_t)4)!=4) {
    while (Wire1.available()) Wire1.read();
    return false;
  }
  uint8_t device=Wire1.read(), low=Wire1.read(), high=Wire1.read(), button=Wire1.read();
  if (device!=0x74 && device!=0x76) return false;
  next=(int16_t)(low | (high<<8));
  pressed=button!=0;
  return true;
}

void probeModules() {
  if (movementReady && !responds(0x6A)) movementReady=false;
  if (knobReady && !responds(knobAddress)) knobReady=false;
  if (buzzerReady && !responds(0x1E)) buzzerReady=false;
  if (!movementReady && responds(0x6A)) movementReady=movement.begin();
  if (!knobReady && (responds(0x3A)||responds(0x3B))) {
    knobAddress=responds(0x3A)?0x3A:0x3B;
    knob=ModulinoKnob(knobAddress);
    // Module::begin avoids the old Knob library's unnecessary encoder writes.
    knobReady=knob.Module::begin();
    if (knobReady) readKnob(position,lastPressed);
  }
  if (!buzzerReady && responds(0x1E)) buzzerReady=buzzer.begin();
}

std::vector<float> balanceStatus() {
  return {(float)sequence,(float)(millis()-lastSample),ax,ay,az,gx,gy,gz,
          (float)position,(float)presses,knobReady?1.0f:0.0f,
          buzzerReady?1.0f:0.0f,movementReady?1.0f:0.0f};
}

bool balanceTone(int frequency,int duration) {
  if (!buzzerReady) return false;
  buzzer.tone(constrain(frequency,100,3000),constrain(duration,10,250));
  return true;
}

void setup() {
  Modulino.begin(Wire1);
  probeModules();
  Bridge.begin();
  Bridge.provide_safe("balance_status",balanceStatus);
  Bridge.provide_safe("balance_tone",balanceTone);
  if (buzzerReady) buzzer.tone(880,100);
}

void loop() {
  unsigned long now=millis();
  if (now-lastProbe>=2000) {lastProbe=now;probeModules();}
  if (now-lastPoll>=10) {
    lastPoll=now;
    if (movementReady && movement.available() && movement.update()) {
      ax=movement.getX();ay=movement.getY();az=movement.getZ();
      gx=movement.getRoll();gy=movement.getPitch();gz=movement.getYaw();
      lastSample=millis();sequence++;
    }
    if (knobReady) {
      int next;bool pressed;
      if (readKnob(next,pressed)) {
        position=next;
        if (pressed && !lastPressed && now-lastPress>=150) {
          presses++;lastPress=now;
          if (buzzerReady) buzzer.tone(1000,50);
        }
        lastPressed=pressed;
      }
    }
  }
  delay(2);
}
