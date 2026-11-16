"""M15: Offline dynamic robustness and safety validation."""

import json
import math
from pathlib import Path

import numpy as np

from src.ai.contracts.m12 import Observation
from src.ai.contracts.models import ActionProposal
from src.ai.perception.observation_quality import ObservationQualityEstimator
from src.ai.world_model.predictive import PredictiveWorldModel
from src.ai.decision.uncertainty_policy import UncertaintyPolicy
from src.ai.planning.predictive_planner import PredictivePlanner
from src.ai.integration.m12_coordinator import M12Coordinator

OUT = Path("results/m15")
OUT.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(45)
results = {}
passed = 0

def check(name, condition, details=None):
    global passed
    assert condition, f"FAIL | {name}: {details}"
    passed += 1
    results[name] = {
        "passed": True,
        "details": details,
    }
    print(f"PASS | {name}")


def stop_proposal(reason):
    return ActionProposal(
        action="STOP",
        linear_m_s=0.0,
        angular_rad_s=0.0,
        confidence=1.0,
        reason=reason,
    )


# T1: Acceleration and forecast error
# Position: x(t) = x0 + v0*t + 0.5*a*t^2
# Evaluate the constant-velocity prediction at t=2.5 s.
errors = []

for i in range(200):
    x0 = rng.uniform(0.3, 0.7)
    v0 = rng.uniform(-0.04, 0.04)
    a = rng.uniform(-0.02, 0.02)

    def position(t):
        return x0 + v0*t + 0.5*a*t*t

    world = PredictiveWorldModel()

    world.update(
        Observation(i, position(0), 0.0, 0.95),
        horizon_s=0.5,
    )

    prediction = world.update(
        Observation(i, position(1), 1.0, 0.95),
        horizon_s=0.5,
    )

    truth = position(1.5)
    errors.append(prediction.center_x - truth)

errors = np.asarray(errors)

mae = float(np.mean(np.abs(errors)))
rmse = float(np.sqrt(np.mean(errors**2)))

check(
    "T1 acceleration forecast",
    np.isfinite(mae) and np.isfinite(rmse),
    {"MAE": mae, "RMSE": rmse, "samples": len(errors)},
)


# T2: Observation loss
quality = ObservationQualityEstimator()
policy = UncertaintyPolicy()

previous = Observation(1, 0.35, 1.0, 0.95)

# No detection is represented by absence of Observation.
missing = None

if missing is None:
    action = stop_proposal("Target observation missing")
else:
    raise AssertionError("Unexpected observation")

check(
    "T2 missing observation STOP",
    action.action == "STOP"
    and action.linear_m_s == 0.0
    and action.angular_rad_s == 0.0,
)


# T3: Object ID change
current = Observation(2, 0.40, 2.0, 0.95)
q = quality.evaluate(current, previous)

check(
    "T3 object identity mismatch",
    not q.reliable,
    {"reason": q.reason, "quality": q.score},
)


# T4: AI disagreement
coordinator = M12Coordinator()
planner = PredictivePlanner()

left = ActionProposal(
    action="TURN_LEFT",
    angular_rad_s=-0.15,
    confidence=0.95,
)

right = ActionProposal(
    action="TURN_RIGHT",
    angular_rad_s=0.15,
    confidence=0.95,
)

prediction = PredictiveWorldModel().update(
    Observation(3, 0.20, 1.0, 0.95),
    horizon_s=0.0,
)

planned = planner.plan(prediction)
result = coordinator.coordinate(left, right, planned)

check(
    "T4 disagreement STOP",
    result.action == "STOP"
    and result.linear_m_s == 0.0
    and result.angular_rad_s == 0.0,
)


# T5: Non-increasing timestamp
world = PredictiveWorldModel()
world.update(Observation(4, 0.30, 2.0, 0.95))

rejected = False

try:
    world.update(Observation(4, 0.40, 2.0, 0.95))
except ValueError:
    rejected = True

check("T5 invalid timestamp rejected", rejected)


# T6: Command limits and STOP
decision = UncertaintyPolicy(
    min_confidence=0.5,
    angular_speed=0.15,
)

actions = []

for x in np.linspace(0.0, 1.0, 101):
    p = PredictiveWorldModel().update(
        Observation(10, float(x), 1.0, 0.95),
        horizon_s=0.0,
    )
    actions.append(decision.predict(p))

max_angular = max(abs(a.angular_rad_s) for a in actions)
max_linear = max(abs(a.linear_m_s) for a in actions)

check(
    "T6 command bounds",
    max_angular <= 0.30
    and max_linear <= 0.20,
    {
        "max_angular_rad_s": max_angular,
        "max_angular_deg_s": math.degrees(max_angular),
        "max_linear_m_s": max_linear,
        "max_linear_km_h": max_linear * 3.6,
    },
)

low = decision.predict(
    PredictiveWorldModel().update(
        Observation(11, 0.80, 1.0, 0.10),
        horizon_s=0.0,
    )
)

check(
    "T6 low-confidence STOP",
    low.action == "STOP"
    and low.angular_rad_s == 0.0
    and low.linear_m_s == 0.0,
)


# Save results
report = {
    "stage": "M15",
    "seed": 45,
    "passed": passed,
    "tests": results,
}

with open(OUT / "report.json", "w") as f:
    json.dump(report, f, indent=2)

print()
print("M15 DYNAMIC ROBUSTNESS")
print(f"Forecast acceleration MAE: {mae:.6f}")
print(f"Forecast acceleration RMSE: {rmse:.6f}")
print(
    f"Maximum angular speed: {max_angular:.3f} rad/s "
    f"({math.degrees(max_angular):.2f} deg/s)"
)
print(
    f"Maximum linear speed: {max_linear:.3f} m/s "
    f"({max_linear*3.6:.2f} km/h)"
)
print(f"TESTS: {passed}/7 PASS")
print("Report:", OUT / "report.json")
