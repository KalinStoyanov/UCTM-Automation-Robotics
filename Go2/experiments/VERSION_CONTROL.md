# DD-M2 controller version-control guidance

The authoritative versioning policy for the **entire Go2/DD-M2 software system** is [`Go2/docs/VERSIONING.md`](../docs/VERSIONING.md).

The main motion controller, experimental posture controllers, AI modules, communications, safety logic, configurations and tests all share **one system release version** from `Go2/VERSION` and one Git commit snapshot. Controllers do not have independent release versions.

Controller files tracked in the same repository:

- `Go2/core/control/remote_control.py` — main keyboard motion controller.
- `Go2/experiments/ddm2_posture_controller.py` — experimental posture controller.
- `Go2/experiments/ddm2_posture_logged.py` — diagnostic posture controller.
- `Go2/experiments/ddm2_manual_control.py` — manual base controller (DDStation command `ddm`).
- `Go2/experiments/ddm2_ai_control.py` — AI controller entry point sharing the base controller; autonomous AI motion currently disabled (`dda`).

Each controller change is committed to the same Git history. Experimental implementation descriptions such as "v3" are internal design iterations, **not** system release numbers. Runtime diagnostic logs under `results/` remain local unless deliberately shared for analysis.

Local `/tmp/` copies on DDStation are **not** version-controlled. Move validated changes to these canonical repository paths and commit them. GitHub edits do not automatically update DDStation.

The development branch `dd-m2-v0.28.0-dev` records the two-controller architecture, but is **not** a validated v0.28.0 release. `Go2/VERSION` and published release tags are unchanged pending full release qualification. See `Go2/docs/DDM2_CONTROLLERS.md` for setup, limitations and validation scope.
