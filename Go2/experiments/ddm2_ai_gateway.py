"""Offline execution gateway for DD-M2 AI.

Accepts arbitration results and writes to an injected
execution interface. Does not import robot transport.
"""

import math


class AIExecutionGateway:
    def __init__(self, executor):
        self.executor = executor
        self.stop_latched = True

    def authorize(self):
        self.stop_latched = False

    def stop(self):
        self.stop_latched = True
        self.executor(0.0, 0.0)
        return "STOP"

    def execute(self, result):
        if result is None:
            return self.stop()

        try:
            action = result.action
            source = result.source
            linear = result.linear
            angular = result.angular
        except AttributeError:
            return self.stop()

        if action == "STOP":
            return self.stop()

        if self.stop_latched:
            return "BLOCKED"

        if (
            source != "AI"
            or action not in ("TURN_LEFT", "TURN_RIGHT")
            or type(linear) not in (int, float)
            or type(angular) not in (int, float)
            or not math.isfinite(linear)
            or not math.isfinite(angular)
            or linear != 0.0
            or not 0 < abs(angular) <= 0.20
        ):
            return self.stop()

        if (
            (action == "TURN_LEFT" and angular <= 0)
            or (action == "TURN_RIGHT" and angular >= 0)
        ):
            return self.stop()

        self.executor(0.0, angular)
        return "EXECUTED"
