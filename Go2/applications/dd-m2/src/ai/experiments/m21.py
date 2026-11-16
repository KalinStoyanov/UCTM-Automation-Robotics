"""M21: End-to-end offline AI runtime stress test."""

import json
import math
import statistics
import time
from pathlib import Path

from src.ai.integration.m20_timing import M20Runtime

OUT = Path("results/m21")
OUT.mkdir(parents=True, exist_ok=True)

FREQUENCY_HZ = 20.0
PERIOD_S = 1.0 / FREQUENCY_HZ
CYCLES = 1200
JITTER_LIMIT_S = 0.005

tests = {}


def check(name, condition):
    assert condition, f"FAIL | {name}"
    tests[name] = True
    print("PASS |", name)


def frame(timestamp, x, confidence=0.95, object_id=1):
    return {
        "timestamp": timestamp,
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


def percentile(values, p):
    ordered = sorted(values)
    index = math.ceil(p * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


runtime = M20Runtime(
    frequency_hz=FREQUENCY_HZ,
    tolerance_s=JITTER_LIMIT_S,
)

records = []
start = time.monotonic()

print("Running M21: 1200 end-to-end cycles at 20 Hz...")

for i in range(CYCLES):
    target = start + i * PERIOD_S
    remaining = target - time.monotonic()

    if remaining > 0:
        time.sleep(remaining)

    cycle_start = time.monotonic()

    # Moving target across the image, within [0.2, 0.8].
    x = 0.5 + 0.3 * math.sin(2.0 * math.pi * i / 200.0)

    # Inject missing frames and low-confidence observations.
    missing = i > 0 and i % 100 == 0
    low_confidence = i > 0 and i % 75 == 0

    raw_frame = None if missing else frame(
        timestamp=cycle_start,
        x=x,
        confidence=0.20 if low_confidence else 0.95,
    )

    processing_start = time.monotonic()

    result, timing = runtime.step(
        raw_frame,
        cycle_start,
    )

    processing_end = time.monotonic()

    processing_s = processing_end - processing_start
    release_jitter_s = cycle_start - target
    completion_s = processing_end - target

    records.append({
        "cycle": i,
        "release_jitter_ms": release_jitter_s * 1000.0,
        "processing_ms": processing_s * 1000.0,
        "completion_ms": completion_s * 1000.0,
        "deadline_miss": timing["deadline_miss"],
        "missed_periods": timing["missed_periods"],
        "missing_frame": missing,
        "low_confidence": low_confidence,
        "action": result.action,
        "reason": result.reason,
        "linear_m_s": result.linear_m_s,
        "angular_rad_s": result.angular_rad_s,
    })


release_jitter = [r["release_jitter_ms"] for r in records]
processing = [r["processing_ms"] for r in records]
completion = [r["completion_ms"] for r in records]

missing_records = [r for r in records if r["missing_frame"]]
low_conf_records = [
    r for r in records if r["low_confidence"] and not r["missing_frame"]
]

check("T01 1200 cycles", len(records) == CYCLES)

check(
    "T02 finite processing times",
    all(math.isfinite(v) and v >= 0 for v in processing),
)

check(
    "T03 finite scheduler jitter",
    all(math.isfinite(v) for v in release_jitter),
)

check(
    "T04 valid actions",
    all(
        r["action"] in {"STOP", "TURN_LEFT", "TURN_RIGHT"}
        for r in records
    ),
)

check(
    "T05 linear command bounds",
    all(abs(r["linear_m_s"]) <= 0.20 for r in records),
)

check(
    "T06 angular command bounds",
    all(abs(r["angular_rad_s"]) <= 0.30 for r in records),
)

check(
    "T07 STOP commands are zero",
    all(
        r["linear_m_s"] == 0.0 and r["angular_rad_s"] == 0.0
        for r in records if r["action"] == "STOP"
    ),
)

check(
    "T08 missing frames STOP",
    len(missing_records) > 0
    and all(r["action"] == "STOP" for r in missing_records),
)

check(
    "T09 low-confidence frames STOP",
    len(low_conf_records) > 0
    and all(r["action"] == "STOP" for r in low_conf_records),
)

check(
    "T10 no missed scheduler periods",
    sum(r["missed_periods"] for r in records) == 0,
)

check(
    "T11 no release deadline misses",
    sum(r["deadline_miss"] for r in records) == 0,
)

check(
    "T12 processing within 50 ms",
    max(processing) < 50.0,
)

check(
    "T13 completion within 50 ms",
    max(completion) < 50.0,
)

check(
    "T14 runtime recovery after missing frames",
    all(
        records[r["cycle"] + 1]["reason"] != "DEADLINE_MISS"
        for r in missing_records
        if r["cycle"] + 1 < CYCLES
    ),
)

report = {
    "stage": "M21",
    "frequency_hz": FREQUENCY_HZ,
    "period_ms": PERIOD_S * 1000.0,
    "cycles": CYCLES,
    "passed": len(tests),
    "total": 14,
    "release_jitter_mean_ms": statistics.mean(release_jitter),
    "release_jitter_max_ms": max(release_jitter),
    "processing_mean_ms": statistics.mean(processing),
    "processing_p95_ms": percentile(processing, 0.95),
    "processing_p99_ms": percentile(processing, 0.99),
    "processing_max_ms": max(processing),
    "completion_max_ms": max(completion),
    "deadline_misses": sum(r["deadline_miss"] for r in records),
    "skipped_periods": sum(r["missed_periods"] for r in records),
    "missing_frames": len(missing_records),
    "low_confidence_frames": len(low_conf_records),
    "action_counts": {
        action: sum(r["action"] == action for r in records)
        for action in ("STOP", "TURN_LEFT", "TURN_RIGHT")
    },
    "tests": tests,
}

with open(OUT / "report.json", "w") as f:
    json.dump(report, f, indent=2)

with open(OUT / "cycles.jsonl", "w") as f:
    for record in records:
        f.write(json.dumps(record) + "\n")

print()
print("M21 END-TO-END AI RUNTIME STRESS TEST")
print(f"Cycles: {CYCLES}")
print(f"Mean release jitter: {report['release_jitter_mean_ms']:.3f} ms")
print(f"Max release jitter: {report['release_jitter_max_ms']:.3f} ms")
print(f"Mean processing: {report['processing_mean_ms']:.3f} ms")
print(f"P95 processing: {report['processing_p95_ms']:.3f} ms")
print(f"P99 processing: {report['processing_p99_ms']:.3f} ms")
print(f"Max processing: {report['processing_max_ms']:.3f} ms")
print(f"Max completion: {report['completion_max_ms']:.3f} ms")
print(f"Deadline misses: {report['deadline_misses']}")
print(f"Skipped periods: {report['skipped_periods']}")
print(f"Missing frames: {report['missing_frames']}")
print(f"Low-confidence frames: {report['low_confidence_frames']}")
print(f"Action counts: {report['action_counts']}")
print(f"M21 TESTS: {len(tests)}/14 PASS")
print("Report:", OUT / "report.json")
