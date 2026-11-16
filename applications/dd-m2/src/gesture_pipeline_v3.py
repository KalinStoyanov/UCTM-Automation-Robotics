import math

from src.gesture_filter import GestureFilter
from src.gesture_controller import GestureController


class GesturePipeline:
    def __init__(self, required=3, timeout=0.5):
        self.filter = GestureFilter(required=required)
        self.controller = GestureController(timeout=timeout)
        self.last_command = None
        self.timeout_handled = False

    def detect(self, raw_command):
        command = self.filter.update(raw_command)

        if command is not None:
            self.controller.detect(command)
            self.timeout_handled = False

        self.last_command = command
        return command

    def step(self, dt):
        if not isinstance(dt, (int, float)):
            raise ValueError("Invalid dt")
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("Invalid dt")

        self.controller.step(dt)

        if self.controller.timed_out and not self.timeout_handled:
            self.filter.reset()
            self.last_command = None
            self.timeout_handled = True

    def status(self):
        result = self.controller.status()
        result["filtered_command"] = self.last_command
        return result
