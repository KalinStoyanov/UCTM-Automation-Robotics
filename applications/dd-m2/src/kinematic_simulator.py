import math


class KinematicSimulator:
    def __init__(self, linear_speed=0.2, angular_speed=0.5):
        if not math.isfinite(linear_speed) or linear_speed <= 0:
            raise ValueError("Invalid linear speed")
        if not math.isfinite(angular_speed) or angular_speed <= 0:
            raise ValueError("Invalid angular speed")

        self.x = 0.0
        self.y = 0.0
        self.heading = 0.0

        self.linear_speed = linear_speed
        self.angular_speed = angular_speed

        self.v = 0.0
        self.w = 0.0
        self.remaining_turn = 0.0

    def command(self, cmd):
        self.remaining_turn = 0.0

        if cmd == "FORWARD":
            self.v = self.linear_speed
            self.w = 0.0

        elif cmd == "BACKWARD":
            self.v = -self.linear_speed
            self.w = 0.0

        elif cmd == "TURN_LEFT_90":
            self.v = 0.0
            self.w = self.angular_speed
            self.remaining_turn = math.pi / 2

        elif cmd == "TURN_RIGHT_90":
            self.v = 0.0
            self.w = -self.angular_speed
            self.remaining_turn = -math.pi / 2

        else:
            self.v = 0.0
            self.w = 0.0

    def step(self, dt):
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be positive and finite")

        if self.remaining_turn != 0.0:
            requested = self.w * dt
            actual = math.copysign(
                min(abs(requested), abs(self.remaining_turn)),
                self.remaining_turn
            )

            self.heading = (
                self.heading + actual
            ) % (2 * math.pi)

            self.remaining_turn -= actual

            if abs(self.remaining_turn) < 1e-10:
                self.remaining_turn = 0.0
                self.w = 0.0

        else:
            self.x += self.v * math.cos(self.heading) * dt
            self.y += self.v * math.sin(self.heading) * dt

    def status(self):
        return {
            "x_m": round(self.x, 4),
            "y_m": round(self.y, 4),
            "heading_deg": round(
                math.degrees(self.heading), 2
            ),
            "linear_m_s": round(self.v, 4),
            "linear_km_h": round(self.v * 3.6, 4),
            "angular_rad_s": round(self.w, 4),
            "angular_deg_s": round(
                math.degrees(self.w), 2
            ),
            "turn_remaining_deg": round(
                math.degrees(self.remaining_turn), 2
            ),
        }
