"""M16 offline integrated runtime tests."""

import json
import math
from pathlib import Path

from src.ai.contracts.m12 import Observation
from src.ai.integration.m16_runtime import M16Runtime

OUT = Path("results/m16")
OUT.mkdir(parents=True, exist_ok=True)

passed = 0
tests = {}


def check(name, condition, details=None):
    global passed
    assert condition, f"FAIL | {name}: {details}"
    passed += 1
    tests[name] = {"passed": True, "details": details}
    print("PASS |", name)


def obs(x, t, confidence=0.95, object_id=1):
    return Observation(
        object_id=object_id,
        center_x=x,
        timestamp=t,
        confidence=confidence,
    )


runtime = M16Runtime()

# 1. Initial state
check("T1 initial STOP", runtime.last_result.action == "STOP")

# 2. Normal processing
r = runtime.step(obs(0.20, 1.0))
check("T2 valid observation", r.action in {
    "STOP", "TURN_LEFT", "TURN_RIGHT"
})

# 3. Temporal processing
r = runtime.step(obs(0.30, 2.0))
check("T3 temporal prediction", runtime.previous is not None)

# 4. Missing target
r = runtime.step(None)
check(
    "T4 missing target STOP",
    r.action == "STOP"
    and r.linear_m_s == 0.0
    and r.angular_rad_s == 0.0
    and runtime.active_id is None,
)

# 5. Recovery
r = runtime.step(obs(0.80, 3.0))
check("T5 recovery", runtime.active_id == 1)

# 6. Identity change
r = runtime.step(obs(0.20, 4.0, object_id=2))
check(
    "T6 identity change STOP",
    r.action == "STOP"
    and runtime.active_id is None,
)

# 7. Low confidence
r = runtime.step(obs(0.80, 5.0, confidence=0.10))
check("T7 low-confidence STOP", r.action == "STOP")

# 8. Invalid timestamp
runtime.step(obs(0.30, 6.0))
r = runtime.step(obs(0.40, 6.0))
check(
    "T8 invalid timestamp STOP",
    r.action == "STOP"
    and runtime.active_id is None,
)

# 9. Invalid input
r = runtime.step({"center_x": 0.5})
check("T9 invalid input STOP", r.action == "STOP")

# 10. Continuous command limits
runtime.reset_tracking()
safe = True
records = []

for i, x in enumerate(
    [0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]
):
    r = runtime.step(obs(x, float(i + 10)))

    valid = (
        abs(r.linear_m_s) <= 0.20
        and abs(r.angular_rad_s) <= 0.30
        and r.action in {"STOP", "TURN_LEFT", "TURN_RIGHT"}
    )
    safe = safe and valid

    records.append({
        "x": x,
        "action": r.action,
        "linear_m_s": r.linear_m_s,
        "linear_km_h": r.linear_m_s * 3.6,
        "angular_rad_s": r.angular_rad_s,
        "angular_deg_s": math.degrees(r.angular_rad_s),
        "reason": r.reason,
    })

check("T10 continuous safety", safe, records)

report = {
    "stage": "M16",
    "passed": passed,
    "total": 10,
    "tests": tests,
    "trajectory": records,
}

with open(OUT / "report.json", "w") as f:
    json.dump(report, f, indent=2)

print()
print("M16 INTEGRATED AI RUNTIME")
for item in records:
    print(
        f"x={item['x']:.2f} "
        f"action={item['action']} "
        f"linear={item['linear_m_s']:.2f} m/s "
        f"({item['linear_km_h']:.2f} km/h) "
        f"angular={item['angular_rad_s']:+.3f} rad/s "
        f"({item['angular_deg_s']:+.2f} deg/s)"
    )

print()
print(f"M16 TESTS: {passed}/10 PASS")
print("Report:", OUT / "report.json")
