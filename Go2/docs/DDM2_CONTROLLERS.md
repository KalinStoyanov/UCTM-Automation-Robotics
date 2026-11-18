# DD-M2 dual-controller architecture — development milestone

## Controllers

- **Base controller**: `experiments/ddm2_manual_control.py` — keyboard arrows,
  U/L/S/R poses, Q (lie and exit), E (explicit movement authorization), Space
  stop, Esc exit, SPORT commands, command queue, and keyboard watchdog.
- **AI controller**: `experiments/ddm2_ai_control.py` — runs the **same base
  controller**, with `AI_ENABLED=False` and an explicit rejection of AI-issued
  motion until independently testable perception, planning, command arbitration
  and safety blocks exist. AI motion is **not** implemented or enabled.

The AI controller imports the base controller rather than copying its control
logic. Manual input is available in both programs. Only one controller process
should connect to the robot at once.

## Short launch commands on DDStation

From `~/go2/Go2`, install once:

```sh
sh scripts/install_ddm2_commands.sh
```

Run `ddm` for manual mode and `dda` for the AI entry point (currently manual
behaviour only). Launchers live under `~/.local/bin`. Ensure this directory is
on `PATH`; restart the shell or update your shell profile if needed.
Both launchers use `~/go2/.venv/bin/python` relative to the checkout and set
`DDM2_LIVE_MANUAL=1`. Do not run both at once.

## Current validation and limitations (2026-11-18)

- U/S/L/R/Q posture behaviour was physically observed on Unitree Go2 Air
  firmware 1.1.12 using the **local DDStation** copy of the manual controller.
- Local offline suite: 207/207 tests passed. Separate mock tests confirmed
  a Move to Stop sequence for the keyboard watchdog.
- Keyboard auto-repeat first delay was observed around 0.502 s, then
  repeats around 0.029–0.046 s. Initial timeout: 0.60 s; repeating timeout:
  0.25 s. The terminal does not expose key-up; a short tap may sustain motion
  for up to the initial timeout. This is an unresolved safety limitation.
- Physical arrow-motion revalidation is **pending**, including reliable
  stop behaviour. There is no verified independent on-robot communications
  failsafe. Live motion requires a safe workspace and independent physical
  stopping capability.
- Startup StopMove and shutdown StopMove can return code -1 in lying posture.
  Interpretation is not conclusively established.
- GitHub development sources may differ from the locally tested DDStation
  working copy. Compare and re-run offline tests after deployment.
- This milestone is **development-only**, not a validated system release.

## Version control

One shared Go2 system version; see `docs/VERSIONING.md`. The
`dd-m2-v0.28.0-dev` branch represents the architectural development
milestone, not a `go2-v0.28.0` release tag. Do not create a release tag
until the full system and physical control are validated. Track future
AI blocks in separate commits and tests, retaining the base controller
as the execution path.
