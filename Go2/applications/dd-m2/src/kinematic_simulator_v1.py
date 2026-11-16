import math


class KinematicSimulator:
    def __init__(self, linear_speed=0.2, angular_speed=0.5):
        self.x = 0.0
        self.y = 0.0
        self.heading = 0.0

        self.linear_speed = linear_speed
        self.angular_speed = angular_speed

        self.v = 0.0
        self.w = 0.0

    def command(self, cmd):
        if cmd == "FORWARD":
            self.v = self.linear_speed
            self.w = 0.0
        elif cmd == "BACKWARD":
            self.v = -self.linear_speed
            self.w = 0.0
        elif cmd == "TURN_LEFT_90":
            self.v = 0.0
            self.w = self.angular_speed
        elif cmd == "TURN_RIGHT_90":
            self.v = 0.0
            self.w = -self.angular_speed
        else:
            self.v = 0.0
            self.w = 0.0

    def step(self, dt):
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be positive and finite")

        if abs(self.w) < 1e-12:
            self.x += self.v * math.cos(self.heading) * dt
            self.y += self.v * math.sin(self.heading) * dt
        else:
            new_heading = self.heading + self.w * dt

            self.x += (self.v / self.w) * (
                math.sin(new_heading) - math.sin(self.heading)
            )

            self.y -= (self.v / self.w) * (
                math.cos(new_heading) - math.cos(self.heading)
            )

        self.heading = (
            self.heading + self.w * dt
        ) % (2 * math.pi)

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
        }
