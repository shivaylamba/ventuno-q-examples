# Smart Mirror · Laptop

Adapted from the supplied Arduino VENTUNO Q Smart Mirror bundle and tutorial:
https://docs.arduino.cc/tutorials/ventuno-q/smart-mirror/

## Hardware

- Barrel-powered VENTUNO Q, connected to the laptop over its USB-C data port.
- Logitech webcam connected to a **VENTUNO Q USB host port**.
- Laptop screen and laptop speakers. No external display or Nano ESP32 button.

## Use on this laptop

1. Keep the board powered and connected over USB.
2. Double-click `Open-Smart-Mirror.cmd` beside the accompanying PowerShell script.
3. The black welcome screen uses Arduino's original animated logo, AI bubble
   and arrow. Select **Enter the mirror** to show the board webcam preview
   and unlock laptop audio. No browser camera permission is needed.
4. Leave **Automatic scan** enabled. Stand in view and hold your pose for about
   three seconds. The mirror starts a three-second countdown, shows Arduino's
   scanning animation, and automatically generates and speaks the style tip.
5. It gives one tip per visit. Step completely out of view for at least four seconds
   to prepare it for the next visitor. The welcome screen returns automatically;
   the next visitor's arrival opens the camera and starts the scan. It detects
   presence, not a person's identity. Detection waits until speech finishes.
6. Select **Hear it again** to replay. **Scan my outfit** remains available for a
   manual retry; disable Automatic scan for button-only operation. Uncheck
   **Speak my tip** to mute playback. Full screen is optional.

The initial Enter the mirror click displays the board camera and unlocks browser
audio; visitors need no scan-button click afterward. **Welcome screen** in the
header reopens the intro while keeping presence detection active. The intro fits
landscape and portrait displays and skips the original footprint screen.
Keep this page active and the laptop awake for automatic operation.

The Windows launcher uses Arduino's bundled ADB and selects the single connected device.
With multiple devices, pass `-BoardSerial` to its PowerShell script.
The page is `http://localhost:7000`. USB forwarding exposes the board's web UI
on the laptop. Camera capture runs on the board, and the laptop plays the WAV.

## Install or reproduce

Import the accompanying `smart-mirror-laptop.zip` in Arduino App Lab, or copy this
folder to `/home/arduino/ArduinoApps/smart-mirror-laptop` on the board. Folder names
determine CLI app IDs; direct installation uses `user:smart-mirror-laptop`.

In App Lab's VLM and TTS bricks, download the models declared in `app.yaml`:

- `genie:qwen2_5_vl_7b_instruct` — Qwen 2.5-VL-7B, local Genie/NPU inference.
- `pipertts_en` — Piper English, local speech synthesis.
- `yolox-qnn-object-detection` — YOLOX-Nano QNN, person detection on the NPU;
  this model is preloaded in Arduino's VENTUNO Q object-detection runner.

Start with `arduino-app-cli app start user:smart-mirror-laptop`. On the laptop:

```powershell
& "$env:LOCALAPPDATA\Arduino15\packages\arduino\tools\adb\32.0.0\adb.exe" -s <BOARD_SERIAL> forward tcp:7000 tcp:7000
```

Then open `http://localhost:7000`. App Lab imports may choose a different app folder
ID; use the ID reported by `arduino-app-cli app list`, or start the app in App Lab.

## Changes from the original

- Responsive laptop layout, visible cursor, live board camera preview and an
  on-screen Scan button replace the portrait kiosk and physical HID button.
- Arduino's black welcome screen and supplied logo, bubble and arrow animations
  introduce the existing camera, scanning and advice flow. The same bubble and
  logo appear beside the advice. A fade introduces the camera screen, and the
  welcome returns after a visitor leaves. No footprint step is used.
- A lightweight person detector adds automatic arrival, countdown, scanning and
  result states. Arduino's supplied scanning GIF is retained. Confidence must be
  at least 55% on several checks over 2.5 seconds to start a scan. Four seconds
  without a person rearms the mirror; momentary misses do not cause repeated tips.
- The board captures the USB webcam and serves an MJPEG preview. Person detection
  reads the current frame directly on the board. The browser submits the exact
  preview snapshot after the countdown for outfit analysis (maximum edge 960 px).
  Images are not saved by the app.
- Person detection uses the QNN/Hexagon backend on the board. It pauses while
  Qwen analyzes the outfit and while the browser speaks. A fresh person check
  validates the captured automatic-scan photo before invoking Qwen.
- The original garment/color task and VLM remain on the board. The prompt uses
  concise instructions and asks the user to reframe when no clothing is visible.
- Piper generates WAV audio on the board. `BrowserAudio` supplies the synthesis
  format without opening an ALSA device; the WAV is returned for Web Audio playback
  on the laptop. No USB speaker on the board is required.
- One scan runs at a time. Errors are shown explicitly and enable retry; there are
  no fabricated style tips or debug buttons that skip inference.
- Camera photos and generated audio stay in memory and are not saved to disk.
  Pause preview stops the browser stream. The board camera runs while the app is
  running; stopping the app in App Lab releases it.

The original assets and font licenses are retained. This adaptation uses the
original application's MPL-2.0 license. No kiosk scripts, display settings,
autologin or security settings are needed.

## Verified on this setup

A Logitech C270 captured a real outfit image, the board generated a style tip,
and browser speech playback completed.
The first scan took about 52 seconds; the next scan took 11.3 seconds including
speech synthesis. Timing varies with model loading and response length.
Aim the webcam downward and stand back to show a shirt or more of the outfit.
Invalid JPEGs, unsupported content types and oversized images were rejected,
and Scan became available again afterward.

Automatic mode was also verified with the live Logitech camera: detection
triggered the countdown and scanning animation without pressing Scan, followed
by a clothing tip and completed laptop speech playback. A second automatic cycle
finished in 10.3 seconds. An empty test frame produced no person detection in
53–73 ms; automatic outfit analysis rejected that frame before calling Qwen.
The running YOLOX process loaded `libQnnHtp.so` and `libQnnHtpV75Stub.so`.
Presence stability, one scan per visit, brief detection misses, departure and
re-entry timing passed state-machine checks. Malformed, unsupported and oversized
presence images were rejected, and subsequent person checks still worked.

## Troubleshooting

- **Camera not ready:** connect the webcam to the board USB host port and start
  this app in App Lab. Browser camera access is not requested.
- **Camera busy:** close any other app using the Logitech webcam.
- **Board disconnected:** check App Lab detects `ventunoq`, reconnect USB and
  run the launcher again. Port forwarding may be lost after reconnection.
- **Another app on port 7000:** stop that app in App Lab before starting the mirror.
- **Analysis unavailable:** inspect App Lab logs; models must finish downloading
  before startup. The first scan includes model initialization and can take longer.
- **Audio unavailable:** the style tip still appears. Check laptop audio output
  and select Hear it again. Board synthesis errors are reported separately.
- **Automatic scan waiting:** show your head and torso, with enough light. The
  webcam must face people, rather than just the ceiling. Keep yourself in view
  through the countdown. A person in the background can also trigger it.
- **Person detection paused:** inspect the object-detection runner's logs. The
  manual Scan button remains available if a presence request fails.

Stop the board app with `arduino-app-cli app stop user:smart-mirror-laptop`.

## Repository packaging

Run `python tools/package_apps.py` from the repository root to build this app's
import ZIP in `dist/`. Windows launchers are in `launchers/windows/`. Model weights
are not included; install the models declared in `app.yaml` using App Lab.
