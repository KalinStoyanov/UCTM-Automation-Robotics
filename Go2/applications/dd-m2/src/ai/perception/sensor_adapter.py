"""M18: Offline sensor frame adapter."""

import math
from dataclasses import dataclass

from ..contracts.m12 import Observation


@dataclass(frozen=True)
class SensorFrame:
    timestamp: float
    detections: tuple


class SensorAdapter:
    def __init__(self, min_confidence=0.5):
        if (
            not math.isfinite(min_confidence)
            or not 0 <= min_confidence <= 1
        ):
            raise ValueError("Invalid confidence threshold")

        self.min_confidence = min_confidence
        self.last_timestamp = None
        self.target_id = None

    def reset(self):
        self.last_timestamp = None
        self.target_id = None

    def convert(self, raw):
        if not isinstance(raw, dict):
            raise ValueError("Frame must be a dictionary")

        timestamp = raw.get("timestamp")
        if (
            isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
            or not math.isfinite(timestamp)
        ):
            raise ValueError("Invalid timestamp")

        if (
            self.last_timestamp is not None
            and timestamp <= self.last_timestamp
        ):
            raise ValueError("Non-increasing timestamp")

        detections = raw.get("detections")
        if not isinstance(detections, list):
            raise ValueError("Detections must be a list")

        candidates = []

        for d in detections:
            if not isinstance(d, dict):
                raise ValueError("Invalid detection")

            object_id = d.get("object_id")
            center_x = d.get("center_x")
            confidence = d.get("confidence")

            if (
                type(object_id) is not int
                or object_id < 0
                or isinstance(center_x, bool)
                or not isinstance(center_x, (int, float))
                or not math.isfinite(center_x)
                or not 0 <= center_x <= 1
                or isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence)
                or not 0 <= confidence <= 1
            ):
                raise ValueError("Invalid detection fields")

            if confidence >= self.min_confidence:
                candidates.append(d)

        self.last_timestamp = timestamp

        if not candidates:
            self.target_id = None
            return None

        if self.target_id is not None:
            matched = [
                d for d in candidates
                if d["object_id"] == self.target_id
            ]
            if matched:
                selected = max(
                    matched,
                    key=lambda d: d["confidence"],
                )
            else:
                self.target_id = None
                return None
        else:
            selected = max(
                candidates,
                key=lambda d: d["confidence"],
            )

        self.target_id = selected["object_id"]

        return Observation(
            object_id=selected["object_id"],
            center_x=float(selected["center_x"]),
            timestamp=float(timestamp),
            confidence=float(selected["confidence"]),
        )
