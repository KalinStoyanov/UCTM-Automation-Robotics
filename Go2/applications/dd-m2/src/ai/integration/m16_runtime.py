"""M16 offline AI runtime. No hardware commands."""

import math
from pathlib import Path

import numpy as np

from ..contracts.m12 import Observation, AIResult
from ..contracts.models import ActionProposal
from ..perception.observation_quality import ObservationQualityEstimator
from ..world_model.predictive import PredictiveWorldModel
from ..decision.uncertainty_policy import UncertaintyPolicy
from ..planning.predictive_planner import PredictivePlanner
from .m12_coordinator import M12Coordinator


ACTIONS = ("TURN_LEFT", "STOP", "TURN_RIGHT")


class NeuralPolicyAdapter:
    def __init__(self, model_path):
        path = Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(path)

        with np.load(path, allow_pickle=False) as data:
            self.W1 = data["W1"]
            self.b1 = data["b1"]
            self.W2 = data["W2"]
            self.b2 = data["b2"]

        if (
            self.W1.ndim != 2
            or self.W1.shape[0] != 2
            or self.W2.shape != (self.W1.shape[1], 3)
            or self.b1.shape != (self.W1.shape[1],)
            or self.b2.shape != (3,)
        ):
            raise ValueError("Invalid M13 model dimensions")

        if not all(
            np.isfinite(a).all()
            for a in (self.W1, self.b1, self.W2, self.b2)
        ):
            raise ValueError("Non-finite model parameters")

    def predict(self, center_x, confidence):
        x = np.array([[center_x, confidence]], dtype=float)

        h = np.tanh(x @ self.W1 + self.b1)
        z = h @ self.W2 + self.b2
        z -= z.max(axis=1, keepdims=True)

        e = np.exp(z)
        probabilities = e / e.sum(axis=1, keepdims=True)

        k = int(probabilities.argmax(axis=1)[0])

        return ActionProposal(
            action=ACTIONS[k],
            confidence=float(probabilities[0, k]),
            reason="M13 neural policy",
        )


class M16Runtime:
    def __init__(
        self,
        model_path="results/m13/neural_policy.npz",
        horizon_s=0.5,
        min_confidence=0.5,
        max_linear_m_s=0.20,
        max_angular_rad_s=0.30,
    ):
        if not math.isfinite(horizon_s) or not 0 <= horizon_s <= 2:
            raise ValueError("Invalid horizon")

        if not math.isfinite(min_confidence) or not 0 <= min_confidence <= 1:
            raise ValueError("Invalid confidence threshold")

        if not math.isfinite(max_linear_m_s) or not 0 < max_linear_m_s <= 0.20:
            raise ValueError("Invalid linear limit")

        if not math.isfinite(max_angular_rad_s) or not 0 < max_angular_rad_s <= 0.30:
            raise ValueError("Invalid angular limit")

        self.horizon_s = horizon_s
        self.max_linear = max_linear_m_s
        self.max_angular = max_angular_rad_s

        self.quality = ObservationQualityEstimator(
            min_confidence=min_confidence
        )
        self.world = PredictiveWorldModel()
        self.decision = UncertaintyPolicy(
            min_confidence=min_confidence
        )
        self.learning = NeuralPolicyAdapter(model_path)
        self.planner = PredictivePlanner()
        self.coordinator = M12Coordinator(
            min_confidence=min_confidence
        )

        self.previous = None
        self.active_id = None
        self.last_result = self.stop("Runtime initialized")

    @staticmethod
    def stop(reason):
        return AIResult(
            action="STOP",
            linear_m_s=0.0,
            angular_rad_s=0.0,
            confidence=0.0,
            reason=reason,
        )

    def reset_tracking(self):
        self.previous = None
        self.active_id = None
        self.world = PredictiveWorldModel()

    def step(self, observation):
        if observation is None:
            self.reset_tracking()
            self.last_result = self.stop("Missing observation")
            return self.last_result

        if not isinstance(observation, Observation):
            self.reset_tracking()
            self.last_result = self.stop("Invalid observation type")
            return self.last_result

        if self.active_id is not None and observation.object_id != self.active_id:
            self.reset_tracking()
            self.last_result = self.stop("Object identity changed")
            return self.last_result

        q = self.quality.evaluate(observation, self.previous)

        if not q.reliable:
            self.reset_tracking()
            self.last_result = self.stop(
                "Unreliable observation: " + q.reason
            )
            return self.last_result

        try:
            prediction = self.world.update(
                observation,
                horizon_s=self.horizon_s,
            )

            decision = self.decision.predict(prediction)

            learned = self.learning.predict(
                prediction.center_x,
                observation.confidence,
            )

            planned = self.planner.plan(prediction)

            result = self.coordinator.coordinate(
                decision,
                learned,
                planned,
            )

        except (ValueError, FloatingPointError, OverflowError):
            self.reset_tracking()
            self.last_result = self.stop("AI computation rejected")
            return self.last_result

        self.previous = observation
        self.active_id = observation.object_id

        if (
            result.action not in ACTIONS
            or not math.isfinite(result.linear_m_s)
            or not math.isfinite(result.angular_rad_s)
            or abs(result.linear_m_s) > self.max_linear
            or abs(result.angular_rad_s) > self.max_angular
        ):
            self.reset_tracking()
            self.last_result = self.stop("Safety limits exceeded")
            return self.last_result

        if result.action == "STOP" and (
            result.linear_m_s != 0.0
            or result.angular_rad_s != 0.0
        ):
            self.reset_tracking()
            self.last_result = self.stop("Nonzero STOP command")
            return self.last_result

        if (
            result.action == "TURN_LEFT"
            and result.angular_rad_s >= 0.0
        ) or (
            result.action == "TURN_RIGHT"
            and result.angular_rad_s <= 0.0
        ):
            self.reset_tracking()
            self.last_result = self.stop("Invalid turn direction")
            return self.last_result

        self.last_result = result
        return result
