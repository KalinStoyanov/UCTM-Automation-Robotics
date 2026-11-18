"""Translate DD-M2 AI decisions into base-controller commands.

Pure offline adapter: no network, robot, or motor access.
"""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class BaseCommand:
    action: str
    linear: float
    angular: float
    reason: str


class AICommandAdapter:
    def __init__(self, max_angular=0.20, min_confidence=0.5):
        if not math.isfinite(max_angular) or not 0 < max_angular <= 0.20:
            raise ValueError("Invalid angular limit")
        if not math.isfinite(min_confidence) or not 0 <= min_confidence <= 1:
            raise ValueError("Invalid confidence threshold")

        self.max_angular = max_angular
        self.min_confidence = min_confidence

    @staticmethod
    def stop(reason):
        return BaseCommand("STOP", 0.0, 0.0, reason)

    def convert(self, result):
        if result is None:
            return self.stop("Missing AI result")

        try:
            action = result.action
            linear = result.linear_m_s
            angular = result.angular_rad_s
            confidence = result.confidence
        except AttributeError:
            return self.stop("Invalid AI result")

        if action not in ("STOP", "TURN_LEFT", "TURN_RIGHT"):
            return self.stop("Unsupported AI action")

        values = (linear, angular, confidence)
        if any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            for v in values
        ):
            return self.stop("Invalid AI values")

        if confidence < self.min_confidence:
            return self.stop("Low AI confidence")

        if linear != 0.0:
            return self.stop("AI linear motion unsupported")

        if action == "STOP":
            return self.stop("AI STOP")

        if abs(angular) < 1e-9:
            return self.stop("Zero turn velocity")

        # M16 convention: LEFT negative, RIGHT positive.
        if action == "TURN_LEFT" and angular >= 0:
            return self.stop("Invalid AI left-turn sign")
        if action == "TURN_RIGHT" and angular <= 0:
            return self.stop("Invalid AI right-turn sign")

        # Manual base convention: LEFT positive, RIGHT negative.
        base_angular = min(abs(angular), self.max_angular)
        if action == "TURN_RIGHT":
            base_angular = -base_angular

        return BaseCommand(
            action, 0.0, base_angular, "AI command converted"
        )
