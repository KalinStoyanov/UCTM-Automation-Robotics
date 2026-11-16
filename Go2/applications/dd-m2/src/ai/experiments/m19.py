"""M19: Scheduling, watchdog and offline runtime tests."""

import json
import math
from pathlib import Path

from src.ai.integration.m19_scheduler import (
    Watchdog,
    PeriodicScheduler,
    M19Runtime,
    run_periodic_measurement,
)

OUT = Path("results/m19")
OUT.mkdir(parents=True, exist_ok=True)

passed = 0
tests = {}


def check(name, condition, details=None):
    global passed
    assert condition, f"FAIL | {name}: {details}"
    passed += 1
    tests[name] = {"passed": True, "details": details}
    print("PASS |", name)


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


# T01-T05: Scheduler
s = PeriodicScheduler(20.0)

check("T01 period 50 ms", abs(s.period_s - 0.05) < 1e-12)

t = s.tick(1.0)
check("T02 first tick", not t["deadline_miss"])

t = s.tick(1.05)
check("T03 on-time tick", not t["deadline_miss"])

t = s.tick(1.12)
check(
    "T04 late tick",
    t["deadline_miss"] and t["missed_periods"] == 0,
)

t = s.tick(1.25)
check(
    "T05 missed periods",
    t["missed_periods"] >= 1,
)


# T06-T10: Watchdog
w = Watchdog()

check("T06 fresh frame", w.check(1.0, 0.95) is None)
check("T07 stale frame", w.check(1.0, 0.80) == "STALE_FRAME")
check("T08 future frame", w.check(1.0, 1.01) == "FUTURE_FRAME")

w.feed(1.0)
check("T09 watchdog active", w.check(1.10) is None)
check(
    "T10 watchdog timeout",
    w.check(1.25) == "WATCHDOG_TIMEOUT",
)


# T11-T16: Integrated runtime
r = M19Runtime()

result, timing = r.step(frame(1.0), 1.0)
check(
    "T11 valid runtime frame",
    result.action in {"STOP", "TURN_LEFT", "TURN_RIGHT"},
)

result, timing = r.step(None, 1.05)
check("T12 missing frame STOP", stopped(result))

result, timing = r.step(frame(1.10), 1.10)
check(
    "T13 recovery",
    result.action in {"STOP", "TURN_LEFT", "TURN_RIGHT"},
)

result, timing = r.step(frame(1.15), 1.20)
check(
    "T14 deadline miss STOP",
    stopped(result) and result.reason == "DEADLINE_MISS",
)

r = M19Runtime()
r.step(frame(1.0), 1.0)

result, timing = r.step(frame(1.05), 1.25)
check(
    "T15 delayed frame STOP",
    stopped(result) and result.reason == "DEADLINE_MISS",
)

r = M19Runtime()
r.step(frame(1.0), 1.0)

result, timing = r.step(frame(1.05), 1.05)
check(
    "T16 command bounds",
    abs(result.linear_m_s) <= 0.20
    and abs(result.angular_rad_s) <= 0.30,
)


# T17-T18: Real scheduler measurement
records = run_periodic_measurement(
    cycles=20,
    frequency_hz=20.0,
)

check("T17 measured 20 cycles", len(records) == 20)

check(
    "T18 finite jitter",
    all(
        math.isfinite(x["lateness_ms"])
        for x in records
    ),
)

lateness = [x["lateness_ms"] for x in records]

report = {
    "stage": "M19",
    "passed": passed,
    "total": 18,
    "frequency_hz": 20,
    "period_ms": 50,
    "mean_lateness_ms": sum(lateness) / len(lateness),
    "max_lateness_ms": max(lateness),
    "missed_periods": sum(
        x["missed_periods"] for x in records
    ),
    "tests": tests,
    "scheduler_measurements": records,
}

with open(OUT / "report.json", "w") as f:
    json.dump(report, f, indent=2)

print()
print("M19 REAL-TIME SCHEDULING & WATCHDOG")
print("Frequency: 20 Hz")
print("Period: 50 ms")
print(
    f"Mean lateness: "
    f"{report['mean_lateness_ms']:.3f} ms"
)
print(
    f"Maximum lateness: "
    f"{report['max_lateness_ms']:.3f} ms"
)
print(f"Missed periods: {report['missed_periods']}")
print(f"M19 TESTS: {passed}/18 PASS")
print("Report:", OUT / "report.json")
