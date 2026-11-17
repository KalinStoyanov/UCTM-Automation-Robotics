# Changelog

## Unreleased — development after v0.25.0

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
