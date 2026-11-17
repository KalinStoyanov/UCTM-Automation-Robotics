# Unified Go2 / DD-M2 software versioning

**Scope:** every software component under `Go2/` shares ONE system-level version.

This includes:
- `core/`: WebRTC transport, robot commands, posture and motion control, safety, sensor adapters.
- `applications/`: DD-M2 AI applications and integration.
- `experiments/`: posture and diagnostic controllers, trial implementations.
- `tests/`, configuration, documentation and scripts that affect system behavior.

## Source of truth

- `Go2/VERSION`: the most recently **released** system version (currently `0.25.0`).
- `Go2/CHANGELOG.md`: released changes and the unreleased change set.
- Git commit SHA: the **exact software snapshot**, including all controllers and other components.
- Annotated Git tag `go2-vMAJOR.MINOR.PATCH` on a verified release commit; use the previously established legacy tag when applicable and do not move existing tags.
- `Go2/tools/version_info.py`: report the current release baseline, commit SHA, and dirty working-tree state.

A commit after a tagged release is **development code**. Its version is displayed as `<VERSION>+dev.<shortsha>` (and `.dirty` if local edits exist). This is a descriptive build ID, not a new SemVer release.

## Version change rules (Semantic Versioning)

- MAJOR: incompatible software/API/control contract change.
- MINOR: backward-compatible new capability or major functional milestone.
- PATCH: backward-compatible bug or safety fix without API break.
- A tested milestone is released only after explicit release validation. An experimental controller being committed does not itself create a release.
- Increment the single `Go2/VERSION` file **once per Go2 release**, not once per subsystem, and never silently overwrite a released tag.

## Commit and release workflow

1. Keep all authoritative source files inside `Go2/` and under Git; `/tmp` scripts are scratch copies only.
2. From DDStation: `git status`, `git pull --ff-only` (resolve local differences first), and inspect `git diff`. Avoid overwriting robot-tested local edits.
3. Run focused and regression tests against the entire system. Record test totals and hardware validation separately. Never describe offline tests as physical verification.
4. Commit each substantive change with a descriptive scope, e.g. `go2(posture): log state transitions` or `go2(webrtc): handle reconnect failure`.
5. For release: update `VERSION`, `CHANGELOG.md`, and `docs/releases/vX.Y.Z.md`; record safety limitations, tested firmware, hardware and commit SHA.
6. Commit release files, then create an annotated tag `go2-vX.Y.Z` pointing to that same commit and push the commit and tag.
7. Deployment and bug reports always record **version + full commit SHA + clean/dirty state**. A change anywhere under `Go2/` changes the build SHA.
8. Check out a release tag or a specific commit to reconstruct all source components together. Restore environments and dependencies according to that snapshot's documented requirements.

## Runtime data

Do not commit robot telemetry, raw JSONL diagnostic sessions, model weights, credentials, virtual environments or local backups by default. The existing `.gitignore` excludes `results/`, environment files and model artifacts. Share selected scrubbed logs separately for diagnostics.

## Safety

A WebRTC API status 0 records command acceptance, not observed completion. Posture state inferred from previous commands must be labeled as such. Keep physical safety verification, independent STOP requirements and firmware compatibility distinct from source release numbers.

## Example usage

From DDStation inside `~/go2/Go2`:

```bash
python tools/version_info.py
git status --short
git log -1 --format='%H %s'
```

The historical `v0.25.0` offline baseline remains documented. Recent LIVE posture experiments are **unreleased** until a validated new Go2 system release is explicitly declared.
