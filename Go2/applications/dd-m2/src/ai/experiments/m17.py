"""M17: Offline runtime hardening and regression checks."""

import json
import math
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from src.ai.contracts.m12 import Observation, AIResult
from src.ai.integration.m16_runtime import M16Runtime

OUT = Path("results/m17")
OUT.mkdir(parents=True, exist_ok=True)

MODEL = Path("results/m13/neural_policy.npz")
assert MODEL.is_file(), "M13 model missing"

passed = 0
failed = 0
tests = {}


def check(name, condition, details=""):
    global passed, failed
    ok = bool(condition)
    tests[name] = {"passed": ok, "details": details}
    print(("PASS" if ok else "FAIL") + " | " + name)
    if ok:
        passed += 1
    else:
        failed += 1


def obs(x=0.2, t=1.0, confidence=0.95, object_id=1):
    return Observation(
        object_id=object_id,
        center_x=x,
        timestamp=t,
        confidence=confidence,
    )


def stopped(result):
    return (
        result.action == "STOP"
        and result.linear_m_s == 0.0
        and result.angular_rad_s == 0.0
    )


def runtime():
    return M16Runtime(model_path=MODEL)


def bad_result(
    action="TURN_RIGHT",
    linear=0.0,
    angular=0.15,
):
    return AIResult(
        action=action,
        linear_m_s=linear,
        angular_rad_s=angular,
        confidence=0.95,
        reason="Injected test result",
    )


# T01-T07: Inputs and tracking
r = runtime()
check("T01 initial STOP", stopped(r.last_result))

check("T02 missing observation", stopped(r.step(None)))
check("T03 invalid input type", stopped(r.step({"x": 0.2})))
check("T04 low confidence", stopped(r.step(obs(confidence=0.1))))

r = runtime()
r.step(obs(t=1.0))
check(
    "T05 repeated timestamp",
    stopped(r.step(obs(x=0.3, t=1.0))),
)

r = runtime()
r.step(obs(object_id=1))
check(
    "T06 identity change",
    stopped(r.step(obs(object_id=2, t=2.0))),
)

r = runtime()
r.step(obs())
r.step(None)
r.step(obs(x=0.8, t=2.0))
check("T07 recovery", r.active_id == 1)


# T08-T12: AI component exceptions
components = [
    ("T08 B2 exception", "world", "update"),
    ("T09 B3 exception", "decision", "predict"),
    ("T10 B4 exception", "learning", "predict"),
    ("T11 B5 exception", "planner", "plan"),
    ("T12 B6 exception", "coordinator", "coordinate"),
]

for name, component, method in components:
    r = runtime()
    target = getattr(r, component)
    try:
        with patch.object(
            target,
            method,
            side_effect=ValueError("Injected failure"),
        ):
            result = r.step(obs())
        check(name, stopped(result))
    except Exception as exc:
        check(name, False, repr(exc))


# T13-T19: Invalid command injection
invalid_commands = [
    ("T13 NaN angular", bad_result(angular=float("nan"))),
    ("T14 Infinity angular", bad_result(angular=float("inf"))),
    ("T15 excessive angular", bad_result(angular=0.31)),
    ("T16 excessive linear", bad_result(linear=0.21)),
    ("T17 wrong turn direction", bad_result(
        action="TURN_LEFT", angular=0.15
    )),
    ("T18 moving STOP", bad_result(
        action="STOP", angular=0.15
    )),
    ("T19 unknown action", bad_result(
        action="FLY", angular=0.15
    )),
]

for name, injected in invalid_commands:
    r = runtime()
    with patch.object(
        r.coordinator,
        "coordinate",
        return_value=injected,
    ):
        result = r.step(obs())
    check(name, stopped(result))


# T20-T21: Limits and normal operation
r = runtime()
commands = [
    r.step(obs(x=x, t=float(i + 1)))
    for i, x in enumerate(
        [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    )
]

check(
    "T20 normal runtime",
    len(commands) == 7
    and all(c.action in {
        "STOP", "TURN_LEFT", "TURN_RIGHT"
    } for c in commands),
)

check(
    "T21 command limits",
    all(
        math.isfinite(c.linear_m_s)
        and math.isfinite(c.angular_rad_s)
        and abs(c.linear_m_s) <= 0.20
        and abs(c.angular_rad_s) <= 0.30
        for c in commands
    ),
)


# T22-T25: Regression of existing experiment scripts
scripts = [
    ("T22 M13 regression",
     "applications/dd-m2/src/ai/experiments/m13.py"),
    ("T23 M14 regression",
     "applications/dd-m2/src/ai/experiments/m14.py"),
    ("T24 M15 regression",
     "applications/dd-m2/src/ai/experiments/m15.py"),
    ("T25 M16 regression",
     "applications/dd-m2/src/ai/experiments/m16.py"),
]

for name, script in scripts:
    completed = subprocess.run(
        [sys.executable, script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    check(
        name,
        completed.returncode == 0,
        completed.stderr[-500:] if completed.returncode else "",
    )


report = {
    "stage": "M17",
    "passed": passed,
    "failed": failed,
    "total": passed + failed,
    "tests": tests,
}

with open(OUT / "report.json", "w") as f:
    json.dump(report, f, indent=2)

print()
print("M17 REGRESSION & RUNTIME HARDENING")
print(f"TESTS: {passed}/{passed + failed} PASS")
print(f"FAILED: {failed}")
print("Report:", OUT / "report.json")

if failed:
    sys.exit(1)
