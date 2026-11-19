"""Follow mode ("Следване"): keep the largest person centered and at a set distance.

Upper layer only: it calls robot.set_velocity() / robot.stop(), exactly like the keyboard.
All safety below it (speed caps, 300 ms deadman, BalanceStand rule) still applies.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

log = logging.getLogger("go2.follow")

# ============================ tunables ============================
# Tuned for the Go2 front camera, which sits low: a person fills the frame much sooner
# than on a webcam. K_YAW, K_X, TARGET_H, MAX_VX and MAX_YAW can also be changed live from
# the sliders in the AI panel (within LIMITS).
DEFAULTS = {
    "k_yaw": 1.2,      # rad/s per unit of horizontal error (box center - 0.5)
    "k_x": 2.5,        # m/s per unit of height error: a person at ~3 m (box ~0.5, estimate) -> ~max speed
    "target_h": 0.75,  # desired person box height / frame height
    "max_vx": 0.60,    # m/s, forward only (never backwards)
    "max_yaw": 0.60,   # rad/s
}
LIMITS = {
    "k_yaw": (0.2, 3.0),
    "k_x": (0.5, 5.0),
    "target_h": (0.50, 0.90),
    "max_vx": (0.25, 0.60),
    "max_yaw": (0.0, 0.60),
}
YAW_DEADZONE = 0.05    # |box center - 0.5| below this -> no turning
TOO_CLOSE_H = 0.92     # box height ratio above this -> vx = 0
EDGE = 0.02            # box within this of both the top and bottom edge -> too close as well
MIN_VX = 0.25          # m/s: whenever it moves forward, at least this (slower = shuffling, no steps)
X_DEADZONE = 0.03      # height error below this -> no forward motion (avoids 0.25 m/s creeping at target)
LOST_TIMEOUT = 0.5     # s without the target -> switch target / stop once
IOU_MIN = 0.3          # same target between frames if IoU >= this
PERSON_CONF = 0.5
RATE_HZ = 10.0
SLOW_FPS = 5.0         # detector slower than this -> warning + vx cap
SLOW_MAX_VX = MIN_VX   # slow detector -> only the minimum forward speed
ACTION_PAUSE = 4.0     # s: do not command motion right after an action (e.g. Hello from a gesture)
# ==================================================================


def clamp_config(cfg: dict[str, Any]) -> dict[str, float]:
    out = dict(DEFAULTS)
    for k, (lo, hi) in LIMITS.items():
        if k in cfg:
            try:
                out[k] = min(hi, max(lo, float(cfg[k])))
            except (TypeError, ValueError):
                pass
    return out


def is_too_close(h: float, y1: float | None = None, y2: float | None = None) -> bool:
    """Box taller than TOO_CLOSE_H, or touching both the top and the bottom edge."""
    touches = y1 is not None and y2 is not None and y1 <= EDGE and y2 >= 1.0 - EDGE
    return h > TOO_CLOSE_H or touches


def control(cx: float, h: float, cfg: dict[str, float], slow: bool = False,
            y1: float | None = None, y2: float | None = None) -> tuple[float, float]:
    """Box center x (0..1), height ratio (0..1) and optional top/bottom edges -> (vx, vyaw)."""
    ex = cx - 0.5
    if abs(ex) <= YAW_DEADZONE:
        vyaw = 0.0
    else:
        vyaw = max(-cfg["max_yaw"], min(cfg["max_yaw"], -cfg["k_yaw"] * ex))
    err = cfg["target_h"] - h
    if is_too_close(h, y1, y2) or err <= X_DEADZONE:
        vx = 0.0
    else:
        vx = min(cfg["max_vx"], max(MIN_VX, cfg["k_x"] * err))
    if slow:
        vx = min(vx, SLOW_MAX_VX)
    return round(vx, 3), round(vyaw, 3)


def iou(a, b) -> float:
    ix = max(0.0, min(a.x2, b.x2) - max(a.x1, b.x1))
    iy = max(0.0, min(a.y2, b.y2) - max(a.y1, b.y1))
    inter = ix * iy
    union = a.area + b.area - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Command:
    kind: str                 # "move" | "stop" | "idle"
    vx: float = 0.0
    vyaw: float = 0.0
    status: str = "searching"  # locked | too_close | searching


class FollowController:
    """Pure logic (no threads, no robot): feed detections, call tick() at 10 Hz."""

    def __init__(self, cfg: dict[str, float] | None = None) -> None:
        self.cfg = clamp_config(cfg or {})
        self.reset(0.0)

    def reset(self, now: float) -> None:
        self.target = None
        self.target_seen = float("-inf")
        self.started = now
        self.stopped = False
        self.persons: list = []
        self.det_t = float("-inf")
        self.last_cmd = Command("idle")

    def on_detections(self, persons: list, t: float) -> None:
        self.persons, self.det_t = persons, t
        if self.target is not None and persons:
            best = max(persons, key=lambda p: iou(self.target, p))
            if iou(self.target, best) >= IOU_MIN:
                self.target, self.target_seen = best, t
        self._maybe_switch(t)

    def _maybe_switch(self, now: float) -> None:
        """Keep the target while it was seen within LOST_TIMEOUT; after that switch to the
        largest person currently visible, or drop the target if nobody is visible."""
        if self.target is not None and now - self.target_seen <= LOST_TIMEOUT:
            return
        if self.persons and now - self.det_t <= LOST_TIMEOUT:
            if self.target is not None:
                log.info("FOLLOW target lost %.1f s -> switching to largest person", LOST_TIMEOUT)
            self.target, self.target_seen = max(self.persons, key=lambda p: p.area), self.det_t
        else:
            self.target = None

    def tick(self, now: float, slow: bool = False) -> Command:
        self._maybe_switch(now)  # the tick may notice the loss before the next detection does
        if self.target is not None:
            # within 0.5 s of the last sighting we keep the last known box (coast)
            t = self.target
            vx, vyaw = control(t.cx, t.h, self.cfg, slow, t.y1, t.y2)
            self.stopped = False
            status = "too_close" if is_too_close(t.h, t.y1, t.y2) else "locked"
            self.last_cmd = Command("move", vx, vyaw, status)
            return self.last_cmd
        # nobody visible and the target gone for > 0.5 s (or nobody since enabling)
        if not self.stopped and now - max(self.target_seen, self.started) > LOST_TIMEOUT:
            self.stopped = True
            self.last_cmd = Command("stop", status="searching")
            return self.last_cmd
        self.last_cmd = Command("idle", status="searching")
        return self.last_cmd


STATUS_BG = {"locked": "Целта е заключена", "too_close": "Твърде близо", "searching": "Търся човек…"}


class FollowMode:
    def __init__(self, robot, detector) -> None:
        self.robot = robot
        self.detector = detector
        self.ctrl = FollowController()
        self._lock = threading.Lock()  # guards enable/disable vs. commanding
        self._enabled = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._paused = False
        self._slow = False
        self._commanding = False
        self._log_at = 0.0
        self._seen_seq = -1
        self.last_disable: dict[str, Any] | None = None
        self.on_disabled = None  # callback(reason) set by the app (UI notice)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def cfg(self) -> dict[str, float]:
        return self.ctrl.cfg

    def update_config(self, values: dict[str, Any]) -> dict[str, float]:
        merged = dict(self.ctrl.cfg)
        merged.update({k: v for k, v in values.items() if k in LIMITS})
        self.ctrl.cfg = clamp_config(merged)
        log.info("FOLLOW config %s", self.ctrl.cfg)
        return self.ctrl.cfg

    def set_enabled(self, on: bool, reason: str = "toggle") -> None:
        if on:
            self.enable()
        else:
            self.disable(reason)

    def enable(self) -> None:
        with self._lock:
            if self._enabled:
                return
            self.ctrl.reset(time.monotonic())
            self._enabled = True
            self._commanding = False
            self.last_disable = None
        self.detector.acquire("follow")
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="follow", daemon=True)
            self._thread.start()
        log.info("FOLLOW ON")

    def disable(self, reason: str = "toggle") -> bool:
        """reason: toggle | manual | gesture | no_client. Returns True if it was enabled."""
        with self._lock:
            if not self._enabled:
                return False
            self._enabled = False
            was_commanding = self._commanding
            self._commanding = False
            self.last_disable = {"reason": reason, "at": time.time()}
            # Manual input takes over directly (its own velocity / StopMove follows),
            # every other reason stops the robot once here.
            if reason != "manual" and was_commanding:
                self.robot.stop(note="Следването е изключено → стоп")
        self.detector.release("follow")
        log.info("FOLLOW OFF (%s)", reason)
        if self.on_disabled:
            try:
                self.on_disabled(reason)
            except Exception:  # noqa: BLE001
                log.exception("on_disabled")
        return True

    def close(self) -> None:
        self._stop.set()

    def state(self) -> dict[str, Any]:
        c = self.ctrl.last_cmd
        status = c.status
        if self._enabled and not self.detector.ready:
            status = "loading"
        elif self._enabled and self._paused:
            status = "paused"
        fps = self.detector.fps if self._enabled else 0.0
        return {
            "enabled": self._enabled,
            "ready": self.detector.ready,
            "status": status if self._enabled else "off",
            "vx": c.vx if self._enabled and c.kind == "move" else 0.0,
            "vyaw": c.vyaw if self._enabled and c.kind == "move" else 0.0,
            "fps": fps,
            "slow": self._enabled and self._slow,
            "persons": len(self.ctrl.persons) if self._enabled else 0,
            "config": self.ctrl.cfg,
            "limits": LIMITS,
            "last_disable": self.last_disable,
            "error": self.detector.error,
        }

    # ---------- worker ----------
    def _run(self) -> None:
        period = 1.0 / RATE_HZ
        next_t = time.monotonic()
        while not self._stop.is_set():
            next_t += period
            time.sleep(max(0.0, next_t - time.monotonic()))
            if time.monotonic() - next_t > period:
                next_t = time.monotonic()
            try:
                self._tick()
            except Exception:  # noqa: BLE001
                log.exception("follow tick")

    def _tick(self) -> None:
        with self._lock:
            if not self._enabled:
                return
            now = time.monotonic()
            det = self.detector.latest()
            if det.seq != self._seen_seq:
                self._seen_seq = det.seq
                self.ctrl.on_detections(det.persons(PERSON_CONF), det.t)
            # warn only once the model runs; while it loads there are simply no detections
            self._slow = self.detector.ready and now - self.ctrl.started > 1.5 and self.detector.fps < SLOW_FPS
            cmd = self.ctrl.tick(now, self._slow)
            self._paused = now - getattr(self.robot, "last_action_at", 0.0) < ACTION_PAUSE
            if self._paused:
                return  # the action already stopped the robot; let it finish
            if cmd.kind == "move":
                self.robot.set_velocity(cmd.vx, 0.0, cmd.vyaw)
                self._commanding = True
            elif cmd.kind == "stop":
                self.robot.stop(note="Следване: няма човек → стоп")
                self._commanding = False
                log.info("FOLLOW no person for %.1f s -> stop", LOST_TIMEOUT)
        if now - self._log_at >= 1.0:
            self._log_at = now
            t = self.ctrl.target
            log.info("FOLLOW %-9s %s -> vx=%.2f vyaw=%+.2f (AI %.0f fps%s)", cmd.status,
                     f"cx={t.cx:.2f} h={t.h:.2f}" if t else "no target  ",
                     cmd.vx, cmd.vyaw, self.detector.fps, ", SLOW" if self._slow else "")

    # ---------- overlay ----------
    def draw(self, img: np.ndarray) -> None:
        if not self._enabled:
            return
        h, w = img.shape[:2]
        k = max(0.45, w / 1280)
        target = self.ctrl.target
        cyan, dim, amber = (242, 208, 63), (120, 120, 120), (61, 179, 242)
        for p in self.ctrl.persons:
            if target is not None and p == target:
                continue
            cv2.rectangle(img, (int(p.x1 * w), int(p.y1 * h)), (int(p.x2 * w), int(p.y2 * h)), dim, max(1, int(k)), cv2.LINE_AA)
        if target is not None:
            p1, p2 = (int(target.x1 * w), int(target.y1 * h)), (int(target.x2 * w), int(target.y2 * h))
            cv2.rectangle(img, p1, p2, cyan, max(2, int(3 * k)), cv2.LINE_AA)
            self._label(img, "TARGET", (p1[0], p1[1]), cyan, k)
        # command arrow from bottom center: length ~ vx, tilt ~ vyaw (left = positive)
        c = self.ctrl.last_cmd
        vx, vyaw = (c.vx, c.vyaw) if c.kind == "move" else (0.0, 0.0)
        ox, oy = w // 2, int(h * 0.86)
        cv2.circle(img, (ox, oy), max(3, int(6 * k)), (245, 240, 235), -1, cv2.LINE_AA)
        if vx > 0 or vyaw != 0:
            ang = -(vyaw / max(DEFAULTS["max_yaw"], 1e-6)) * np.radians(70)
            length = h * (0.07 + 0.22 * vx / DEFAULTS["max_vx"])
            ex, ey = int(ox + length * np.sin(ang)), int(oy - length * np.cos(ang))
            cv2.arrowedLine(img, (ox, oy), (ex, ey), cyan, max(2, int(5 * k)), cv2.LINE_AA, tipLength=0.25)
        status = {"locked": "LOCKED", "too_close": "TOO CLOSE", "searching": "SEARCHING"}.get(c.status, c.status.upper())
        text = f"FOLLOW {status}  vx {vx:.2f}  w {vyaw:+.2f}  AI {self.detector.fps:.0f} fps"
        # top-right: the bottom corners are covered by the joysticks in the UI
        self._label(img, text, (w - int(16 * k), int(52 * k)), cyan if c.status == "locked" else (230, 230, 230), k, right=True)
        if self._slow:
            self._label(img, f"AI SLOW (<{SLOW_FPS:.0f} fps): vx <= {SLOW_MAX_VX}", (w - int(16 * k), int(96 * k)), amber, k, right=True)

    @staticmethod
    def _label(img, text, org, color, k, right=False) -> None:
        fs, t = 0.6 * k, max(1, int(2 * k))
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, fs, t)
        pad = int(6 * k)
        x, y = org
        if right:
            x -= tw + 2 * pad
        cv2.rectangle(img, (x, y - th - 2 * pad), (x + tw + 2 * pad, y), (20, 16, 12), -1)
        cv2.putText(img, text, (x + pad, y - pad), cv2.FONT_HERSHEY_SIMPLEX, fs, color, t, cv2.LINE_AA)
