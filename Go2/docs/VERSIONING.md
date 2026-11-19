# Unified Go2 / DD-M2 version control

All components under `Go2/`, including `go2_control/`, `core/`, `applications/`, `experiments/`, tests, models and configuration, belong to **one software system**. The exact Git commit is the reproducible source snapshot.

## Current authoritative implementation (2026-11-19)

- **Integrated operational implementation:** branch `go2-control`, directory `Go2/go2_control/`.
- **Release version in this branch:** `Go2/VERSION = 0.26.0`.
- **Previous offline release:** `v0.25.0` (M25, 207 tests).
- **Hardware validation:** the operator reports the base and AI controllers tested on the real Go2 Air, and the integration complete. This is operator-reported validation, separate from automated regression evidence.
- **Release status:** integrated v0.26.0 source release; annotated Git tag pending. No tag or release number has been invented or advanced.

**Important:** the default `main` branch may lag behind `go2-control`. Do not infer current operational functionality from `main` alone. Keep the validated integrated controller unchanged when updating documentation.

## Version and snapshot rules

1. Use the Git commit SHA plus branch and clean/dirty status to identify the exact implementation. Record the physical robot firmware and runtime platform separately.
2. `Go2/VERSION` identifies the branch's version string. A `-dev` suffix indicates development; do not represent it as a finalized release.
3. MAJOR: incompatible control/API change; MINOR: backward-compatible capability; PATCH: backward-compatible fix. A new release is declared only after explicit validation and approval.
4. For an approved release, update `Go2/VERSION`, `Go2/CHANGELOG.md`, and a new `docs/releases/vX.Y.Z.md`; commit together and create a new annotated `go2-vX.Y.Z` tag. Never move existing tags.
5. Keep historical offline test results distinct from operator-observed hardware tests and from untested capabilities.
6. Do not overwrite robot-tested source or perform destructive merges/resets when synchronizing `go2-control` and `main`.

## Reproduction

From the repository root, inspect `git status --short`, `git log -1 --format='%H %s'`, and `Go2/VERSION`. The integrated controller's instructions and tests are in `Go2/go2_control/README.md`.

A command acknowledgment confirms acceptance by the robot API, not necessarily completed physical motion. Safety verification and supervised hardware tests remain distinct from software release numbering.
