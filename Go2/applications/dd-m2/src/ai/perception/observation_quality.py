"""M12 B1: Observation quality assessment."""

from dataclasses import dataclass
import math

from ..contracts.m12 import Observation


@dataclass(frozen=True)
class ObservationQuality:
    score: float
    reliable: bool
    reason: str


class ObservationQualityEstimator:
    def __init__(self, min_confidence=0.50,
                 max_image_speed=0.50):
        if not 0 <= min_confidence <= 1:
            raise ValueError("Invalid min_confidence")
        if not math.isfinite(max_image_speed) or max_image_speed <= 0:
            raise ValueError("Invalid max_image_speed")

        self.min_confidence = min_confidence
        self.max_image_speed = max_image_speed

    def evaluate(self, current: Observation,
                 previous: Observation | None = None):

        if current.confidence < self.min_confidence:
            return ObservationQuality(
                current.confidence, False,
                "Low detector confidence"
            )

        if previous is None:
            return ObservationQuality(
                current.confidence, True,
                "Initial observation"
            )

        if current.object_id != previous.object_id:
            return ObservationQuality(
                0.0, False, "Object ID mismatch"
            )

        dt = current.timestamp - previous.timestamp

        if dt <= 0:
            return ObservationQuality(
                0.0, False, "Invalid observation time"
            )

        image_speed = abs(
            current.center_x - previous.center_x
        ) / dt

        consistency = max(
            0.0,
            1.0 - image_speed / self.max_image_speed
        )

        score = current.confidence * consistency

        return ObservationQuality(
            score,
            score >= self.min_confidence,
            "Temporal consistency evaluated"
        )
