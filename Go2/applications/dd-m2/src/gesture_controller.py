import math

from src.kinematic_simulator import KinematicSimulator


class GestureController:
    def __init__(self, timeout=0.5):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Invalid timeout")

        self.robot = KinematicSimulator()
        self.timeout = timeout
        self.time = 0.0
        self.last_detection = None
        self.active_gesture = None
        self.timed_out = False

    def detect(self, command):
        if command == "STOP":
            self.robot.command("STOP")
            self.active_gesture = "STOP"
            self.last_detection = self.time
            self.timed_out = False
            return

        if command in (
            "FORWARD",
            "BACKWARD",
            "TURN_LEFT_90",
            "TURN_RIGHT_90",
        ):
            self.last_detection = self.time

            if self.timed_out:
                self.active_gesture = None
                self.timed_out = False

            if command != self.active_gesture:
                self.robot.command(command)
                self.active_gesture = command

    def step(self, dt):
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("Invalid dt")

        # Split at the timeout boundary so motion cannot
        # continue beyond the allowed detection interval.
        remaining = dt

        while remaining > 1e-12:
            if self.last_detection is None:
                self.robot.command("STOP")
                self.timed_out = True
                self.time += remaining
                break

            deadline = self.last_detection + self.timeout

            if self.time >= deadline - 1e-12:
                self.robot.command("STOP")
                self.timed_out = True
                self.time += remaining
                break

            chunk = min(remaining, deadline - self.time)
            self.robot.step(chunk)
            self.time += chunk
            remaining -= chunk

            if self.time >= deadline - 1e-12:
                self.robot.command("STOP")
                self.timed_out = True

    def status(self):
        result = self.robot.status()
        result["time_s"] = round(self.time, 3)
        result["timed_out"] = self.timed_out
        return result
