"""M13: Offline AI learning and evaluation."""

import json
import math
from pathlib import Path

import numpy as np

from src.ai.contracts.m12 import Observation
from src.ai.perception.observation_quality import ObservationQualityEstimator
from src.ai.world_model.predictive import PredictiveWorldModel
from src.ai.decision.uncertainty_policy import UncertaintyPolicy
from src.ai.planning.predictive_planner import PredictivePlanner
from src.ai.integration.m12_coordinator import M12Coordinator
from src.ai.contracts.models import ActionProposal


SEED = 42
RNG = np.random.default_rng(SEED)

RESULTS = Path("results/m13")
RESULTS.mkdir(parents=True, exist_ok=True)

ACTIONS = ("TURN_LEFT", "STOP", "TURN_RIGHT")


def labels(x):
    return np.where(
        x < 0.4, 0,
        np.where(x > 0.6, 2, 1)
    )


def generate_dataset(n, noise=0.015):
    true_x = RNG.uniform(0.05, 0.95, n)
    observed_x = np.clip(
        true_x + RNG.normal(0, noise, n), 0, 1
    )
    confidence = RNG.uniform(0.65, 1.0, n)

    X = np.column_stack([observed_x, confidence])
    y = labels(true_x)

    return X, y


class NeuralPolicy:
    def __init__(self, hidden=24, lr=0.08):
        self.lr = lr
        self.W1 = RNG.normal(0, 0.5, (2, hidden))
        self.b1 = np.zeros(hidden)
        self.W2 = RNG.normal(0, 0.5, (hidden, 3))
        self.b2 = np.zeros(3)

    def forward(self, X):
        H = np.tanh(X @ self.W1 + self.b1)
        Z = H @ self.W2 + self.b2
        Z -= Z.max(axis=1, keepdims=True)
        E = np.exp(Z)
        P = E / E.sum(axis=1, keepdims=True)
        return H, P

    def fit(self, X, y, epochs=600):
        Y = np.eye(3)[y]
        n = len(X)

        for _ in range(epochs):
            H, P = self.forward(X)

            dZ = (P - Y) / n
            dW2 = H.T @ dZ
            db2 = dZ.sum(axis=0)

            dH = (dZ @ self.W2.T) * (1 - H * H)
            dW1 = X.T @ dH
            db1 = dH.sum(axis=0)

            self.W2 -= self.lr * dW2
            self.b2 -= self.lr * db2
            self.W1 -= self.lr * dW1
            self.b1 -= self.lr * db1

    def predict(self, X):
        _, P = self.forward(X)
        return P.argmax(axis=1), P.max(axis=1)


def accuracy(y_true, y_pred):
    return float(np.mean(y_true == y_pred))


def evaluate_trajectory(name, positions, confidence=0.95):
    world = PredictiveWorldModel()
    quality = ObservationQualityEstimator()
    decision = UncertaintyPolicy()
    planner = PredictivePlanner()
    coordinator = M12Coordinator()

    previous = None
    records = []

    for i, x in enumerate(positions):
        obs = Observation(
            object_id=1,
            center_x=float(x),
            timestamp=float(i + 1),
            confidence=confidence,
        )

        q = quality.evaluate(obs, previous)
        prediction = world.update(obs, horizon_s=0.5)
        d = decision.predict(prediction)
        plan = planner.plan(prediction)

        _, probabilities = MODEL.forward(
            np.array([[x, confidence]])
        )

        learned_action = ACTIONS[
            int(probabilities.argmax(axis=1)[0])
        ]

        learned = ActionProposal(
            action=learned_action,
            confidence=float(probabilities.max()),
        )

        result = coordinator.coordinate(d, learned, plan)

        if not q.reliable:
            final_action = "STOP"
            reason = "Unreliable observation"
        else:
            final_action = result.action
            reason = result.reason

        records.append({
            "time": i + 1,
            "observed_x": round(float(x), 4),
            "predicted_x": round(prediction.center_x, 4),
            "image_velocity": round(prediction.velocity_x, 4),
            "quality": round(q.score, 4),
            "decision": d.action,
            "learned": learned_action,
            "planned": plan.action,
            "final": final_action,
            "reason": reason,
        })

        previous = obs

    return {"scenario": name, "records": records}


# Independent train/test samples
X_train, y_train = generate_dataset(3000)
X_test, y_test = generate_dataset(1000)

MODEL = NeuralPolicy()
MODEL.fit(X_train, y_train)

train_pred, _ = MODEL.predict(X_train)
test_pred, _ = MODEL.predict(X_test)

train_acc = accuracy(y_train, train_pred)
test_acc = accuracy(y_test, test_pred)

print("M13 Neural Learning")
print("Train accuracy:", round(train_acc, 4))
print("Test accuracy: ", round(test_acc, 4))

# Unseen synthetic trajectories
scenarios = [
    evaluate_trajectory(
        "left_to_right",
        [0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80],
    ),
    evaluate_trajectory(
        "right_to_left",
        [0.80, 0.70, 0.60, 0.50, 0.40, 0.30, 0.20],
    ),
    evaluate_trajectory(
        "low_confidence",
        [0.20, 0.30, 0.40, 0.50],
        confidence=0.20,
    ),
]

# Safety invariants
valid_actions = set(ACTIONS)

for scenario in scenarios:
    for record in scenario["records"]:
        assert record["final"] in valid_actions

low = scenarios[2]["records"]
assert all(r["final"] == "STOP" for r in low)

# Invalid observation must be rejected
try:
    Observation(1, float("nan"), 1.0, 0.95)
    raise AssertionError("NaN observation accepted")
except ValueError:
    pass

# Save model parameters
np.savez(
    RESULTS / "neural_policy.npz",
    W1=MODEL.W1,
    b1=MODEL.b1,
    W2=MODEL.W2,
    b2=MODEL.b2,
)

report = {
    "seed": SEED,
    "train_samples": len(X_train),
    "test_samples": len(X_test),
    "train_accuracy": train_acc,
    "test_accuracy": test_acc,
    "scenarios": scenarios,
}

with open(RESULTS / "report.json", "w") as f:
    json.dump(report, f, indent=2)

for scenario in scenarios:
    print()
    print("Scenario:", scenario["scenario"])
    for r in scenario["records"]:
        print(
            f"t={r['time']} "
            f"x={r['observed_x']:.2f} "
            f"pred={r['predicted_x']:.2f} "
            f"quality={r['quality']:.2f} "
            f"final={r['final']}"
        )

print()
print("M13 COMPLETED")
print("Report:", RESULTS / "report.json")
print("Model: ", RESULTS / "neural_policy.npz")
