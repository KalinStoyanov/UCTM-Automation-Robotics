import math


class FollowMotion:
    def __init__(
        self,
        linear_speed=0.2,
        angular_speed=0.5,
        target_height_ratio=0.55,
        center_tolerance=0.10,
        distance_tolerance=0.05,
    ):
        self.linear_speed = linear_speed
        self.angular_speed = angular_speed
        self.target_height_ratio = target_height_ratio
        self.center_tolerance = center_tolerance
        self.distance_tolerance = distance_tolerance

    @staticmethod
    def stop():
        return {
            "linear_m_s": 0.0,
            "linear_km_h": 0.0,
            "angular_rad_s": 0.0,
            "angular_deg_s": 0.0,
        }

    def compute(self, target, frame_width, frame_height):
        if target is None or frame_width <= 0 or frame_height <= 0:
            return self.stop()

        x1, y1, x2, y2 = target["bbox"]

        if x2 <= x1 or y2 <= y1:
            return self.stop()

        center_x = (x1 + x2) / 2
        error_x = (center_x - frame_width / 2) / (frame_width / 2)

        height_ratio = (y2 - y1) / frame_height
        distance_error = self.target_height_ratio - height_ratio

        linear = 0.0
        angular = 0.0

        if abs(error_x) > self.center_tolerance:
            angular = math.copysign(self.angular_speed, error_x)

        if distance_error > self.distance_tolerance:
            linear = self.linear_speed
        elif distance_error < -self.distance_tolerance:
            linear = -self.linear_speed

        return {
            "linear_m_s": linear,
            "linear_km_h": linear * 3.6,
            "angular_rad_s": angular,
            "angular_deg_s": math.degrees(angular),
        }
