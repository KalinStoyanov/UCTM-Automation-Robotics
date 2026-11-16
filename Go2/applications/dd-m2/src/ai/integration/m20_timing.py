"""M20: Timing hardening and offline long-run stability."""

import math
import threading
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


def valid_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


class HardenedScheduler:
    def __init__(self, frequency_hz=20.0, tolerance_s=0.005):
        if not valid_number(frequency_hz) or frequency_hz <= 0:
            raise ValueError("Invalid frequency")
        if not valid_number(tolerance_s) or tolerance_s < 0:
            raise ValueError("Invalid tolerance")

        self.period_s = 1.0 / frequency_hz
        if tolerance_s >= self.period_s:
            raise ValueError("Tolerance must be smaller than period")

        self.tolerance_s = tolerance_s
        self.next_release = None
        self.jitter_s = []
        self.deadline_misses = 0

    def tick(self, now):
        if not valid_number(now):
            raise ValueError("Invalid clock")

        if self.next_release is None:
            self.next_release = now

        lateness = now - self.next_release
        missed = max(0, math.floor(
            (lateness + 1e-12) / self.period_s
        ))

        deadline_miss = lateness > self.tolerance_s
        self.deadline_misses += int(deadline_miss)
        self.jitter_s.append(lateness)

        self.next_release += (missed + 1) * self.period_s

        return {
            "lateness_s": lateness,
            "missed_periods": missed,
            "deadline_miss": deadline_miss,
        }


class IndependentWatchdog:
    """Threaded watchdog with independent monotonic timeout."""

    def __init__(self, timeout_s=0.200, poll_s=0.010):
        if not valid_number(timeout_s) or timeout_s <= 0:
            raise ValueError("Invalid timeout")
        if not valid_number(poll_s) or poll_s <= 0:
            raise ValueError("Invalid polling interval")

        self.timeout_s = timeout_s
        self.poll_s = poll_s
        self.lock = threading.Lock()
        self.last_feed = None
        self.tripped = False
        self._stop = threading.Event()
        self._thread = None

    def feed(self, now=None):
        now = time.monotonic() if now is None else now
        if not valid_number(now):
            raise ValueError("Invalid clock")

        with self.lock:
            if self.tripped:
                return False
            self.last_feed = now
            return True

    def check(self, now=None):
        now = time.monotonic() if now is None else now
        if not valid_number(now):
            raise ValueError("Invalid clock")

        with self.lock:
            if self.last_feed is not None:
                if now < self.last_feed or (
                    now - self.last_feed > self.timeout_s
                ):
                    self.tripped = True
            return self.tripped

    def reset(self):
        with self.lock:
            self.last_feed = None
            self.tripped = False

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop.clear()

        def monitor():
            while not self._stop.wait(self.poll_s):
                self.check()

        self._thread = threading.Thread(
            target=monitor, daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None


class M20Runtime:
    """Offline AI runtime with timing and freshness checks."""

    def __init__(
        self,
        model_path="results/m13/neural_policy.npz",
        frequency_hz=20.0,
        tolerance_s=0.005,
        max_frame_age_s=0.150,
    ):
        self.scheduler = HardenedScheduler(
            frequency_hz, tolerance_s
        )
        self.adapter = SensorAdapter()
        self.ai = M16Runtime(model_path=model_path)
        self.max_frame_age_s = max_frame_age_s

        if not valid_number(max_frame_age_s) or max_frame_age_s <= 0:
            raise ValueError("Invalid frame age")

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
            return safe_stop("NO_FRAME"), timing

        if not isinstance(raw_frame, dict):
            self.reset_tracking()
            return safe_stop("INVALID_FRAME"), timing

        timestamp = raw_frame.get("timestamp")

        if not valid_number(timestamp):
            self.reset_tracking()
            return safe_stop("INVALID_TIMESTAMP"), timing

        age = now - timestamp

        if age < 0:
            self.reset_tracking()
            return safe_stop("FUTURE_FRAME"), timing

        if age > self.max_frame_age_s:
            self.reset_tracking()
            return safe_stop("STALE_FRAME"), timing

        try:
            observation = self.adapter.convert(raw_frame)
            result = self.ai.step(observation)
        except (ValueError, TypeError, KeyError, OverflowError):
            self.reset_tracking()
            return safe_stop("RUNTIME_FAILURE"), timing

        if observation is None:
            self.reset_tracking()
            return safe_stop("NO_TARGET"), timing

        return result, timing


def measure_long_run(duration_s=60.0, frequency_hz=20.0):
    scheduler = HardenedScheduler(frequency_hz)
    period = scheduler.period_s
    cycles = int(duration_s * frequency_hz)
    start = time.monotonic()
    measurements = []

    for i in range(cycles):
        target = start + i * period
        remaining = target - time.monotonic()

        if remaining > 0:
            time.sleep(remaining)

        now = time.monotonic()
        timing = scheduler.tick(now)

        measurements.append({
            "cycle": i,
            "lateness_ms": timing["lateness_s"] * 1000,
            "deadline_miss": timing["deadline_miss"],
            "missed_periods": timing["missed_periods"],
        })

    return measurements
