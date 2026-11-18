"""Offline arbitration for DD-M2. No hardware operations."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ArbitrationResult:
    source: str
    action: str
    linear: float
    angular: float


class CommandArbiter:
    def __init__(self):
        self.mode = "MANUAL"
        self.stop_latched = False
        self.motion_authorized = False

    @staticmethod
    def stop():
        return ArbitrationResult("SAFETY", "STOP", 0.0, 0.0)

    def set_motion_authorized(self, authorized):
        if type(authorized) is not bool:
            raise TypeError("Authorization must be boolean")
        self.motion_authorized = authorized
        if not authorized:
            self.mode = "MANUAL"

    def manual_stop(self):
        self.stop_latched = True
        self.mode = "STOP"
        self.motion_authorized = False
        return self.stop()

    def authorize_manual(self):
        if self.stop_latched:
            return False
        self.mode = "MANUAL"
        return True

    def reset_stop(self):
        # Explicit reset only; never performed by AI.
        self.stop_latched = False
        self.motion_authorized = False
        self.mode = "MANUAL"

    def enable_ai(self):
        if self.stop_latched or not self.motion_authorized:
            return False
        self.mode = "AI"
        return True

    def manual_command(self, linear, angular):
        if self.stop_latched:
            return self.stop()

        if not all(
            type(v) in (int, float) and math.isfinite(v)
            for v in (linear, angular)
        ):
            return self.manual_stop()

        if linear == 0 and angular == 0:
            return self.manual_stop()

        if not self.motion_authorized:
            return self.stop()

        self.mode = "MANUAL"
        return ArbitrationResult(
            "MANUAL", "MOVE", linear, angular
        )

    def ai_command(self, command):
        if self.stop_latched:
            return self.stop()

        if self.mode != "AI" or not self.motion_authorized:
            return self.stop()

        if command is None:
            return self.manual_stop()

        try:
            action = command.action
            linear = command.linear
            angular = command.angular
        except AttributeError:
            return self.manual_stop()

        if action == "STOP":
            return self.manual_stop()

        if action not in ("TURN_LEFT", "TURN_RIGHT"):
            return self.manual_stop()

        if (
            type(linear) not in (int, float)
            or type(angular) not in (int, float)
            or not math.isfinite(linear)
            or not math.isfinite(angular)
            or linear != 0
            or not 0 < abs(angular) <= 0.20
        ):
            return self.manual_stop()

        if action == "TURN_LEFT" and angular <= 0:
            return self.manual_stop()

        if action == "TURN_RIGHT" and angular >= 0:
            return self.manual_stop()

        return ArbitrationResult(
            "AI", action, 0.0, angular
        )
