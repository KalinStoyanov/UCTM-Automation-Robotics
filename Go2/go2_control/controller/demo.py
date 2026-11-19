""""Демо" sequence: Hello -> Stretch -> Sit -> RiseSit.

Upper layer: only calls robot.action(). Never sends Move. Each step starts after the
previous command replied (or timed out) plus a pause for the motion. Any manual input
cancels it immediately (wired in app.py).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from .timing import ACTION_WAIT

log = logging.getLogger("go2.demo")

# ============================ tunables ============================
# (SPORT_CMD name, pause in seconds after the reply, for the motion to finish).
# The pauses come from the shared table in controller/timing.py (also used by the
# automatic posture transitions): tune them there.
STEPS = [(n, ACTION_WAIT[n]) for n in ("Hello", "Stretch", "Sit", "RiseSit")]
CHAIN_WAIT = 60.0  # s: max wait for one step incl. auto-inserted posture steps (reply timeout is 1 s)
# ==================================================================


class DemoSequence:
    def __init__(self, robot, steps=None) -> None:
        self.robot = robot
        self.steps = [(n, p) for n, p in (steps or STEPS) if n in robot.allowed]
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._state: dict[str, Any] = {"running": False, "step": -1, "phase": "idle", "result": None}
        self.on_change = None  # callback() set by the app (push UI update)

    @property
    def running(self) -> bool:
        return self._state["running"]

    def state(self) -> dict[str, Any]:
        with self._lock:
            st = dict(self._state)
        st["steps"] = [n for n, _ in self.steps]
        return st

    def start(self) -> bool:
        with self._lock:
            if self._state["running"]:
                return False
            self._cancel.clear()
            self._state = {"running": True, "step": -1, "phase": "starting", "result": None}
            self._thread = threading.Thread(target=self._run, name="demo", daemon=True)
            self._thread.start()
        log.info("DEMO start: %s", " -> ".join(n for n, _ in self.steps))
        self._event("Демо: старт")
        return True

    def cancel(self, reason: str = "manual") -> bool:
        """Immediate: after this returns, the sequence sends nothing more."""
        with self._lock:
            if not self._state["running"]:
                return False
            self._cancel.set()
            self._state.update(running=False, phase="cancelled", result=reason)
        log.info("DEMO cancelled (%s)", reason)
        self._event("Демо: прекъснато", "warn")
        self._changed()
        return True

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def _changed(self) -> None:
        if self.on_change:
            try:
                self.on_change()
            except Exception:  # noqa: BLE001
                log.exception("demo on_change")

    def _set(self, **kw) -> bool:
        with self._lock:
            if self._cancel.is_set():
                return False
            self._state.update(kw)
        self._changed()
        return True

    def _run(self) -> None:
        for i, (name, pause) in enumerate(self.steps):
            # send only if not cancelled; checked under the same lock cancel() takes
            with self._lock:
                if self._cancel.is_set():
                    return
                self._state.update(step=i, phase="sending")
                fut = self.robot.action(name)
            self._changed()
            deadline = time.monotonic() + CHAIN_WAIT
            while not fut.done() and time.monotonic() < deadline:
                if self._cancel.wait(0.02):
                    return
            code = fut.result() if fut.done() else "timeout"
            log.info("DEMO step %d/%d %s -> code=%s, pause %.1f s", i + 1, len(self.steps), name, code, pause)
            if not self._set(phase="waiting"):
                return
            if self._cancel.wait(pause):
                return
        with self._lock:
            if self._cancel.is_set():
                return
            self._state.update(running=False, phase="done", result="done")
        log.info("DEMO done")
        self._event("Демо: готово", "ok")
        self._changed()

    def _event(self, text: str, level: str = "info") -> None:
        events = getattr(self.robot, "events", None)
        if events is not None:
            events.add(text, level)
