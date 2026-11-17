#!/usr/bin/env python3
"""Report one unified Go2 system version and exact Git code snapshot."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def main():
    release = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    sha = git("rev-parse", "HEAD")
    changes = git("status", "--porcelain", "--untracked-files=normal", "--", "Go2")
    # Repository layout may be Go2/ inside the superproject. Git -C resolves
    # the root; use Git's own --show-prefix to restrict status consistently.
    prefix = git("rev-parse", "--show-prefix") or ""
    changes = git("status", "--porcelain", "--untracked-files=normal", "--", ".")
    dirty = bool(changes) if changes is not None else None
    tags = git("tag", "--points-at", "HEAD") or ""
    released_here = any(
        tag in {f"go2-v{release}", f"v{release}"}
        for tag in tags.splitlines()
    )
    build = release if released_here else (
        f"{release}+dev.{sha[:12]}" if sha else f"{release}+untracked"
    )
    if dirty:
        build += ".dirty"
    report = {
        "system": "Go2/DD-M2",
        "release_baseline": release,
        "build": build,
        "git_commit": sha,
        "working_tree_dirty": dirty,
        "release_tag_at_head": released_here,
        "project_prefix": prefix,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
