# Changelog

## v0.26.0 — Integrated Go2 Control (2026-11-19)

**Operator-reported hardware status:** basic controller and AI controller tested on the physical Unitree Go2 Air; integration considered complete for the current demonstration scope. This is a documentation and version-control record, not a claim that tests were rerun as part of this commit.

- Integrated local web controller under `go2_control/`, sharing a single LocalAP WebRTC session across video, telemetry and commands.
- Keyboard and joystick locomotion, emergency STOP, speed presets and live status.
- Automatic posture transitions: standing, balance, sitting, lying and rise-from-sit; supported in-place actions and demo sequence.
- MediaPipe hand gesture recognition and gesture-to-action mapping with consecutive-frame filtering and cooldown.
- YOLO11n object recognition and person following with target tracking, stop-on-loss and manual override.
- Controller safety: 300 ms deadman, server velocity limits, browser/key-release stop and restricted action whitelist.
- Unit tests are present under `go2_control/controller/tests/`; their latest execution result is **not recorded here**.
- Release version: `0.26.0`. Source release record: `docs/releases/v0.26.0.md`. Annotated Git tag pending.
- Deployment instructions in the integrated controller README describe macOS; Linux/WSL instructions for DDStation should be validated before publication.

### Other unreleased experiments

- Experimental LIVE posture control and JSONL diagnostic logging.
- Git SHA and working-tree status reporting; unified Go2/DD-M2 versioning.

## v0.25.0 — M25 Offline Baseline

- WebRTC communication and remote control foundation.
- Command queue and STOP handling.
- Direction-dependent obstacle safety filtering.
- Offline LiDAR point-to-clearance adapter.
- Sensor validity and timeout checks.
- 207 automated tests passed.
- Live robot control disabled in this historical baseline.

See [docs/releases/v0.25.0.md](docs/releases/v0.25.0.md).
