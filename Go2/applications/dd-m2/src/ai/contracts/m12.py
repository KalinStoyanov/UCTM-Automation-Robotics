"""M12: Shared contracts for predictive AI components."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Observation:
    object_id: int
    center_x: float
    timestamp: float
    confidence: float

    def __post_init__(self):
        if not math.isfinite(self.center_x) or not 0 <= self.center_x <= 1:
            raise ValueError("Invalid center_x")
        if not math.isfinite(self.timestamp):
            raise ValueError("Invalid timestamp")
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("Invalid confidence")


@dataclass(frozen=True)
class Prediction:
    object_id: int
    center_x: float
    velocity_x: float
    horizon_s: float
    confidence: float


@dataclass(frozen=True)
class ActionEvaluation:
    action: str
    score: float
    confidence: float


@dataclass(frozen=True)
class AIResult:
    action: str
    linear_m_s: float
    angular_rad_s: float
    confidence: float
    reason: str
