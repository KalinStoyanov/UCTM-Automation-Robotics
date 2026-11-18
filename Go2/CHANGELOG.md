# Changelog

## Unreleased — development after v0.25.0

### DD-M2 dual controllers (development branch dd-m2-v0.28.0-dev)

- Add a separately tracked manual controller with posture U/L/S/R/Q, movement authorization E, keyboard arrows, command queue and watchdog.
- Add an AI controller entry point that shares the manual execution path. Autonomous AI commands are explicitly disabled pending implementation and safety validation.
- Add installable DDStation short launch commands `ddm` and `dda`, with architecture and usage documentation.
- Preserve terminal auto-repeat timing measurements (0.60 s initial, 0.25 s repeat watchdog) and document unresolved key-up and communications safety limitations.
- Source reconstructed from the documented DDStation development session; confirm equality against the robot-tested local file before deployment.
- No physical validation of arrow motion after the watchdog change; no system release tag created.


- Experimental LIVE posture control with a shared WebRTC session and standing-centered transitions.
- Separate diagnostic posture controller with JSONL command/response/observation logs.
- Unified Go2/DD-M2 system versioning policy covering core, AI modules, safety, experiments and tests.
- Added build identification by Git commit and dirty working-tree status.
- LIVE physical posture tests are not yet a validated system release.


## v0.25.0 — M25 Offline Baseline

- WebRTC communication and remote control foundation.
- Command queue and STOP handling.
- Direction-dependent obstacle safety filtering.
- Offline LiDAR point-to-clearance adapter.
- Sensor validity and timeout checks.
- 207 automated tests passed.
- Live robot control disabled.

See docs/releases/v0.25.0.md for the functional baseline.
