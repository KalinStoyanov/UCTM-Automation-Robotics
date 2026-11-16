"""B5: Short-horizon planning for discrete visual actions."""


class DiscretePlanner:
    def __init__(self, horizon=3):
        if horizon < 1:
            raise ValueError("horizon must be positive")
        self.horizon = horizon

    def plan(self, target_center_x):
        if target_center_x is None:
            return ["STOP"]

        if not 0.0 <= target_center_x <= 1.0:
            return ["STOP"]

        if target_center_x < 0.4:
            action = "TURN_LEFT"
        elif target_center_x > 0.6:
            action = "TURN_RIGHT"
        else:
            action = "STOP"

        if action == "STOP":
            return ["STOP"]

        return [action] * self.horizon
