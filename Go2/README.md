# Unitree Go2 Air / DD-M2

**Current integrated controller:** [go2_control](go2_control/README.md), branch `go2-control`. **Status as reported by the operator on 2026-11-19:** physical integration complete; the base and AI controllers have been tested on the robot. The GitHub snapshot contains the integrated implementation. This statement records operator validation; it is not a newly executed regression or hardware test.

## Working system

- Unitree Go2 Air, firmware 1.1.12, LocalAP `192.168.12.1`.
- One shared WebRTC connection for commands, telemetry and robot camera video.
- Local browser controller with keyboard, joysticks, posture actions, tricks, demonstration sequence, live video and operator log.
- Keyboard: W/S or Up/Down forward/back; A/D lateral; Q/E or Left/Right turning; Space STOP. Keyboard handling uses physical key codes.
- AI hand gestures using MediaPipe: Thumb_Up/Hello, Closed_Fist/Sit, Open_Palm/RiseSit, Victory/Stretch, Pointing_Up/StandUp, Thumb_Down/StandDown, ILoveYou/FingerHeart. Gesture actions pass through the posture-transition logic.
- YOLO11n object overlays and person-following control with manual override and Open_Palm follow cancellation.
- Automatic posture transition chains; movement only after the appropriate balance step.
- Safety mechanisms implemented in the controller: velocity caps, 300 ms deadman, key release and browser disconnect stop, STOP latch/cancellation and action whitelist.

The detailed controls, configuration, startup and hardware checklist are maintained in [go2_control/README.md](go2_control/README.md). That README currently describes a macOS Python 3.12 startup environment; do not treat its Mac-specific setup instructions as verified Linux/WSL instructions for DDStation.

## Version control

The current **authoritative integrated code snapshot** is on the `go2-control` branch, not `main`. The branch's `Go2/VERSION` is `0.26.0`, a release version. The historical offline release `v0.25.0` remains a separate baseline. See [v0.26.0 release record](docs/releases/v0.26.0.md).

See [docs/VERSIONING.md](docs/VERSIONING.md) and [CHANGELOG.md](CHANGELOG.md). A new release tag and finalized version number require an explicit release decision; no existing tag is moved.
