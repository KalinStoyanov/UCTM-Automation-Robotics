"""M12 B3: Confidence-aware visual decision."""

from ..contracts.models import ActionProposal
from ..contracts.m12 import Prediction


class UncertaintyPolicy:
    def __init__(self, min_confidence=0.5,
                 deadband=0.1, angular_speed=0.15):
        if not 0 <= min_confidence <= 1:
            raise ValueError("Invalid confidence threshold")
        if not 0 <= deadband < 0.5:
            raise ValueError("Invalid deadband")
        if not 0 <= angular_speed <= 0.30:
            raise ValueError("Invalid angular speed")

        self.min_confidence = min_confidence
        self.deadband = deadband
        self.angular_speed = angular_speed

    def predict(self, prediction: Prediction):
        if prediction.confidence < self.min_confidence:
            return ActionProposal(
                action="STOP",
                reason="Low prediction confidence",
            )

        error = prediction.center_x - 0.5

        if abs(error) <= self.deadband:
            return ActionProposal(
                action="STOP",
                reason="Predicted target centered",
            )

        right = error > 0

        return ActionProposal(
            action="TURN_RIGHT" if right else "TURN_LEFT",
            angular_rad_s=(
                self.angular_speed if right
                else -self.angular_speed
            ),
            confidence=prediction.confidence,
            reason="Predicted visual alignment",
        )
