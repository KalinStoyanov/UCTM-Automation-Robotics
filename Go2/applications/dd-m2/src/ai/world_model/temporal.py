"""B2: Temporal world model in normalized image coordinates."""

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class TrackState:
    object_id: int
    center_x: float
    velocity_x: float
    timestamp: float


class TemporalWorldModel:
    def __init__(self, history_size=20):
        if history_size < 2:
            raise ValueError("history_size must be >= 2")
        self.history = deque(maxlen=history_size)

    def update(self, object_id, center_x, timestamp):
        if not 0.0 <= center_x <= 1.0:
            raise ValueError("Invalid center_x")

        previous = next(
            (s for s in reversed(self.history)
             if s.object_id == object_id),
            None,
        )

        velocity = 0.0
        if previous is not None:
            dt = timestamp - previous.timestamp
            if dt <= 0:
                raise ValueError("Timestamp must increase")
            velocity = (center_x - previous.center_x) / dt

        state = TrackState(
            object_id=object_id,
            center_x=center_x,
            velocity_x=velocity,
            timestamp=timestamp,
        )
        self.history.append(state)
        return state
