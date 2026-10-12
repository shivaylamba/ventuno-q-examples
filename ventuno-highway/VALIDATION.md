# Validation — 12 October 2026

- Imported as `user:ventuno-highway`; App Lab compiled and uploaded the Knob sketch, then successfully launched the hand worker and WebUI gateway.
- Both containers running; perception worker healthy. `/api/controls` returned real camera hands, changing packet sequence, and `knob_ready: true`. Gear changed from 1 to 6 during live checks, proving encoder changes reach the game service; visitor steering feel still needs human confirmation.
- Worker startup proved one QNN delegate attachment and one delegated partition for each palm and landmark model, with successful warm invocation. Provider: `QNN HTP / NPU palm + landmarks; CPU classifier`.
- A short live worker snapshot at elapsed 92.8 seconds reported capture 7.65 FPS, inference 7.70 FPS, median inference 8.72 ms, p95 30.4 ms, RSS 273 MB, and zero dropped frames. This is one diagnostic snapshot, not a sustained or camera-to-display benchmark.
- Live browser check against the board: actual webcam image loaded; Knob connected; keyboard test drove the rendered game and selected gear 2; no JavaScript errors.
- Five Python unit tests passed: steering orientation, malformed/low-confidence hands, calibrated deadzone, encoder wraparound/gear limits, and reset rejection.
- Node physics checks passed for hand-loss pause, acceleration/speed limits, non-running lifecycle, single-collision immunity, finish, and crash states.
- Browser fixture integration passed: start, shifting, movement, manual pause, hand-loss pause/recovery, and smaller viewport rendering. Fixture tests are distinguished from physical input testing.
- Python compilation and JavaScript syntax checks passed.

The first launch encountered unavailable `/dev/video2` and `/dev/video3` devices inherited from the older installation. The setup script now discovers existing camera nodes before generating Compose device bindings. The next App Lab launch succeeded.

OpenOCD printed adapter-speed warnings while uploading. App Lab nevertheless completed the upload, and the new `highway_controls` RPC returned Knob state successfully. No system firmware or SDK was replaced.

Remaining acceptance: the operator should confirm comfortable two-hand left/right steering, Knob direction and press behavior, collision feel, and a full 3 km run on the chosen display. No sustained rendering FPS or physical end-to-end latency guarantee is made.

## 3D circuit update

- User confirmed hand detection but reported reversed steering. The board steering mapping was inverted and deployed; six control unit tests now include physical single-hand direction.
- Added a locally bundled Three.js 0.186.1 renderer and original fictional closed circuit, rider/bike meshes, 12 rivals, kerbs, stands, pit buildings, shadows, and textured asphalt.
- Physics tests passed for a three-second countdown with stationary grid, simultaneous rival launch, acceleration, collision events and timed recovery, final crash, and lap completion.
- Isolated browser integration explicitly verified successful WebGL initialization, positive lateral movement projecting screen-right, the visible countdown, rivals launching, rider/bike crash animation and particle visibility, and post-crash recovery. No JavaScript errors were captured. Test screenshots use fixture controls and are not physical visitor evidence.
- Hand loss and recovery tests also check pause behavior in the revised race UI. Game effects are arcade animations, not a rigid-body motorcycle simulation. The worker/MCU and their previously corrected steering direction were preserved during this asset-only update.

## Wrist throttle update

- Added a two-pose calibrated palm-depth angle for right-wrist throttle, live 0–100% meter, automatic gears by default, and an original Knob cruise fallback. The game no longer accelerates without throttle in wrist mode.
- Ten Python tests passed, including translation/in-plane steering invariance, fresh two-pose calibration, both twist directions, insufficient-motion rejection, relaxed release, and preventing the other hand from replacing the calibrated throttle hand.
- Node physics tests passed for zero throttle at rest, full acceleration with automatic shifting to sixth, release deceleration/downshift, and throttle scaling in manual gears.
- Browser fixture integration exercised the actual calibration controls and race UI, distinguishing synthetic angles from physical input. Real board status reported a valid wrist-angle estimate, live tracking, and connected Knob. Physical wrist usability and speed feel still require the operator's calibration and test.
- Main service restarted with the new estimator; the hand-model worker remained running. No NPU model or MCU firmware change was needed for throttle.

## Simplified one-click controls
User reported rejected twist calibration and requested no settings. Removed the two-pose requirement and hid calibration/mode controls; Start captures a relaxed wrist reference automatically. A gentle minimum riding throttle avoids a stationary bike when wrist depth is poorly estimated. Automatic gears are enabled. Browser fixture check confirmed one-click start with no calibrated wrist and hidden settings; physical throttle sensitivity remains an operator check.

## Wrist signal correction
Found mismatched landmark units: x/y were transformed out of the hand ROI while z remained in ROI coordinates. The exported z now uses the inverse ROI affine scale; classifier preprocessing is unchanged. Automatic reference waits for real samples when Start occurs without a hand, and automatic hand association tolerates handedness label flips. Removed the artificial minimum riding throttle and exposed the throttle percentage without adding settings. Thirteen Python tests passed; board worker remained QNN-accelerated and healthy after restart; live browser showed the meter with no errors. Physical wrist-response confirmation is still pending the operator test.

## Directional throttle and braking
Replaced absolute wrist-angle acceleration with a signed direction learned from three deliberate twist samples after Start. The opposite twist produces a separate proportional brake signal, which overrides throttle. Neutral coasts with gentler slowing; reverse wrist brakes harder. Fifteen Python tests passed, including both first-twist directions, reverse braking, neutral release, and output exclusivity. Physics checks confirm braking overrides accelerator input and stops faster than neutral. Browser fixture verifies the red Wrist Brake feedback. Physical feel remains for operator confirmation.

## Wrist acceleration instead of a speed target
User identified the key behavior mismatch: partial wrist input was a proportional target-speed cap (25% produced roughly 49 km/h), and neutral reduced speed. Wrist mode now integrates acceleration, retains speed in neutral, and decelerates only with reverse-wrist brake, collision, or off-track penalty. Automatic gears permit the 195 km/h arcade limit independently of wrist percentage. Regression tests confirm 25% input exceeds 140 km/h, neutral preserves speed, continued input reaches sixth/195, and reverse braking stops the bike. Legacy keyboard/cruise modes retain their old target-speed behavior.

## Persistent focus-pause fix
Live user Chrome tab was inspected: updated v7 scripts, race paused at 0 km/h, and background rendering at 1 FPS. Blur/visibility events had latched a permanent pause. v8 now suspends only while hidden and automatically resumes when visible; blur clears keys without setting manual pause. Reloaded and started the actual user game tab. Manual pause is reserved for explicit P, Knob or Pause button.
