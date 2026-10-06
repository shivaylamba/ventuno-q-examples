# AI Balance Challenge

A separate Arduino App Lab game for VENTUNO Q: keep a dragon egg steady, hatch a
baby dragon, and hear playful narration generated locally from your round result.

## Hardware

- VENTUNO Q, powered and connected to the laptop over USB-C data.
- Modulino Movement connected to the VENTUNO Q's MCU Qwiic connector; default
  address `0x6a`
  (the sketch also supports `0x6b` when its address jumper has been changed).
- Modulino Knob (`0x3a` or `0x3b`) for difficulty and starting a round, and
  Modulino Buzzer (`0x1e`) for warning chirps and a victory tune.
- Laptop display and speakers. No USB speaker, camera, or Thermo is needed.

The sketch uses `Wire1` and the installed Arduino Modulino 0.7.0 library. The
Movement module measures its own motion: hold the module as your controller.
Knob and Buzzer are optional; Movement is required. The screen provides equivalent
start and difficulty buttons. Keep enough slack in the Qwiic cable to move it.

## Play

1. In App Lab, stop the currently running app, then open **My Apps → AI Balance
   Challenge → Run**. App Lab compiles and uploads this project's MCU sketch.
2. Open its Web UI. On this laptop, USB forwarding makes it available at
   `http://localhost:7000`. The included `Open-AI-Balance-Challenge.cmd` restores
   forwarding and opens the running game.
3. Choose **Enter the hatchery** once to enable laptop speech.
4. Turn the Knob to select **Easy**, **Normal**, or **Hard**. Press it, or select
   **Start a round**. Hold the module flat and still for two seconds to calibrate
   the starting position. The egg follows your tilt on screen.
5. Keep that position steady for five seconds. Large tilt, rotation, or shaking
   causes a warning chirp and resets the hold after a short noise grace period.
   You have 25 seconds after calibration to finish.
6. On success, the dragon hatches and the Buzzer plays an ascending tune. The AI
   adds a short reaction based on the measured outcome and score. Laptop speech
   plays automatically when enabled; **Hear it again** replays it.
7. Press again for another egg. Each round calibrates afresh. Difficulty changes
   during a round select the next round; the active round keeps its original rules.

**Cancel round** returns to idle. A press during calibration or play does not
queue another round. Resting the module on a table is useful for learning the
game and testing the connection; holding it in your hand makes it a challenge.

## Real-time controls and local AI

The MCU samples acceleration (g) and angular velocity (degrees/second). The board's
Python game reads fresh sensor packets approximately 25 times/second, computes
tilt from a two-second gravity reference and scores the hold. The browser animates
the latest tilt smoothly. Game rules are deterministic; AI does not judge raw
motion or invent scores. Stale or missing sensor readings cannot count as a win.

| Difficulty | Allowed tilt from starting position | Rotation | Acceleration change |
|---|---:|---:|---:|
| Easy | 12° | 35°/s | 0.30 g |
| Normal | 8° | 25°/s | 0.20 g |
| Hard | 5° | 15°/s | 0.15 g |

Existing `genie:qwen2_5_vl_7b_instruct` generates a fantasy mission and short
commentary from round facts plus the game's original egg illustration. The
installed vision runner requires an image, so the app supplies that illustration
instead of using a webcam. Existing `pipertts_en`
generates speech on the board; a memory-backed WAV is played on the laptop.
The existing Qualcomm model runners provide acceleration; game logic, networking
and orchestration use the board CPU and MCU. There is no cloud service, API key,
additional model, sensor-model training, or camera capture.

AI warms up in a background thread; the game remains playable during model loading
or narration. One AI request runs at a time. Results for superseded rounds are
discarded, and narration is played between rounds. If AI is unavailable, the live
motion game remains usable and the UI reports the error. Instructions and scoring
remain controlled by the application. Generated fantasy phrasing can vary.

## Import and troubleshooting

Import `ai-balance-challenge.zip` into App Lab. Project ID: `user:ai-balance-challenge`.
Board folder: `/home/arduino/ArduinoApps/ai-balance-challenge`. Start one of the
mirror, booth, or balance applications at a time; they share port 7000 and the MCU.

- **Movement unavailable:** check the Qwiic chain and the board MCU connector.
  The sketch checks the bus every two seconds. `/api/diagnostics` lists the
  addresses seen on the MCU Qwiic bus; expect `0x6a` for Movement. Stop and Run
  again if needed.
- **Calibration restarts:** hold still or rest the module flat on a table until
  the two-second progress bar completes. Movement during calibration starts it over.
- **Connection lost:** an active round ends without a win. Reconnect, then start
  another round. No fixed dummy sensor readings substitute for missing hardware.
- **Silent laptop:** select Enter the hatchery or Hear it again and check volume.
  Physical Knob presses cannot unlock browser audio on their own.
- **Controller unavailable:** ensure App Lab uploaded this project's sketch. Its
  Bridge methods are `balance_status`, `balance_scan` and `balance_tone`.

## Verified on this VENTUNO Q (6 October 2026)

App Lab compiled and uploaded the MCU sketch, then launched the separate project.
Movement, Knob and Buzzer were detected. Live sensor samples changed with physical
tilt; Knob rotation selected difficulty and its press started a round.

A real Easy round calibrated, held for 5.03 seconds and scored 100/100 with zero
restarts. A physical Hard round recorded three wobble resets and a 0.7-second best
hold. Qwen generated reactions from these results; the successful round's reaction
and Piper audio were ready in 8.6 seconds. Browser playback started successfully.
The first cold mission took 55 seconds while gameplay remained available.
Buzzer commands were accepted; audible hardware feedback awaits user confirmation.

Seven game-engine checks passed, covering calibration, wins, wobble resets, stale
and repeated samples, absent hardware, controller wraparound and moving calibration.
Duplicate starts during a running round returned HTTP 409. The success screen was
visually checked after fixing SVG visibility.

## License and sources

Application code and original SVG artwork: MPL-2.0. The BrowserAudio adapter is
reused from our Smart Mirror/Story Booth implementation. Bundled Open Sans and
Roboto Mono fonts retain their SIL Open Font License files.

- https://docs.arduino.cc/hardware/modulino-movement/
- https://docs.arduino.cc/libraries/arduino_modulino/
- https://docs.arduino.cc/tutorials/ventuno-q/smart-mirror/

## Repository packaging

Run `python tools/package_apps.py` from the repository root to build this app's
import ZIP in `dist/`. Windows launchers are in `launchers/windows/`. Model weights
are not included; install the models declared in `app.yaml` using App Lab.
