#include <Arduino_Modulino.h>
#include <Arduino_RouterBridge.h>
#include <vector>
ModulinoKnob knob;
bool ready = false, lastPressed = false;
uint8_t address = 0;
int position = 0, presses = 0;
unsigned long lastPoll = 0, lastProbe = 0, lastPress = 0;
bool responds(uint8_t addr) { Wire1.beginTransmission(addr); return Wire1.endTransmission() == 0; }
bool readKnob() {
  if (Wire1.requestFrom(address, (uint8_t)4) != 4) { while (Wire1.available()) Wire1.read(); return false; }
  uint8_t device = Wire1.read(), low = Wire1.read(), high = Wire1.read(), button = Wire1.read();
  if (device != 0x74 && device != 0x76) return false;
  position = (int16_t)(low | (high << 8));
  bool pressed = button != 0;
  if (pressed && !lastPressed && millis() - lastPress >= 150) { presses++; lastPress = millis(); }
  lastPressed = pressed;
  return true;
}
std::vector<int> controls() { return {position, presses, ready ? 1 : 0}; }
void setup() { Modulino.begin(Wire1); Bridge.begin(); Bridge.provide_safe("highway_controls", controls); }
void loop() {
  unsigned long now = millis();
  if (now - lastProbe >= 1500) {
    lastProbe = now;
    if (ready && !responds(address)) ready = false;
    if (!ready && (responds(0x3A) || responds(0x3B))) {
      address = responds(0x3A) ? 0x3A : 0x3B;
      knob = ModulinoKnob(); ready = knob.begin();
      if (ready) { readKnob(); lastPressed = false; }
    }
  }
  if (now - lastPoll >= 20) { lastPoll = now; if (ready && !readKnob()) ready = false; }
  delay(2);
}
