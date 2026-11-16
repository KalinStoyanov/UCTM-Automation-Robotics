import math


class DiscreteCommands:
    POSTURES = {"STAND_UP", "SIT", "LIE_DOWN"}
    TURNS = {"TURN_LEFT_90", "TURN_RIGHT_90"}

    def __init__(self, angular_speed=0.5):
        if not math.isfinite(angular_speed) or angular_speed <= 0:
            raise ValueError("Invalid angular speed")

        self.angular_speed = angular_speed
        self.posture = "STANDING"
        self.remaining_angle = 0.0
        self.turn_sign = 0

    def command(self, name):
        if name in self.POSTURES:
            self.remaining_angle = 0.0
            self.turn_sign = 0
            self.posture = {
                "STAND_UP": "STANDING",
                "SIT": "SITTING",
                "LIE_DOWN": "LYING",
            }[name]
            return True

        if name in self.TURNS:
            if self.posture != "STANDING":
                return False
            self.remaining_angle = math.pi / 2
            self.turn_sign = (
                1 if name == "TURN_LEFT_90" else -1
            )
            return True

        return False

    def step(self, dt):
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("Invalid dt")

        if self.remaining_angle <= 0:
            return 0.0

        speed = min(
            self.angular_speed,
            self.remaining_angle / dt,
        )

        self.remaining_angle = max(
            0.0,
            self.remaining_angle - speed * dt,
        )

        signed_speed = self.turn_sign * speed

        if self.remaining_angle == 0:
            self.turn_sign = 0

        return signed_speed

    def cancel(self):
        self.remaining_angle = 0.0
        self.turn_sign = 0

    @property
    def turning(self):
        return self.remaining_angle > 0
