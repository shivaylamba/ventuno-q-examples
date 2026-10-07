# VENTUNO Q Examples

Four interactive Arduino App Lab applications for VENTUNO Q, using local AI and
a laptop display/speakers. Model weights are **not included** in this repository.

| App | Interaction | Hardware beyond VENTUNO Q |
| --- | --- | --- |
| [Smart Mirror](smart-mirror-laptop/) | Automatically detects a visitor and gives an outfit style tip | USB webcam |
| [Smart Mirror · EmbeddingGemma 2](smart-mirror-embeddinggemma/) | Keeps the same Qwen style tip and adds local similar-dress retrieval | USB webcam; 485 MB generic LiteRT-LM model download |
| [AI Object Story Booth](ai-object-story-booth/) | Show an object, choose a storyteller and hear its fictional adventure | USB webcam, Modulino Knob and Buzzer |
| [AI Balance Challenge](ai-balance-challenge/) | Tilt a dragon egg and hold it steady for five seconds to hatch it | Modulino Movement; Knob and Buzzer optional |

Each folder is an independent App Lab project with its own `app.yaml`, Python
backend and HTML/CSS/JavaScript interface. The Modulino apps also include their
MCU sketch and Arduino library profile. The Smart Mirror is our adapted landscape
version with Arduino's animated intro, automatic scanning and laptop speech.

## Run in Arduino App Lab

1. Complete the [VENTUNO Q first setup](https://docs.arduino.cc/tutorials/ventuno-q/first-setup/)
   and connect the board to App Lab. These applications were exercised with App Lab
   0.10.0 and Arduino Modulino 0.7.0 on VENTUNO Q.
2. Clone or download this repository. With Python 3, run:

   ```sh
   python tools/package_apps.py
   ```

3. Import the chosen ZIP from `dist/` into App Lab. Import the other ZIPs too if
   you want all four apps listed in My Apps.
4. Install the models declared in that app's `app.yaml` through App Lab's model
   setup. For Smart Mirror · EmbeddingGemma 2, also follow its README to install
   the separate EmbeddingGemma 2 LiteRT-LM model file. Model weights remain outside this repository.
5. Connect the required hardware and select **Run** in that application's App Lab
   entry. App Lab compiles and uploads the MCU sketch for the Modulino games.
6. Open the app's Web UI. Click its welcome button once to unlock laptop speech.

Run **one app at a time**: all use port 7000, the camera apps share the webcam, and
the Modulino apps replace each other's MCU sketch. Stop the current app before
running another. The app READMEs contain the specific controls and troubleshooting.

### Laptop access over USB

Start the app in App Lab, then use its Web UI link or the matching Windows launcher
in `launchers/windows/`. The launchers restore USB forwarding to `localhost:7000`.
They select the sole connected ADB device; if several devices are attached, run:

```powershell
.\launchers\windows\Open-AI-Balance-Challenge.ps1 -BoardSerial YOUR_BOARD_SERIAL
```

Arduino's bundled ADB path in these scripts uses tools version `32.0.0`; adjust
that path if your App Lab installation provides another version. The booth and
balance launchers open an already-running app. The mirror launcher can also start
its app using the board CLI. No USB audio speaker is required: generated speech
plays in the laptop browser. The Buzzer supplies tones, not spoken narration.

## Where AI runs

The interactive demos use `genie:qwen2_5_vl_7b_instruct` (Qwen 2.5-VL-7B) and
`pipertts_en` (Piper English) on VENTUNO Q through its existing Qualcomm runners.
The Smart Mirror also declares `yolox-qnn-object-detection` for person detection.

- **Mirror:** Qwen examines a board-camera image and writes a style tip.
- **Mirror · EmbeddingGemma 2:** Qwen still examines the image and writes the same
  style tip; then EmbeddingGemma 2 embeds the image and Qwen's description to find
  three similar clothing styles in a local catalog while Piper prepares speech.
- **Booth:** Qwen examines a fresh object image and writes a short fictional story.
- **Balance:** Qwen receives the game's original egg illustration and measured
  round facts to write a mission and reaction. Motion sensing and scoring do not
  wait for AI; this app does not open a camera.
- **Speech:** Piper creates WAV audio on the board; the laptop browser plays it.

The MCU reads Modulinos and drives the Buzzer. The board CPU handles game rules,
camera capture, networking and orchestration; the browser renders the interface.
The model runners provide AI acceleration. This is not an NPU-only application.
No cloud API key is required. Initial model loading can take substantially longer
than subsequent responses, and timings depend on board load and output length.

## Source-only contents and checks

This repository includes application source, original/generated game artwork,
Arduino tutorial UI assets, fonts and license notices. It excludes model weights,
model download archives, cached environments, compiled firmware, runtime camera
captures, generated speech, device logs and setup installers. The model names in
`app.yaml` are dependency references, not model files.

Pure-logic checks can run without a connected board or the App Lab Python SDK:

```sh
python -m unittest discover -s tests -p "test_*.py"
node tests/test-presence-gate.cjs
```

Hardware and model execution require VENTUNO Q. App-specific READMEs record the
measured validation and its limits. The `.gitignore` also excludes common model
formats so subsequent downloads are not accidentally committed.

## License and attribution

Application source is [MPL-2.0](LICENSE). The Smart Mirror derives from Arduino's
[VENTUNO Q Smart Mirror tutorial](https://docs.arduino.cc/tutorials/ventuno-q/smart-mirror/)
and its supplied application assets. Third-party fonts and Socket.IO retain their
separate license notices; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
