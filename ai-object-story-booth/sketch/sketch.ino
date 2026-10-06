// SPDX-License-Identifier: MPL-2.0
#include <Arduino_Modulino.h>
#include <Arduino_RouterBridge.h>
#include <vector>

ModulinoKnob knob;
ModulinoBuzzer buzzer;
bool knobReady = false, buzzerReady = false, lastPressed = false;
int position = 0, presses = 0;
uint8_t knobAddress = 0;
int buttonByte = 0, readErrors = 0;
unsigned long lastPoll = 0, lastProbe = 0, lastPress = 0;

bool readKnob(int &next, bool &pressed) {
  // Read position and button together, with a complete packet check.
  // get() followed by isPressed() performs two back-to-back I2C reads.
  if (Wire1.requestFrom(knobAddress, (uint8_t)4) != 4) {
    while (Wire1.available()) Wire1.read();
    readErrors++;
    return false;
  }
  uint8_t device = Wire1.read();
  uint8_t low = Wire1.read(), high = Wire1.read();
  buttonByte = Wire1.read();
  if (device != 0x74 && device != 0x76) { readErrors++; return false; }
  next = (int16_t)(low | (high << 8));
  pressed = buttonByte != 0;
  return true;
}

bool responds(uint8_t address) {
  Wire1.beginTransmission(address);
  return Wire1.endTransmission() == 0;
}

void probeModules() {
  if (knobReady && !responds(knobAddress)) knobReady = false;
  if (buzzerReady && !responds(0x1E)) buzzerReady = false;
  if (!knobReady && (responds(0x3A) || responds(0x3B))) {
    knobAddress = responds(0x3A) ? 0x3A : 0x3B;
    knob = ModulinoKnob();
    knobReady = knob.begin();
    if (knobReady) readKnob(position, lastPressed);
  }
  if (!buzzerReady && responds(0x1E)) buzzerReady = buzzer.begin();
}

std::vector<int> boothStatus() {
  return {position, presses, knobReady ? 1 : 0, buzzerReady ? 1 : 0,
          knobReady ? knobAddress : 0, buzzerReady ? 0x1E : 0};
}

std::vector<int> knobDebug() { return {lastPressed ? 1 : 0, buttonByte, readErrors}; }

bool boothTone(int frequency, int duration) {
  if (!buzzerReady) return false;
  frequency = constrain(frequency, 100, 3000);
  duration = constrain(duration, 10, 250);
  buzzer.tone(frequency, duration);
  return true;
}

void setup() {
  Modulino.begin(Wire1);  // VENTUNO Q's MCU Qwiic bus.
  probeModules();
  Bridge.begin();
  // I2C and hardware functions execute on the main loop, not the RPC thread.
  Bridge.provide_safe("booth_status", boothStatus);
  Bridge.provide_safe("booth_tone", boothTone);
  Bridge.provide_safe("booth_knob_debug", knobDebug);
  if (buzzerReady) buzzer.tone(880, 100);
}

void loop() {
  unsigned long now = millis();
  if (now - lastProbe >= 2000) { lastProbe = now; probeModules(); }
  if (now - lastPoll >= 20) {
    lastPoll = now;
    if (knobReady) {
      int next;
      bool pressed;
      if (readKnob(next, pressed)) {
        if (next != position && buzzerReady) buzzer.tone(660, 18);
        position = next;
        if (pressed && !lastPressed && now - lastPress >= 150) {
          presses++; lastPress = now;
          if (buzzerReady) buzzer.tone(1000, 60);
        }
        lastPressed = pressed;
      }
    }
  }
  delay(2);
}
