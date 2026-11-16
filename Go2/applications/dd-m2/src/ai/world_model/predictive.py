"""M12 B2: Constant-velocity image-space prediction."""

from ..contracts.m12 import Observation, Prediction


class PredictiveWorldModel:
    def __init__(self, max_horizon_s=2.0):
        if max_horizon_s <= 0:
            raise ValueError("Invalid maximum horizon")
        self.max_horizon_s = max_horizon_s
        self.previous = {}

    def update(self, observation: Observation, horizon_s=1.0):
        if not 0 <= horizon_s <= self.max_horizon_s:
            raise ValueError("Invalid prediction horizon")

        previous = self.previous.get(observation.object_id)
        velocity = 0.0

        if previous is not None:
            dt = observation.timestamp - previous.timestamp
            if dt <= 0:
                raise ValueError("Timestamp must increase")
            velocity = (
                observation.center_x - previous.center_x
            ) / dt

        self.previous[observation.object_id] = observation

        predicted_x = max(
            0.0,
            min(1.0, observation.center_x + velocity * horizon_s),
        )

        return Prediction(
            object_id=observation.object_id,
            center_x=predicted_x,
            velocity_x=velocity,
            horizon_s=horizon_s,
            confidence=observation.confidence,
        )
