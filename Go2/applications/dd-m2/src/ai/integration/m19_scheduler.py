"""M19: Offline soft real-time scheduler and watchdog."""

import math
import time

from ..contracts.m12 import AIResult
from ..perception.sensor_adapter import SensorAdapter
from .m16_runtime import M16Runtime


def safe_stop(reason):
    return AIResult(
        action="STOP",
        linear_m_s=0.0,
        angular_rad_s=0.0,
        confidence=0.0,
        reason=reason,
    )


class Watchdog:
    def __init__(self, max_frame_age_s=0.150, timeout_s=0.200):
        if not (
            math.isfinite(max_frame_age_s)
            and max_frame_age_s > 0
            and math.isfinite(timeout_s)
            and timeout_s > 0
        ):
            raise ValueError("Invalid watchdog configuration")

        self.max_frame_age_s = max_frame_age_s
        self.timeout_s = timeout_s
        self.last_valid_time = None

    def reset(self):
        self.last_valid_time = None

    def check(self, now, frame_timestamp=None):
        if not math.isfinite(now):
            return "INVALID_CLOCK"

        if frame_timestamp is not None:
            if (
                isinstance(frame_timestamp, bool)
                or not isinstance(frame_timestamp, (int, float))
                or not math.isfinite(frame_timestamp)
            ):
                return "INVALID_TIMESTAMP"

            age = now - frame_timestamp
            if age < 0:
                return "FUTURE_FRAME"
            if age > self.max_frame_age_s:
                return "STALE_FRAME"

        if self.last_valid_time is not None:
            elapsed = now - self.last_valid_time
            if elapsed < 0:
                return "CLOCK_REGRESSION"
            if elapsed > self.timeout_s:
                return "WATCHDOG_TIMEOUT"

        return None

    def feed(self, now):
        if not math.isfinite(now):
            raise ValueError("Invalid clock")
        self.last_valid_time = now


class PeriodicScheduler:
    def __init__(self, frequency_hz=20.0):
        if not math.isfinite(frequency_hz) or frequency_hz <= 0:
            raise ValueError("Invalid frequency")

        self.period_s = 1.0 / frequency_hz
        self.next_deadline = None
        self.jitter_s = []
        self.deadline_misses = 0

    def reset(self):
        self.next_deadline = None
        self.jitter_s.clear()
        self.deadline_misses = 0

    def tick(self, now):
        if not math.isfinite(now):
            raise ValueError("Invalid clock")

        if self.next_deadline is None:
            self.next_deadline = now

        lateness = now - self.next_deadline
        self.jitter_s.append(lateness)

        missed = max(
            0,
            math.floor(max(0.0, lateness) / self.period_s + 1e-9),
        )

        self.deadline_misses += missed
        self.next_deadline += (missed + 1) * self.period_s

        return {
            "lateness_s": lateness,
            "missed_periods": missed,
            "deadline_miss": lateness > 1e-9,
        }


class M19Runtime:
    def __init__(
        self,
        model_path="results/m13/neural_policy.npz",
        frequency_hz=20.0,
        max_frame_age_s=0.150,
        watchdog_timeout_s=0.200,
    ):
        self.scheduler = PeriodicScheduler(frequency_hz)
        self.watchdog = Watchdog(
            max_frame_age_s, watchdog_timeout_s
        )
        self.adapter = SensorAdapter()
        self.ai = M16Runtime(model_path=model_path)

    def reset_tracking(self):
        self.adapter.reset()
        self.ai.reset_tracking()

    def step(self, raw_frame, now):
        timing = self.scheduler.tick(now)

        if timing["deadline_miss"]:
            self.reset_tracking()
            return safe_stop("DEADLINE_MISS"), timing

        if raw_frame is None:
            self.reset_tracking()
            reason = self.watchdog.check(now)
            return safe_stop(reason or "NO_FRAME"), timing

        if not isinstance(raw_frame, dict):
            self.reset_tracking()
            return safe_stop("INVALID_FRAME"), timing

        reason = self.watchdog.check(
            now, raw_frame.get("timestamp")
        )

        if reason is not None:
            self.reset_tracking()
            return safe_stop(reason), timing

        try:
            observation = self.adapter.convert(raw_frame)
            result = self.ai.step(observation)
        except (ValueError, TypeError, KeyError):
            self.reset_tracking()
            return safe_stop("ADAPTER_FAILURE"), timing

        if observation is None:
            self.reset_tracking()
            return safe_stop("NO_TARGET"), timing

        if result.action != "STOP":
            self.watchdog.feed(now)

        return result, timing


def run_periodic_measurement(cycles=20, frequency_hz=20.0):
    scheduler = PeriodicScheduler(frequency_hz)
    period = scheduler.period_s
    start = time.monotonic()
    records = []

    for i in range(cycles):
        target = start + i * period
        remaining = target - time.monotonic()

        if remaining > 0:
            time.sleep(remaining)

        actual = time.monotonic()
        timing = scheduler.tick(actual)

        records.append({
            "cycle": i,
            "lateness_ms": timing["lateness_s"] * 1000,
            "missed_periods": timing["missed_periods"],
            "deadline_miss": timing["deadline_miss"],
        })

    return records
