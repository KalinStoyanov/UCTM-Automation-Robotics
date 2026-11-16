"""M12 B4: Nearest-neighbor generalization."""

import math
from ..contracts.models import ActionProposal


class NearestPolicy:
    def __init__(self, max_distance=0.1):
        if not math.isfinite(max_distance) or max_distance <= 0:
            raise ValueError("Invalid max_distance")
        self.max_distance = max_distance
        self.examples = []

    def fit(self, examples):
        self.examples = list(examples)

        if not self.examples:
            raise ValueError("Empty training set")

        for x, action in self.examples:
            if not math.isfinite(x) or not 0 <= x <= 1:
                raise ValueError("Invalid training observation")
            if action not in {
                "STOP", "TURN_LEFT", "TURN_RIGHT"
            }:
                raise ValueError("Invalid training action")

        return self

    def predict(self, center_x):
        if not math.isfinite(center_x) or not 0 <= center_x <= 1:
            return ActionProposal(
                action="STOP", reason="Invalid observation"
            )

        if not self.examples:
            return ActionProposal(
                action="STOP", reason="Model not trained"
            )

        x, action = min(
            self.examples,
            key=lambda item: abs(item[0] - center_x),
        )

        distance = abs(x - center_x)

        if distance > self.max_distance:
            return ActionProposal(
                action="STOP",
                reason="Outside training coverage",
            )

        return ActionProposal(
            action=action,
            confidence=max(0.0, 1.0 - distance / self.max_distance),
            reason="Nearest training observation",
        )
