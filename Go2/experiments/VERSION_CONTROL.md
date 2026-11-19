# DD-M2 controller version-control guidance

See [the unified system policy](../docs/VERSIONING.md).

**Current integrated controller:** `Go2/go2_control/` on branch `go2-control`, including base keyboard/joystick control, AI hand gestures, camera, person following, posture transitions and STOP/deadman logic. The operator confirmed physical testing of both base and AI controllers as of 2026-11-19.

Earlier components remain in the repository as historical or experimental implementations:
- `Go2/core/control/remote_control.py` — earlier keyboard controller.
- `Go2/experiments/ddm2_posture_controller.py` — experimental posture controller.
- `Go2/experiments/ddm2_posture_logged.py` — diagnostic posture controller.

These are not the authoritative integrated web controller. They share the Go2 system version history rather than separate release numbers. The current `go2-control` branch contains `Go2/VERSION = 0.26.0-dev`; this documentation update does not issue a new release or tag.

Do not overwrite validated local source or assume `main` includes the integrated implementation. Record branch, commit SHA, firmware and test evidence for any later release. Keep runtime logs and credentials out of Git unless deliberately reviewed.
