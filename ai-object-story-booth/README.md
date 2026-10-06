# AI Object Story Booth

Turn an everyday object into a tiny detective mystery, an alien discovery or a
fairy tale. A separate Arduino App Lab project for VENTUNO Q.

## Hardware

- VENTUNO Q, powered and connected to this laptop over its USB-C data port.
- USB webcam connected to the board's USB host port.
- Modulino Knob and Modulino Buzzer connected in a chain to the board's MCU Qwiic
  connector. The sketch uses `Wire1`, with the official Arduino Modulino library.
- Laptop screen and speakers. The buzzer plays tones; the laptop speaks the story.

## Run from App Lab

1. Open **Apps → AI Object Story Booth** and press **Run**.
2. After startup, open the Web UI link shown in App Lab. On this laptop,
   `http://localhost:7000` reaches the board through USB forwarding. If forwarding
   was lost after reconnecting, use `Open-Object-Story-Booth.cmd` beside its `.ps1`.
3. Select **Open the story booth** once to enable laptop audio and the preview.
   No laptop camera permission is requested; the camera belongs to VENTUNO Q.
4. Turn the Knob to select **Detective**, **Alien Scientist** or **Fairy Tale**.
5. Hold one object prominently in front of the webcam, then press the Knob.
   An immediate short chirp acknowledges a button press, even while busy.
   Three countdown beeps give you time to get ready. The exact captured frame
   remains visible while the board generates the story and speech. When the story
   is ready, the camera returns to live preview for your next object.
6. Hear the story on the laptop. **Hear it again** replays it. Show another object
   and press the Knob again for a new story. The on-screen buttons also work.

The story's mode is fixed when capture starts. Turning the Knob during generation
selects the next story's mode. Presses while busy are consumed rather than queued.
One story runs at a time, including captures initiated by a second browser tab.
Keep the page open and the laptop awake to see results and hear speech.

Refreshing or reopening the page starts a fresh visit: the live preview loads
again and the previous completed story, photograph and audio are not restored.
Press the Knob or **Tell its story** to capture a new frame after the countdown.
If a story is already processing when you refresh, the page reconnects to that
ongoing job; a refresh does not start a second inference.

Start the mirror or booth one at a time: both need the same USB webcam and port.
App Lab Run compiles and installs the booth's MCU sketch automatically. The mirror
projects remain separate and can be started from their own App Lab entries.

## Local AI

- `genie:qwen2_5_vl_7b_instruct`: the already-installed Qwen 2.5-VL-7B image model.
- `pipertts_en`: the already-installed Piper English speech model.
- Both use the board's existing Qualcomm runners. The microcontroller reads the
  Knob and controls the Buzzer through RouterBridge; ordinary camera, networking,
  preprocessing and orchestration also use the board CPU.

No cloud service, API key or additional AI model is required. Each capture is an
independent prompt. Prompts ask for two or three sentences, at most 55 words,
grounded in the prominent object, with a playful fictional adventure. Model
recognition and response length can vary. If the object is unclear, move it closer.
The first story after starting the app includes model initialization and can take
longer than subsequent stories. The UI distinguishes countdown, thinking and speech
creation. Images, stories and WAV audio stay in memory; only the latest result is
retained, and photographs are not saved to disk by this app.

## Import elsewhere

Import `ai-object-story-booth.zip` into App Lab. The archive includes `app.yaml`,
Python, HTML/CSS/JS, and `sketch/sketch.ino` plus its library profile. Direct board
installation uses `/home/arduino/ArduinoApps/ai-object-story-booth`, app ID
`user:ai-object-story-booth`. The declared models must already be installed.

## Troubleshooting

- **Knob / Buzzer not detected:** check the Qwiic chain and correct board connector;
  stop and run this project again after changing connections. Default seven-bit
  addresses are Knob `0x3a` or `0x3b`, Buzzer `0x1e`. The sketch checks the bus every
  two seconds and can reconnect the modules. Custom module addresses require
  adapting the sketch.
- **Controller unavailable:** inspect Python and sketch startup logs in App Lab.
  The booth MCU sketch must be compiled and uploaded by Run; a different sketch
  does not provide its `booth_status` and `booth_tone` functions.
- **Turning works, pressing does nothing:** press the encoder shaft straight down
  until it clicks. The sketch reads the full four-byte position/button packet once
  per poll, validates its device type, and retains a press count between reads.
  The diagnostic Bridge method `booth_knob_debug` returns pressed state, raw button
  byte and failed-read count. No chirp and a zero press count indicate that the
  press has not reached the MCU; the on-screen capture button remains available.
- **Webcam not ready:** check its board USB host connection and stop other camera
  applications. The app refuses a capture if its camera frame is stale.
- **Audio blocked:** click Open the story booth or Hear it again and check laptop
  volume. A physical Knob press cannot unlock browser audio by itself.
- **Board disconnected:** reconnect USB, then run the launcher to restore forwarding.
- **Story failed:** check App Lab's Python/model logs. Press again to retry after
  generation finishes; there are no canned responses that replace failed inference.

## Verified on this board

On 6 October 2026, this separate project was started using App Lab 0.10.0's Run
button on the connected VENTUNO Q. The MCU sketch compiled and uploaded, the
Logitech C270 camera started, and the live browser UI detected both Modulinos
(Knob `0x3a`, Buzzer `0x1e`). Physical rotation changed the selected storyteller.
The user confirmed hearing a Buzzer sound check sent through the real MCU Bridge.

A screen-triggered Fairy Tale capture completed with Qwen and Piper, and the
browser reported that the story played on the laptop. That first cold-model run
took 61.2 seconds for vision generation and 69.8 seconds including speech
creation, excluding the three-second countdown. Concurrent captures correctly
returned HTTP 409, invalid modes returned
400, and changing the next mode did not alter a story already in progress.

After the initial physical press did not register, the MCU reader was changed to
one validated packet per poll with an immediate press chirp. The revised sketch
was compiled and started through App Lab; complete packets arrived with no read
errors. A subsequent physical press incremented the counter to one and started a
Detective capture with trigger `knob`; the three-second countdown completed and
the live UI advanced to generation. This confirms the push switch now reaches the
application. This Knob-triggered story completed and played on the laptop:
45.7 seconds of vision generation and 49.8 seconds including speech after a fresh
app start. Hearing the separately tested Buzzer was confirmed by the user.

A subsequent Alien Scientist capture with the model already loaded completed in
8.0 seconds for vision and 12.7 seconds including speech, plus the three-second
countdown. The browser again played the story and re-enabled capture for the next
object. These are measured examples; timings vary with image, output and board load.

The refresh fix was verified against a real completed result: reopening the UI
showed live preview and an empty story card, a new capture completed successfully,
and the camera returned to live preview on completion. A second refresh again
cleared the finished visit. Consecutive board camera frames were confirmed to
change; verification did not save camera photographs.

## Sources and license

Built with Arduino App Lab's WebUI, VLM, TTS, Camera and RouterBridge APIs.
The `BrowserAudio` adapter comes from our Smart Mirror adaptation of Arduino's
MPL-2.0 Smart Mirror example. Application source is MPL-2.0; bundled Open Sans
and Roboto Mono fonts retain their SIL Open Font License files.

- https://docs.arduino.cc/libraries/arduino_modulino/
- https://docs.arduino.cc/hardware/modulino-knob/
- https://docs.arduino.cc/hardware/modulino-buzzer/
- https://docs.arduino.cc/tutorials/ventuno-q/smart-mirror/

## Repository packaging

Run `python tools/package_apps.py` from the repository root to build this app's
import ZIP in `dist/`. Windows launchers are in `launchers/windows/`. Model weights
are not included; install the models declared in `app.yaml` using App Lab.
