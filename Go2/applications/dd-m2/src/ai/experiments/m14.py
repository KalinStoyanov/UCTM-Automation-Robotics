"""M14: Quantitative offline validation of DD-M2 AI."""

import csv
import json
from pathlib import Path

import numpy as np

from src.ai.contracts.models import WorldState
from src.ai.contracts.m12 import Observation
from src.ai.decision.visual_follow_policy import VisualFollowPolicy
from src.ai.learning.nearest_policy import NearestPolicy
from src.ai.learning.scenarios import generate_training_examples
from src.ai.world_model.predictive import PredictiveWorldModel


SEED = 43
RNG = np.random.default_rng(SEED)

OUT = Path("results/m14")
OUT.mkdir(parents=True, exist_ok=True)

ACTIONS = ("TURN_LEFT", "STOP", "TURN_RIGHT")
INDEX = {name: i for i, name in enumerate(ACTIONS)}

MODEL_PATH = Path("results/m13/neural_policy.npz")

if not MODEL_PATH.is_file():
    raise FileNotFoundError(
        "M13 model missing: results/m13/neural_policy.npz"
    )

weights = np.load(MODEL_PATH)

W1 = weights["W1"]
b1 = weights["b1"]
W2 = weights["W2"]
b2 = weights["b2"]


def neural_predict(X):
    H = np.tanh(X @ W1 + b1)
    Z = H @ W2 + b2
    Z = Z - Z.max(axis=1, keepdims=True)
    E = np.exp(Z)
    P = E / E.sum(axis=1, keepdims=True)
    return P.argmax(axis=1), P.max(axis=1)


def labels(x):
    return np.where(
        x < 0.4, 0,
        np.where(x > 0.6, 2, 1)
    )


def confusion_matrix(y_true, y_pred):
    cm = np.zeros((3, 3), dtype=int)
    for actual, predicted in zip(y_true, y_pred):
        cm[int(actual), int(predicted)] += 1
    return cm


def classification_metrics(y_true, y_pred):
    cm = confusion_matrix(y_true, y_pred)
    precision = []
    recall = []
    f1 = []

    for k in range(3):
        tp = cm[k, k]
        fp = cm[:, k].sum() - tp
        fn = cm[k, :].sum() - tp

        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0

        precision.append(p)
        recall.append(r)
        f1.append(f)

    return {
        "accuracy": float(np.mean(y_true == y_pred)),
        "macro_precision": float(np.mean(precision)),
        "macro_recall": float(np.mean(recall)),
        "macro_f1": float(np.mean(f1)),
        "per_class_precision": [float(v) for v in precision],
        "per_class_recall": [float(v) for v in recall],
        "per_class_f1": [float(v) for v in f1],
        "confusion_matrix": cm.tolist(),
    }


def evaluate_models(true_x, observed_x, confidence):
    n = len(true_x)
    y = labels(true_x)

    m11 = VisualFollowPolicy()
    m12 = NearestPolicy(max_distance=0.10)
    m12.fit(generate_training_examples())

    pred11 = np.empty(n, dtype=int)
    pred12 = np.empty(n, dtype=int)

    for i, x in enumerate(observed_x):
        state = WorldState(
            timestamp=float(i + 1),
            robot_state={"target_center_x": float(x)},
        )

        pred11[i] = INDEX[m11.predict(state).action]
        pred12[i] = INDEX[m12.predict(float(x)).action]

    X = np.column_stack([observed_x, confidence])
    pred13, confidence13 = neural_predict(X)

    return {
        "M11": classification_metrics(y, pred11),
        "M12": classification_metrics(y, pred12),
        "M13": classification_metrics(y, pred13),
    }, pred13, confidence13


# 1. Common independent validation set
N = 3000
true_x = RNG.uniform(0.05, 0.95, N)
confidence = RNG.uniform(0.65, 1.0, N)

noise_levels = [0.0, 0.015, 0.03, 0.06, 0.10]

noise_results = []

for noise in noise_levels:
    observed_x = np.clip(
        true_x + RNG.normal(0, noise, N),
        0.0, 1.0,
    )

    metrics, _, _ = evaluate_models(
        true_x, observed_x, confidence
    )

    row = {
        "noise_sigma": noise,
        "M11_accuracy": metrics["M11"]["accuracy"],
        "M12_accuracy": metrics["M12"]["accuracy"],
        "M13_accuracy": metrics["M13"]["accuracy"],
        "M11_macro_f1": metrics["M11"]["macro_f1"],
        "M12_macro_f1": metrics["M12"]["macro_f1"],
        "M13_macro_f1": metrics["M13"]["macro_f1"],
    }

    noise_results.append(row)

    if noise == 0.015:
        reference_metrics = metrics


# 2. Forecast validation
# Independent synthetic trajectories, fixed 1-second sampling.
forecast_errors = []
horizon = 0.5

for trajectory_id in range(100):
    x0 = RNG.uniform(0.2, 0.8)
    velocity = RNG.uniform(-0.12, 0.12)

    # Constant velocity; stay within image boundaries.
    x1 = x0
    x2 = np.clip(x0 + velocity, 0.0, 1.0)
    future = np.clip(x2 + velocity * horizon, 0.0, 1.0)

    world = PredictiveWorldModel()

    world.update(
        Observation(trajectory_id, x1, 1.0, 0.95),
        horizon_s=horizon,
    )

    prediction = world.update(
        Observation(trajectory_id, x2, 2.0, 0.95),
        horizon_s=horizon,
    )

    forecast_errors.append(prediction.center_x - future)

forecast_errors = np.array(forecast_errors)

forecast = {
    "horizon_s": horizon,
    "trajectories": len(forecast_errors),
    "mae": float(np.mean(np.abs(forecast_errors))),
    "rmse": float(np.sqrt(np.mean(forecast_errors ** 2))),
}


# 3. Low-confidence safety check
low_confidence = 0.20

low_observations = [
    Observation(1, float(x), float(i + 1), low_confidence)
    for i, x in enumerate(np.linspace(0.1, 0.9, 100))
]

from src.ai.decision.uncertainty_policy import UncertaintyPolicy

policy = UncertaintyPolicy()
world = PredictiveWorldModel()

stop_count = 0

for obs in low_observations:
    prediction = world.update(obs, horizon_s=0.0)
    action = policy.predict(prediction).action
    stop_count += action == "STOP"

safety = {
    "samples": len(low_observations),
    "stop_count": stop_count,
    "stop_rate": stop_count / len(low_observations),
}


# 4. Save reports
report = {
    "seed": SEED,
    "validation_samples": N,
    "reference_noise_sigma": 0.015,
    "reference_metrics": reference_metrics,
    "noise_robustness": noise_results,
    "forecast": forecast,
    "low_confidence_safety": safety,
}

with open(OUT / "report.json", "w") as f:
    json.dump(report, f, indent=2)

with open(OUT / "noise_robustness.csv", "w", newline="") as f:
    writer = csv.DictWriter(
        f, fieldnames=noise_results[0].keys()
    )
    writer.writeheader()
    writer.writerows(noise_results)


# 5. Terminal summary
print("M14 — QUANTITATIVE VALIDATION")
print()

for name in ("M11", "M12", "M13"):
    m = reference_metrics[name]
    print(
        f"{name}: "
        f"Accuracy={m['accuracy']:.4f} "
        f"Macro-F1={m['macro_f1']:.4f}"
    )

print()
print("M13 confusion matrix:")
for row in reference_metrics["M13"]["confusion_matrix"]:
    print(row)

print()
print("Noise robustness:")
for row in noise_results:
    print(
        f"sigma={row['noise_sigma']:.3f} | "
        f"M11={row['M11_accuracy']:.3f} | "
        f"M12={row['M12_accuracy']:.3f} | "
        f"M13={row['M13_accuracy']:.3f}"
    )

print()
print(
    f"Forecast: MAE={forecast['mae']:.6f}, "
    f"RMSE={forecast['rmse']:.6f}"
)
print(
    f"Low-confidence STOP rate: "
    f"{safety['stop_rate']:.2%}"
)

assert safety["stop_rate"] == 1.0
assert np.isfinite(forecast["rmse"])

print()
print("M14 COMPLETED")
print("Report:", OUT / "report.json")
print("Noise data:", OUT / "noise_robustness.csv")
