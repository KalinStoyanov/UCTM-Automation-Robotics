"""M23: Final offline AI validation and regression."""

import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from src.ai.integration.m20_timing import (
    M20Runtime,
    IndependentWatchdog,
)

ROOT = Path.cwd()
OUT = ROOT / "results/m23"
OUT.mkdir(parents=True, exist_ok=True)

PYTHON = sys.executable
ENV = os.environ.copy()
ENV["PYTHONPATH"] = (
    str(ROOT / "applications/dd-m2")
    + os.pathsep + str(ROOT)
)

results = {}


def check(name, condition, detail=""):
    passed = bool(condition)
    results[name] = {
        "passed": passed,
        "detail": str(detail),
    }
    print(
        ("PASS" if passed else "FAIL")
        + " | " + name,
        flush=True,
    )


def frame(t, x=0.2, confidence=0.95, object_id=1):
    return {
        "timestamp": t,
        "detections": [{
            "object_id": object_id,
            "center_x": x,
            "confidence": confidence,
        }],
    }


def safe(result):
    if result.action not in {
        "STOP", "TURN_LEFT", "TURN_RIGHT"
    }:
        return False

    v = result.linear_m_s
    w = result.angular_rad_s

    if not all(math.isfinite(x) for x in (v, w)):
        return False

    if abs(v) > 0.20 or abs(w) > 0.30:
        return False

    if result.action == "STOP":
        return v == 0 and w == 0

    if result.action == "TURN_LEFT":
        return w < 0

    return w > 0


def runtime():
    return M20Runtime()


# Recovery and tracking
r = runtime()
a, _ = r.step(frame(1.0), 1.0)
b, _ = r.step(None, 1.05)
c, _ = r.step(frame(1.10), 1.10)
d, _ = r.step(frame(1.15), 1.15)

check(
    "R01 recovery after missing frame",
    safe(a) and b.action == "STOP"
    and safe(c) and safe(d),
)

check(
    "R02 active tracking restored",
    c.action == "TURN_LEFT"
    or d.action == "TURN_LEFT",
    f"actions={c.action},{d.action}",
)

r = runtime()
r.step(frame(1.0), 1.0)
a, _ = r.step(frame(1.05, object_id=2), 1.05)
b, _ = r.step(frame(1.10, object_id=2), 1.10)

check(
    "R03 target identity change safe",
    safe(a) and safe(b),
    f"actions={a.action},{b.action}",
)

r = runtime()
r.step(frame(1.0), 1.0)
a, _ = r.step(frame(0.8), 1.05)
b, _ = r.step(frame(1.10), 1.10)

check(
    "R04 stale frame recovery",
    a.action == "STOP" and safe(b),
)


# Timing
r = runtime()
r.step(frame(1.0), 1.0)
a, timing = r.step(frame(1.10), 1.108)

check(
    "T01 deadline miss safe",
    timing["deadline_miss"]
    and a.action == "STOP",
)

w = IndependentWatchdog(
    timeout_s=0.05,
    poll_s=0.005,
)
w.start()
w.feed()
time.sleep(0.08)

check(
    "T02 independent watchdog",
    w.check(),
)
w.stop()


# Safety
r = runtime()
commands = []

for i in range(100):
    t = 1.0 + i * 0.05
    x = 0.5 + 0.3 * math.sin(i * 0.05)
    result, _ = r.step(frame(t, x), t)
    commands.append(result)

check(
    "S01 command invariants",
    all(safe(x) for x in commands),
)

check(
    "S02 STOP zero motion",
    all(
        x.linear_m_s == 0
        and x.angular_rad_s == 0
        for x in commands
        if x.action == "STOP"
    ),
)


# Existing regression suites
suites = [
    "m13.py",
    "m14.py",
    "m15.py",
    "m16.py",
    "m17.py",
    "m18.py",
    "m19.py",
    "m20.py",
    "m21.py",
    "m22.py",
]

base = ROOT / "applications/dd-m2/src/ai/experiments"

for name in suites:
    path = base / name

    if not path.is_file():
        check("REG " + name, False, "File missing")
        continue

    try:
        completed = subprocess.run(
            [PYTHON, str(path)],
            cwd=ROOT,
            env=ENV,
            capture_output=True,
            text=True,
            timeout=150,
        )

        log = OUT / (name + ".log")
        log.write_text(
            completed.stdout + "\n" + completed.stderr,
            encoding="utf-8",
        )

        check(
            "REG " + name,
            completed.returncode == 0,
            f"exit={completed.returncode}; log={log}",
        )

    except subprocess.TimeoutExpired:
        check("REG " + name, False, "Timeout")


passed = sum(
    x["passed"] for x in results.values()
)
total = len(results)

report = {
    "stage": "M23",
    "passed": passed,
    "total": total,
    "status": (
        "PASS" if passed == total else "FAIL"
    ),
    "results": results,
}

(OUT / "report.json").write_text(
    json.dumps(report, indent=2),
    encoding="utf-8",
)

print()
print("M23 FINAL AI VALIDATION")
print(f"TESTS: {passed}/{total} PASS")
print("STATUS:", report["status"])
print("REPORT:", OUT / "report.json")

if passed != total:
    raise SystemExit(1)
