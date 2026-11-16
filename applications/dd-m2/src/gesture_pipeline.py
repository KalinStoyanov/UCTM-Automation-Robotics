import math

from src.gesture_filter import GestureFilter
from src.gesture_controller import GestureController


class GesturePipeline:
    def __init__(self, required=3, timeout=0.5):
        self.filter = GestureFilter(required=required)
        self.controller = GestureController(timeout=timeout)
        self.last_command = None
        self.state = "INITIAL"

    def detect(self, raw_command):
        command = self.filter.update(raw_command)

        if command is not None:
            self.controller.detect(command)
            self.state = "ACTIVE"

        self.last_command = command
        return command

    def step(self, dt):
        if not isinstance(dt, (int, float)):
            raise ValueError("Invalid dt")
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("Invalid dt")

        if self.state == "INITIAL":
            # The robot remains stopped while a gesture
            # is being confirmed for the first time.
            self.controller.time += dt
            self.controller.robot.command("STOP")
            self.controller.timed_out = True
            return

        was_timed_out = self.controller.timed_out

        self.controller.step(dt)

        if self.controller.timed_out and not was_timed_out:
            self.filter.reset()
            self.last_command = None
            self.state = "TIMED_OUT"

    def status(self):
        result = self.controller.status()
        result["filtered_command"] = self.last_command
        result["pipeline_state"] = self.state
        return result
