from src.gesture_filter import GestureFilter
from src.gesture_controller import GestureController


class GesturePipeline:
    def __init__(self, required=3, timeout=0.5):
        self.filter = GestureFilter(required=required)
        self.controller = GestureController(timeout=timeout)
        self.last_command = None

    def detect(self, raw_command):
        command = self.filter.update(raw_command)

        if command is not None:
            self.controller.detect(command)

        self.last_command = command
        return command

    def step(self, dt):
        # Allow initial gesture confirmation before the
        # controller has received its first valid command.
        if self.controller.last_detection is None:
            if not isinstance(dt, (int, float)) or dt <= 0:
                raise ValueError("Invalid dt")

            import math
            if not math.isfinite(dt):
                raise ValueError("Invalid dt")

            self.controller.time += dt
            self.controller.robot.command("STOP")
            return

        self.controller.step(dt)

        if self.controller.timed_out:
            self.filter.reset()
            self.last_command = None

    def status(self):
        result = self.controller.status()
        result["filtered_command"] = self.last_command
        return result
