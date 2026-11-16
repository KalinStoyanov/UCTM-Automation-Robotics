"""M20: Timing hardening regression and 60-second stability test."""

import json
import math
import time
from pathlib import Path

from src.ai.integration.m20_timing import (
    HardenedScheduler,
    IndependentWatchdog,
    M20Runtime,
    measure_long_run,
)

OUT = Path("results/m20")
OUT.mkdir(parents=True, exist_ok=True)

tests = {}


def check(name, condition):
    assert condition, f"FAIL | {name}"
    tests[name] = True
    print("PASS |", name)


def frame(t, x=0.2):
    return {
        "timestamp": t,
        "detections": [{
            "object_id": 1,
            "center_x": x,
            "confidence": 0.95,
        }],
    }


def stopped(result):
    return (
        result.action == "STOP"
        and result.linear_m_s == 0.0
        and result.angular_rad_s == 0.0
    )


# Scheduler tests
s = HardenedScheduler()
check("T01 period 50 ms", abs(s.period_s - 0.05) < 1e-12)
check("T02 first tick", not s.tick(1.0)["deadline_miss"])
check("T03 jitter 2 ms accepted",
      not s.tick(1.052)["deadline_miss"])
check("T04 jitter 8 ms rejected",
      s.tick(1.108)["deadline_miss"])
check("T05 skipped period",
      s.tick(1.25)["missed_periods"] >= 1)

# Watchdog tests
w = IndependentWatchdog(timeout_s=0.05, poll_s=0.005)
w.feed(1.0)
check("T06 watchdog before timeout", not w.check(1.03))
check("T07 watchdog after timeout", w.check(1.06))
check("T08 watchdog latch", not w.feed(1.07))
w.reset()
check("T09 watchdog reset", not w.check(1.0))

w = IndependentWatchdog(timeout_s=0.05, poll_s=0.005)
w.start()
w.feed()
time.sleep(0.08)
check("T10 independent watchdog thread", w.check())
w.stop()

# Runtime tests
r = M20Runtime()
result, timing = r.step(frame(1.0), 1.0)
check("T11 valid frame", result.action in {
    "STOP", "TURN_LEFT", "TURN_RIGHT"
})

result, timing = r.step(frame(1.05), 1.052)
check("T12 acceptable jitter", not timing["deadline_miss"])

result, timing = r.step(frame(1.10), 1.108)
check("T13 excessive jitter STOP",
      stopped(result) and result.reason == "DEADLINE_MISS")

r = M20Runtime()
result, timing = r.step(frame(1.0), 1.0)
result, timing = r.step(frame(0.90), 1.05)
check("T14 stale frame STOP",
      stopped(result) and result.reason == "STALE_FRAME")

r = M20Runtime()
r.step(frame(1.0), 1.0)
result, timing = r.step(None, 1.05)
check("T15 missing frame STOP", stopped(result))

r = M20Runtime()
r.step(frame(1.0), 1.0)
result, timing = r.step(frame(1.10), 1.05)
check("T16 future frame STOP",
      stopped(result) and result.reason == "FUTURE_FRAME")

r = M20Runtime()
r.step(frame(1.0), 1.0)
result, timing = r.step(frame(1.05), 1.05)
check("T17 command limits",
      abs(result.linear_m_s) <= 0.20
      and abs(result.angular_rad_s) <= 0.30)

# Long-run measurement
print()
print("Running 60-second offline stability measurement...")
records = measure_long_run(60.0, 20.0)

check("T18 1200 cycles", len(records) == 1200)
check("T19 finite timing measurements",
      all(math.isfinite(x["lateness_ms"]) for x in records))

lateness = [x["lateness_ms"] for x in records]
misses = sum(x["deadline_miss"] for x in records)

check("T20 no accumulated timing drift",
      abs(lateness[-1]) < 50.0)

report = {
    "stage": "M20",
    "passed": len(tests),
    "total": 20,
    "frequency_hz": 20.0,
    "period_ms": 50.0,
    "duration_s": 60.0,
    "cycles": len(records),
    "mean_lateness_ms": sum(lateness) / len(lateness),
    "max_lateness_ms": max(lateness),
    "deadline_misses": misses,
    "skipped_periods": sum(
        x["missed_periods"] for x in records
    ),
    "tests": tests,
}

with open(OUT / "report.json", "w") as f:
    json.dump(report, f, indent=2)

print()
print("M20 TIMING HARDENING & LONG-RUN STABILITY")
print(f"Cycles: {report['cycles']}")
print(f"Mean lateness: {report['mean_lateness_ms']:.3f} ms")
print(f"Maximum lateness: {report['max_lateness_ms']:.3f} ms")
print(f"Deadline misses: {report['deadline_misses']}")
print(f"Skipped periods: {report['skipped_periods']}")
print(f"M20 TESTS: {len(tests)}/20 PASS")
print("Report:", OUT / "report.json")
