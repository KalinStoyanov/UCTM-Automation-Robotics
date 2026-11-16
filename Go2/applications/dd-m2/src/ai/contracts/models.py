"""Shared data contracts for DD-M2 AI components."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DetectedObject:
    object_id: int
    label: str
    bbox: tuple[float, float, float, float]
    confidence: float


@dataclass(frozen=True)
class WorldState:
    timestamp: float
    objects: tuple[DetectedObject, ...] = ()
    robot_state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionProposal:
    action: str
    linear_m_s: float = 0.0
    angular_rad_s: float = 0.0
    confidence: float = 1.0
    reason: str = ""
