"""M22: Offline fault injection and recovery validation."""

import json
import math
from pathlib import Path
from unittest.mock import patch

from src.ai.integration.m20_timing import M20Runtime

OUT = Path("results/m22")
OUT.mkdir(parents=True, exist_ok=True)

tests = {}


def check(name, condition, details=None):
    ok = bool(condition)
    tests[name] = {
        "passed": ok,
        "details": details,
    }
    print(("PASS" if ok else "FAIL") + " | " + name)


def frame(t, x=0.2, confidence=0.95, object_id=1):
    return {
        "timestamp": t,
        "detections": [{
            "object_id": object_id,
            "center_x": x,
            "confidence": confidence,
        }],
    }


def stopped(result):
    return (
        result.action == "STOP"
        and result.linear_m_s == 0.0
        and result.angular_rad_s == 0.0
    )


def safe_result(result):
    if result.action not in {"STOP", "TURN_LEFT", "TURN_RIGHT"}:
        return False

    if not all(math.isfinite(v) for v in (
        result.linear_m_s,
        result.angular_rad_s,
    )):
        return False

    if abs(result.linear_m_s) > 0.20:
        return False

    if abs(result.angular_rad_s) > 0.30:
        return False

    if result.action == "STOP":
        return stopped(result)

    if result.action == "TURN_LEFT":
        return result.angular_rad_s < 0

    if result.action == "TURN_RIGHT":
        return result.angular_rad_s > 0

    return False


def fresh_runtime():
    return M20Runtime(
        frequency_hz=20.0,
        tolerance_s=0.005,
        max_frame_age_s=0.150,
    )


def run_case(name, injected, expected_reason=None):
    runtime = fresh_runtime()
    result, timing = runtime.step(injected, 1.0)

    condition = stopped(result)

    if expected_reason is not None:
        condition = (
            condition
            and result.reason == expected_reason
        )

    check(name, condition, result.reason)


# F1: Invalid input types
run_case("T01 None frame", None, "NO_FRAME")
run_case("T02 integer frame", 123, "INVALID_FRAME")
run_case("T03 string frame", "invalid", "INVALID_FRAME")
run_case("T04 empty dictionary", {}, "INVALID_TIMESTAMP")
run_case("T05 NaN timestamp",
         frame(float("nan")), "INVALID_TIMESTAMP")
run_case("T06 Infinity timestamp",
         frame(float("inf")), "INVALID_TIMESTAMP")
run_case("T07 boolean timestamp",
         frame(True), "INVALID_TIMESTAMP")

# F2: Invalid detections
invalid_detections = [
    ("T08 missing detections", {"timestamp": 1.0}),
    ("T09 detections None",
     {"timestamp": 1.0, "detections": None}),
    ("T10 detections string",
     {"timestamp": 1.0, "detections": "bad"}),
    ("T11 invalid center",
     frame(1.0, x=float("nan"))),
    ("T12 center outside image",
     frame(1.0, x=1.5)),
    ("T13 invalid confidence",
     frame(1.0, confidence=float("inf"))),
    ("T14 invalid object ID",
     frame(1.0, object_id="robot")),
]

for name, injected in invalid_detections:
    runtime = fresh_runtime()

    try:
        result, timing = runtime.step(injected, 1.0)
        check(name, stopped(result), result.reason)
    except Exception as exc:
        check(name, False, type(exc).__name__)


# F3: Timing failures
runtime = fresh_runtime()
runtime.step(frame(1.0), 1.0)
result, timing = runtime.step(frame(0.80), 1.05)
check("T15 stale frame",
      stopped(result) and result.reason == "STALE_FRAME")

runtime = fresh_runtime()
runtime.step(frame(1.0), 1.0)
result, timing = runtime.step(frame(1.10), 1.05)
check("T16 future frame",
      stopped(result) and result.reason == "FUTURE_FRAME")

runtime = fresh_runtime()
runtime.step(frame(1.0), 1.0)
result, timing = runtime.step(frame(1.10), 1.108)
check("T17 excessive jitter",
      stopped(result) and result.reason == "DEADLINE_MISS")


# F4: Injected exceptions
runtime = fresh_runtime()

with patch.object(
    runtime.adapter,
    "convert",
    side_effect=ValueError("Injected adapter failure"),
):
    result, timing = runtime.step(frame(1.0), 1.0)

check("T18 adapter exception",
      stopped(result) and result.reason == "RUNTIME_FAILURE")

runtime = fresh_runtime()

with patch.object(
    runtime.ai,
    "step",
    side_effect=ValueError("Injected AI failure"),
):
    result, timing = runtime.step(frame(1.0), 1.0)

check("T19 AI exception",
      stopped(result) and result.reason == "RUNTIME_FAILURE")


# F5: Recovery after failures
runtime = fresh_runtime()

result1, _ = runtime.step(frame(1.0), 1.0)
result2, _ = runtime.step(None, 1.05)
result3, _ = runtime.step(frame(1.10), 1.10)

check(
    "T20 recovery after missing frame",
    safe_result(result1)
    and stopped(result2)
    and safe_result(result3)
    and result3.reason != "DEADLINE_MISS",
)

runtime = fresh_runtime()

runtime.step(frame(1.0), 1.0)
result2, _ = runtime.step(frame(0.80), 1.05)
result3, _ = runtime.step(frame(1.10), 1.10)

check(
    "T21 recovery after stale frame",
    stopped(result2)
    and safe_result(result3)
    and result3.reason != "DEADLINE_MISS",
)

runtime = fresh_runtime()

runtime.step(frame(1.0), 1.0)
result2, _ = runtime.step(frame(1.10), 1.108)
result3, _ = runtime.step(frame(1.15), 1.15)

check(
    "T22 recovery after deadline miss",
    stopped(result2)
    and safe_result(result3)
    and result3.reason != "DEADLINE_MISS",
)


# F6: Safety invariants
runtime = fresh_runtime()
results = []

for i in range(20):
    now = 1.0 + i * 0.05
    x = 0.5 + 0.3 * math.sin(i * 0.2)
    result, _ = runtime.step(frame(now, x), now)
    results.append(result)

check(
    "T23 all commands within limits",
    all(safe_result(r) for r in results),
)

check(
    "T24 STOP always zero",
    all(stopped(r) for r in results if r.action == "STOP"),
)

check(
    "T25 valid action vocabulary",
    all(
        r.action in {"STOP", "TURN_LEFT", "TURN_RIGHT"}
        for r in results
    ),
)


passed = sum(t["passed"] for t in tests.values())
total = len(tests)

report = {
    "stage": "M22",
    "passed": passed,
    "total": total,
    "tests": tests,
    "status": "PASS" if passed == total else "FAIL",
}

with open(OUT / "report.json", "w") as f:
    json.dump(report, f, indent=2)

print()
print("M22 FAULT INJECTION & RECOVERY VALIDATION")
print(f"M22 TESTS: {passed}/{total} PASS")
print("Status:", report["status"])
print("Report:", OUT / "report.json")

if passed != total:
    raise SystemExit(1)
