"""M18: Sensor adapter and offline replay validation."""

import json
import math
import time
from pathlib import Path

from src.ai.perception.sensor_adapter import SensorAdapter
from src.ai.integration.m16_runtime import M16Runtime

OUT = Path("results/m18")
OUT.mkdir(parents=True, exist_ok=True)

passed = 0
tests = {}


def check(name, condition, details=None):
    global passed
    assert condition, f"FAIL | {name}: {details}"
    passed += 1
    tests[name] = {"passed": True, "details": details}
    print("PASS |", name)


def frame(t, detections):
    return {
        "timestamp": t,
        "detections": detections,
    }


def detection(object_id, x, confidence=0.95):
    return {
        "object_id": object_id,
        "center_x": x,
        "confidence": confidence,
    }


def stopped(result):
    return (
        result.action == "STOP"
        and result.linear_m_s == 0.0
        and result.angular_rad_s == 0.0
    )


# T01-T08: Sensor adapter validation
a = SensorAdapter()

o = a.convert(frame(1.0, [detection(1, 0.2)]))
check("T01 valid detection", o.object_id == 1)

o = a.convert(frame(2.0, [detection(1, 0.3)]))
check("T02 target continuity", o.object_id == 1)

o = a.convert(frame(3.0, []))
check("T03 missing target", o is None)

o = a.convert(frame(4.0, [detection(2, 0.8)]))
check("T04 new target", o.object_id == 2)

try:
    a.convert(frame(4.0, []))
    rejected = False
except ValueError:
    rejected = True
check("T05 repeated timestamp", rejected)

a.reset()
try:
    a.convert(frame(float("nan"), []))
    rejected = False
except ValueError:
    rejected = True
check("T06 NaN timestamp", rejected)

try:
    a.convert(frame(1.0, [detection(1, 1.5)]))
    rejected = False
except ValueError:
    rejected = True
check("T07 invalid coordinate", rejected)

try:
    a.convert(frame(1.0, [detection(1, 0.5, 1.5)]))
    rejected = False
except ValueError:
    rejected = True
check("T08 invalid confidence", rejected)


# T09: Multiple detections
a.reset()
o = a.convert(frame(1.0, [
    detection(1, 0.2, 0.6),
    detection(2, 0.8, 0.9),
]))
check("T09 strongest detection", o.object_id == 2)


# T10: Tracking continuity over confidence
o = a.convert(frame(2.0, [
    detection(1, 0.2, 0.99),
    detection(2, 0.7, 0.70),
]))
check("T10 preserve target ID", o.object_id == 2)


# Create a deterministic replay dataset
frames = [
    frame(1.0, [detection(1, 0.20)]),
    frame(2.0, [detection(1, 0.30)]),
    frame(3.0, [detection(1, 0.40)]),
    frame(4.0, []),
    frame(5.0, [detection(1, 0.60)]),
    frame(6.0, [detection(1, 0.70)]),
    frame(7.0, [detection(1, 0.80)]),
    frame(8.0, [detection(2, 0.20)]),
    frame(9.0, [detection(2, 0.30)]),
    frame(10.0, []),
]

DATASET = OUT / "sensor_replay.jsonl"

with open(DATASET, "w") as f:
    for item in frames:
        f.write(json.dumps(item) + "\n")


# T11-T12: End-to-end replay
adapter = SensorAdapter()
runtime = M16Runtime()

records = []
latencies_ms = []

with open(DATASET) as f:
    for line in f:
        raw = json.loads(line)

        start = time.perf_counter()

        try:
            observation = adapter.convert(raw)
            result = runtime.step(observation)
        except ValueError:
            adapter.reset()
            result = runtime.step(None)

        elapsed_ms = (
            time.perf_counter() - start
        ) * 1000.0

        latencies_ms.append(elapsed_ms)

        records.append({
            "timestamp": raw["timestamp"],
            "target_id": (
                observation.object_id
                if "observation" in locals()
                and observation is not None
                else None
            ),
            "action": result.action,
            "linear_m_s": result.linear_m_s,
            "linear_km_h": result.linear_m_s * 3.6,
            "angular_rad_s": result.angular_rad_s,
            "angular_deg_s": math.degrees(
                result.angular_rad_s
            ),
            "latency_ms": elapsed_ms,
            "reason": result.reason,
        })

check(
    "T11 replay completed",
    len(records) == len(frames),
)

check(
    "T12 safe commands",
    all(
        math.isfinite(r["linear_m_s"])
        and math.isfinite(r["angular_rad_s"])
        and abs(r["linear_m_s"]) <= 0.20
        and abs(r["angular_rad_s"]) <= 0.30
        and (
            r["action"] != "STOP"
            or (
                r["linear_m_s"] == 0.0
                and r["angular_rad_s"] == 0.0
            )
        )
        for r in records
    ),
)

report = {
    "stage": "M18",
    "passed": passed,
    "total": 12,
    "frames": len(frames),
    "missing_frames": sum(
        not f["detections"] for f in frames
    ),
    "mean_latency_ms": (
        sum(latencies_ms) / len(latencies_ms)
    ),
    "max_latency_ms": max(latencies_ms),
    "tests": tests,
    "replay": records,
}

with open(OUT / "report.json", "w") as f:
    json.dump(report, f, indent=2)

print()
print("M18 SENSOR ADAPTER & OFFLINE REPLAY")

for r in records:
    print(
        f"t={r['timestamp']:.0f} "
        f"id={r['target_id']} "
        f"action={r['action']} "
        f"linear={r['linear_m_s']:.2f} m/s "
        f"({r['linear_km_h']:.2f} km/h) "
        f"angular={r['angular_rad_s']:+.3f} rad/s "
        f"({r['angular_deg_s']:+.2f} deg/s) "
        f"latency={r['latency_ms']:.3f} ms"
    )

print()
print(
    f"Mean latency: {report['mean_latency_ms']:.3f} ms"
)
print(
    f"Maximum latency: {report['max_latency_ms']:.3f} ms"
)
print(f"M18 TESTS: {passed}/12 PASS")
print("Report:", OUT / "report.json")
