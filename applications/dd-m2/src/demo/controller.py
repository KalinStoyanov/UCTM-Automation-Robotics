import math

from src.tracking.follow_motion import FollowMotion


class DemoController:
    """
    Software-only demonstration controller.

    States:
        IDLE
        FOLLOW
        ROTATE_SEARCH
        STOP

    No physical robot commands are sent.
    """

    def __init__(self):
        self.state = "IDLE"
        self.target_id = None
        self.motion = FollowMotion()
        self.search_angle = 0.0
        self.search_speed = 0.5
        self.max_search_angle = 2 * math.pi

    def stop(self):
        self.state = "STOP"
        self.target_id = None
        return self.status()

    def reset(self):
        self.state = "IDLE"
        self.target_id = None
        self.search_angle = 0.0
        return self.status()

    def status(self):
        return {
            "state": self.state,
            "target_id": self.target_id,
            "motion": FollowMotion.stop(),
        }

    def update(
        self,
        persons,
        frame_width,
        frame_height,
        dt=1 / 30,
        gesture=None,
    ):
        if gesture == "STOP":
            return self.stop()

        if self.state == "STOP":
            return self.status()

        if self.state == "IDLE":
            candidates = [
                p for p in persons
                if p.get("arm_raised") is True
            ]

            if len(candidates) == 1:
                self.target_id = candidates[0]["id"]
                self.state = "FOLLOW"
            else:
                return self.status()

        target = next(
            (
                p for p in persons
                if p["id"] == self.target_id
            ),
            None,
        )

        if self.state == "FOLLOW":
            if target is None:
                return self.stop()

            if target.get("arm_raised") is not True:
                if (
                    target.get("left_arm") == "HORIZONTAL"
                    or target.get("right_arm") == "HORIZONTAL"
                ):
                    self.state = "ROTATE_SEARCH"
                    self.target_id = None
                    self.search_angle = 0.0
                else:
                    return self.stop()

            if self.state == "FOLLOW":
                return {
                    "state": "FOLLOW",
                    "target_id": self.target_id,
                    "motion": self.motion.compute(
                        target, frame_width, frame_height
                    ),
                }

        if self.state == "ROTATE_SEARCH":
            candidates = [
                p for p in persons
                if p.get("arm_raised") is True
            ]

            if len(candidates) == 1:
                self.target_id = candidates[0]["id"]
                self.state = "FOLLOW"
                return self.update(
                    persons,
                    frame_width,
                    frame_height,
                    dt,
                )

            remaining = self.max_search_angle - self.search_angle
            if remaining <= 0:
                return self.stop()

            angular = min(
                self.search_speed,
                remaining / dt,
            )
            self.search_angle += angular * dt

            return {
                "state": "ROTATE_SEARCH",
                "target_id": None,
                "motion": {
                    "linear_m_s": 0.0,
                    "linear_km_h": 0.0,
                    "angular_rad_s": angular,
                    "angular_deg_s": math.degrees(angular),
                },
            }

        return self.status()
