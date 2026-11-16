import math

from src.demo.discrete_commands import DiscreteCommands
from src.tracking.follow_motion import FollowMotion


class CompleteDemoController:
    """
    DD-M2 software-only demonstration controller.

    All outputs are simulated motion requests.
    No robot hardware interface is used.
    """

    def __init__(self):
        self.state = "IDLE"
        self.target_id = None
        self.follow_motion = FollowMotion()
        self.discrete = DiscreteCommands()
        self.search_angle = 0.0
        self.search_speed = 0.5
        self.search_limit = 2 * math.pi
        self.distance_mode = None

    @staticmethod
    def zero_motion():
        return FollowMotion.stop()

    def result(self, motion=None):
        return {
            "state": self.state,
            "target_id": self.target_id,
            "posture": self.discrete.posture,
            "distance_mode": self.distance_mode,
            "motion": motion or self.zero_motion(),
        }

    def stop(self):
        self.state = "STOP"
        self.target_id = None
        self.distance_mode = None
        self.discrete.cancel()
        return self.result()

    def reset(self):
        self.state = "IDLE"
        self.target_id = None
        self.distance_mode = None
        self.search_angle = 0.0
        self.discrete.cancel()
        return self.result()

    def update(
        self,
        persons,
        frame_width,
        frame_height,
        dt=1 / 30,
        command=None,
    ):
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("Invalid dt")

        if command == "STOP":
            return self.stop()

        if self.state == "STOP":
            return self.result()

        if command in DiscreteCommands.POSTURES:
            self.discrete.command(command)
            self.state = "IDLE"
            self.target_id = None
            self.distance_mode = None
            return self.result()

        if command in DiscreteCommands.TURNS:
            if self.discrete.command(command):
                self.state = "TURNING"
                self.target_id = None
                self.distance_mode = None

        if self.state == "TURNING":
            angular = self.discrete.step(dt)

            if not self.discrete.turning:
                self.state = "IDLE"

            return self.result({
                "linear_m_s": 0.0,
                "linear_km_h": 0.0,
                "angular_rad_s": angular,
                "angular_deg_s": math.degrees(angular),
            })

        if self.discrete.posture != "STANDING":
            return self.result()

        if self.state == "IDLE":
            candidates = [
                p for p in persons
                if p.get("arm_above_head") is True
            ]

            if len(candidates) != 1:
                return self.result()

            self.target_id = candidates[0]["id"]
            self.state = "FOLLOW"

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
                horizontal = (
                    target.get("left_arm") == "HORIZONTAL"
                    or target.get("right_arm") == "HORIZONTAL"
                )

                if horizontal:
                    self.state = "ROTATE_SEARCH"
                    self.target_id = None
                    self.search_angle = 0.0
                    self.distance_mode = None
                else:
                    return self.stop()

            else:
                if command in ("COME_TO_ME", "MOVE_AWAY"):
                    self.distance_mode = command

                motion = self.follow_motion.compute(
                    target,
                    frame_width,
                    frame_height,
                )

                if self.distance_mode == "COME_TO_ME":
                    motion["linear_m_s"] = abs(
                        self.follow_motion.linear_speed
                    )

                elif self.distance_mode == "MOVE_AWAY":
                    motion["linear_m_s"] = -abs(
                        self.follow_motion.linear_speed
                    )

                motion["linear_km_h"] = (
                    motion["linear_m_s"] * 3.6
                )

                return self.result(motion)

        if self.state == "ROTATE_SEARCH":
            candidates = [
                p for p in persons
                if p.get("arm_above_head") is True
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

            remaining = self.search_limit - self.search_angle

            if remaining <= 1e-9:
                return self.stop()

            angular = min(
                self.search_speed,
                remaining / dt,
            )

            self.search_angle += angular * dt

            return self.result({
                "linear_m_s": 0.0,
                "linear_km_h": 0.0,
                "angular_rad_s": angular,
                "angular_deg_s": math.degrees(angular),
            })

        return self.result()
