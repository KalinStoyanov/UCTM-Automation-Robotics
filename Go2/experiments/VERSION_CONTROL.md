# DD-M2 controller version-control policy

All DD-M2 controllers are first-class source files in GitHub and should be committed with each functional change.

## Tracked controllers

- `Go2/core/control/remote_control.py` — main keyboard motion controller (existing repository implementation).
- `Go2/experiments/ddm2_posture_controller.py` — experimental posture controller v3 (U/L/S/R/Q).
- `Go2/experiments/ddm2_posture_logged.py` — experimental posture controller with JSONL command/API/physical-observation logging.

## Development rules

1. Before editing, pull/review the current GitHub version; keep a single canonical path for each controller.
2. Modify existing tracked paths rather than creating untracked `/tmp`-only revisions.
3. Run Python compilation and relevant local regression tests before each commit; label hardware-only validation separately from offline testing.
4. Commit every behavior change with a descriptive message, especially command routing, transitions, STOP and shutdown behavior.
5. Preserve an accessible commit history; use Git tags for tested hardware milestones (not automatic release declarations).
6. Keep experimental controllers separate from the main controller until deliberately integrated and tested.
7. Store runtime logs under `Go2/results/` locally and share selected redacted log files for diagnosis; do not automatically commit raw runtime telemetry.
8. Use `git status`, `git diff`, `git add`, `git commit`, `git push` to synchronize local DDStation edits with the repository. GitHub-side edits do not automatically update files already on DDStation.

## Safety and state semantics

The posture controllers are experimental LIVE command clients. An API response code 0 means accepted, not necessarily physically completed. Locally tracked pose is inferred, not direct telemetry. `Q` attempts to lie down before disconnect, but a command failure or link loss can prevent that state being reached. An independent emergency-stop method has not been verified for this platform.

## Running from project root

```bash
PYTHONPATH=. python Go2/experiments/ddm2_posture_controller.py  # if at repository top level
```

Within the Go2 directory:

```bash
PYTHONPATH=. python experiments/ddm2_posture_controller.py
PYTHONPATH=. python -u experiments/ddm2_posture_logged.py
```
