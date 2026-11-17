"""M25 obstacle safety: offline decision layer."""

import math
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Clearance:
    forward: float
    backward: float
    left: float
    right: float
    turn: float


class ObstacleSafetyFilter:
    def __init__(self, stop_distance=0.50, max_age=0.25,
                 clock=time.monotonic):
        if not math.isfinite(stop_distance) or stop_distance <= 0:
            raise ValueError("Invalid stop distance")
        if not math.isfinite(max_age) or max_age <= 0:
            raise ValueError("Invalid maximum age")
        self.stop_distance = stop_distance
        self.max_age = max_age
        self.clock = clock
        self.clearance = None
        self.observed_at = None
        self.state = "WAITING_FOR_SENSOR"

    def observe(self, clearance):
        if not isinstance(clearance, Clearance):
            self.invalidate()
            return False
        if any(not math.isfinite(v) or v < 0
               for v in vars(clearance).values()):
            self.invalidate()
            return False
        self.clearance = clearance
        self.observed_at = self.clock()
        return True

    def invalidate(self):
        self.clearance = None
        self.observed_at = None
        self.state = "SENSOR_FAULT"

    def fresh(self):
        return (
            self.clearance is not None
            and self.observed_at is not None
            and math.isfinite(self.clock() - self.observed_at)
            and 0 <= self.clock() - self.observed_at <= self.max_age
        )

    def safe(self, vx=0.0, vy=0.0, wz=0.0):
        if not all(math.isfinite(v) for v in (vx, vy, wz)):
            return False
        if not self.fresh():
            return False
        c = self.clearance
        checks = (
            (vx > 0, c.forward),
            (vx < 0, c.backward),
            (vy > 0, c.left),
            (vy < 0, c.right),
            (wz != 0, c.turn),
        )
        return all(not active or d > self.stop_distance
                   for active, d in checks)

    def command(self, vx=0.0, vy=0.0, wz=0.0):
        if not all(math.isfinite(v) for v in (vx, vy, wz)):
            raise ValueError("Invalid velocity")
        if vx == vy == wz == 0:
            return (0.0, 0.0, 0.0)
        if not self.safe(vx, vy, wz):
            self.state = (
                "STOPPED_OBSTACLE" if self.fresh()
                else "SENSOR_FAULT"
            )
            return (0.0, 0.0, 0.0)
        self.state = "MOVING"
        return (vx, vy, wz)
