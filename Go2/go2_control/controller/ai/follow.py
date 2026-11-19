"""Follow mode ("Следване"): follow a person who asks for it.

Enabling the mode only ARMS it. It locks onto a person after that person holds ONE arm
above the head for ~1 s, then keeps that person centered and at a set distance. It stops
following (back to armed) when the target holds BOTH arms above the head for ~1 s, shows
an open palm (needs Жестове), or is lost for 2 s. СТОП / manual input turn the mode off.

Upper layer only: it calls robot.set_velocity() / robot.stop(), exactly like the keyboard.
All safety below it (speed caps, 300 ms deadman, BalanceStand rule) still applies.
Turning the mode on also switches on the robot's built-in obstacle avoidance
(robot.set_avoidance); if the robot refuses it, the mode runs and is shown "без избягване".
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
LOST_TIMEOUT = 2.0     # s without the target while following -> stop once ("Спрях")
STALE = 0.4            # s without a fresh sighting -> stand still (no blind driving)
RAISE_HOLD = 1.0       # s with ONE arm above the head -> lock onto that person
STOP_HOLD = 1.0        # s with BOTH arms above the head -> stop following
STOPPED_SHOW = 2.0     # s "Спрях" stays on screen, then the mode is armed again
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
    status: str = "armed"     # armed | following | too_close | stopped


@dataclass
class Track:
    box: Any
    since: float | None = None   # when ONE arm went up (armed state)


ARMED, FOLLOWING, STOPPED = "armed", "following", "stopped"


class FollowController:
    """Pure logic (no threads, no robot): feed detections (person boxes with .arms =
    number of arms above the head, or None if the pose is unknown), call tick() at 10 Hz."""

    def __init__(self, cfg: dict[str, float] | None = None) -> None:
        self.cfg = clamp_config(cfg or {})
        self.reset(0.0)

    def reset(self, now: float) -> None:
        self.state = ARMED
        self.tracks: list[Track] = []
        self.target = None
        self.target_seen = float("-inf")
        self.both_since: float | None = None
        self.stopped_at = float("-inf")
        self.stop_reason = ""
        self._pending_stop: str | None = None
        self.started = now
        self.persons: list = []
        self.det_t = float("-inf")
        self.last_cmd = Command("idle")
        self.events: list[str] = []  # "lock" / "stop:<reason>", drained by FollowMode

    # ---- inputs ----
    def on_detections(self, persons: list, t: float) -> None:
        self.persons, self.det_t = persons, t
        if self.state == FOLLOWING:
            self._update_target(persons, t)
        elif self.state == ARMED:
            self._update_candidates(persons, t)

    def stop_following(self, reason: str) -> None:
        """External stop (open palm). Applied on the next tick."""
        if self.state == FOLLOWING:
            self._pending_stop = reason

    def _update_candidates(self, persons: list, t: float) -> None:
        tracks = []
        for p in persons:
            prev = max(self.tracks, key=lambda tr: iou(tr.box, p), default=None)
            prev = prev if prev is not None and iou(prev.box, p) >= IOU_MIN else None
            if p.arms == 1:
                since = prev.since if prev is not None and prev.since is not None else t
            elif p.arms is None and prev is not None:
                since = prev.since  # pose unknown this frame: neither start nor reset
            else:
                since = None
            tracks.append(Track(p, since))
        self.tracks = tracks
        ready = [tr for tr in tracks if tr.since is not None and t - tr.since >= RAISE_HOLD]
        if ready:
            first = min(ready, key=lambda tr: tr.since)
            self.state, self.target, self.target_seen = FOLLOWING, first.box, t
            self.both_since, self.tracks = None, []
            self.events.append("lock")

    def _update_target(self, persons: list, t: float) -> None:
        best = max(persons, key=lambda p: iou(self.target, p), default=None)
        if best is None or iou(self.target, best) < IOU_MIN:
            return  # someone else raising an arm does not matter while following
        self.target, self.target_seen = best, t
        if best.arms == 2:
            self.both_since = self.both_since if self.both_since is not None else t
            if t - self.both_since >= STOP_HOLD:
                self._pending_stop = "both_arms"
        elif best.arms is not None:
            self.both_since = None

    def raise_progress(self, now: float) -> float:
        """0..1: how far the best candidate is into the 1 s one-arm hold (armed state)."""
        sinces = [tr.since for tr in self.tracks if tr.since is not None]
        return 0.0 if not sinces else min(1.0, (now - min(sinces)) / RAISE_HOLD)

    # ---- output ----
    def tick(self, now: float, slow: bool = False) -> Command:
        if self.state == STOPPED:
            if now - self.stopped_at >= STOPPED_SHOW:
                self.state, self.tracks = ARMED, []
            else:
                self.last_cmd = Command("idle", status="stopped")
                return self.last_cmd
        if self.state == ARMED:
            self.last_cmd = Command("idle", status="armed")
            return self.last_cmd
        # FOLLOWING
        reason = self._pending_stop or ("lost" if now - self.target_seen > LOST_TIMEOUT else None)
        if reason:
            self._pending_stop = None
            self.state, self.stopped_at, self.stop_reason = STOPPED, now, reason
            self.target, self.both_since = None, None
            self.events.append(f"stop:{reason}")
            self.last_cmd = Command("stop", status="stopped")
            return self.last_cmd
        t = self.target
        too_close = is_too_close(t.h, t.y1, t.y2)
        if now - self.target_seen > STALE:
            vx, vyaw = 0.0, 0.0  # not seen right now: stand still, do not drive blind
        else:
            vx, vyaw = control(t.cx, t.h, self.cfg, slow, t.y1, t.y2)
        self.last_cmd = Command("move", vx, vyaw, "too_close" if too_close else "following")
        return self.last_cmd


STOP_REASON_BG = {"both_arms": "двете ръце горе", "palm": "длан", "lost": "изгубих те"}


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
        self._last_vel = (0.0, 0.0)
        self._log_at = 0.0
        self._seen_seq = -1
        self.last_disable: dict[str, Any] | None = None
        self.on_disabled = None  # callback(reason) set by the app (UI notice)
        self.on_change = None    # callback() on armed/following/stopped changes (UI refresh)
        self._phase = ARMED

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def following(self) -> bool:
        return self._enabled and self.ctrl.state == FOLLOWING

    def stop_following(self, reason: str = "palm") -> None:
        with self._lock:
            self.ctrl.stop_following(reason)

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
        self.detector.acquire("follow", pose=True)
        set_avoidance = getattr(self.robot, "set_avoidance", None)
        if set_avoidance is not None:
            set_avoidance(True, "follow")  # result shown via avoid_status(); never blocks here
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
        now = time.monotonic()
        avoid = self._avoid()
        return {
            "phase": self.ctrl.state if self._enabled else "off",
            "raise_progress": round(self.ctrl.raise_progress(now), 2) if self._enabled else 0.0,
            "stop_reason": STOP_REASON_BG.get(self.ctrl.stop_reason, "") if self.ctrl.state == STOPPED else "",
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
            "avoid": avoid,   # robot avoidance state: "on" | "enabling" | "failed" | "off" | None
        }

    def _avoid(self) -> str | None:
        status = getattr(self.robot, "avoid_status", None)
        return status()["state"] if status is not None else None

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
            if self.ctrl.state != self._phase:
                self._phase = self.ctrl.state
                if self.on_change:
                    try:
                        self.on_change()
                    except Exception:  # noqa: BLE001
                        log.exception("follow on_change")
            for ev in self.ctrl.events:
                if ev == "lock":
                    avoid = self._avoid()
                    if avoid == "on":
                        log.info("FOLLOW lock: one arm raised %.1f s (obstacle avoidance on)", RAISE_HOLD)
                        self._event("Следване: вдигната ръка, следвам (с избягване)", "ok")
                    else:
                        log.warning("FOLLOW lock: one arm raised %.1f s, WITHOUT obstacle avoidance (%s)",
                                    RAISE_HOLD, avoid)
                        self._event("Следване: следвам БЕЗ избягване на препятствия", "danger")
            self.ctrl.events.clear()
            if cmd.kind == "stop":  # always honoured, even during an action pause
                why = STOP_REASON_BG.get(self.ctrl.stop_reason, self.ctrl.stop_reason)
                log.info("FOLLOW stop (%s)", self.ctrl.stop_reason)
                if self._commanding and self._last_vel != (0.0, 0.0):
                    self.robot.stop(note=f"Следване: спрях ({why})")
                else:  # already standing still (zero velocity sent its StopMove): just log
                    self._event(f"Следване: спрях ({why})")
                self._commanding, self._last_vel = False, (0.0, 0.0)
                return
            self._paused = now - getattr(self.robot, "last_action_at", 0.0) < ACTION_PAUSE
            if self._paused:
                return  # the action already stopped the robot; let it finish
            if cmd.kind == "move":
                self.robot.set_velocity(cmd.vx, 0.0, cmd.vyaw)
                self._commanding, self._last_vel = True, (cmd.vx, cmd.vyaw)
        if now - self._log_at >= 1.0:
            self._log_at = now
            t = self.ctrl.target
            log.info("FOLLOW %-9s %s -> vx=%.2f vyaw=%+.2f (AI %.0f fps%s)", cmd.status,
                     f"cx={t.cx:.2f} h={t.h:.2f}" if t else "no target  ",
                     cmd.vx, cmd.vyaw, self.detector.fps, ", SLOW" if self._slow else "")

    def _event(self, text: str, level: str = "info") -> None:
        events = getattr(self.robot, "events", None)
        if events is not None:
            events.add(text, level)

    # ---------- overlay ----------
    def draw(self, img: np.ndarray) -> None:
        if not self._enabled:
            return
        h, w = img.shape[:2]
        k = max(0.45, w / 1280)
        cyan, dim, amber, white = (242, 208, 63), (120, 120, 120), (61, 179, 242), (235, 235, 235)
        ctrl, now = self.ctrl, time.monotonic()
        target = ctrl.target if ctrl.state == FOLLOWING else None
        candidates = {id(tr.box): tr for tr in ctrl.tracks} if ctrl.state == ARMED else {}
        for p in ctrl.persons:
            if target is not None and p == target:
                continue
            p1, p2 = (int(p.x1 * w), int(p.y1 * h)), (int(p.x2 * w), int(p.y2 * h))
            cv2.rectangle(img, p1, p2, dim, max(1, int(k)), cv2.LINE_AA)
            self._draw_arms(img, p, dim, k)
            tr = candidates.get(id(p))
            if tr is not None and tr.since is not None:  # one arm up: show the 1 s hold filling
                frac = min(1.0, (now - tr.since) / RAISE_HOLD)
                bw = p2[0] - p1[0]
                cv2.rectangle(img, (p1[0], p1[1] - int(10 * k)), (p1[0] + int(bw * frac), p1[1] - int(4 * k)), cyan, -1)
        if target is not None:
            p1, p2 = (int(target.x1 * w), int(target.y1 * h)), (int(target.x2 * w), int(target.y2 * h))
            cv2.rectangle(img, p1, p2, cyan, max(2, int(3 * k)), cv2.LINE_AA)
            self._draw_arms(img, target, cyan, k)
            self._label(img, "TARGET", (p1[0], p1[1]), cyan, k)
        # command arrow from bottom center: length ~ vx, tilt ~ vyaw (left = positive)
        c = ctrl.last_cmd
        vx, vyaw = (c.vx, c.vyaw) if c.kind == "move" else (0.0, 0.0)
        if ctrl.state == FOLLOWING:
            ox, oy = w // 2, int(h * 0.86)
            cv2.circle(img, (ox, oy), max(3, int(6 * k)), white, -1, cv2.LINE_AA)
            if vx > 0 or vyaw != 0:
                ang = -(vyaw / max(DEFAULTS["max_yaw"], 1e-6)) * np.radians(70)
                length = h * (0.07 + 0.22 * vx / DEFAULTS["max_vx"])
                ex, ey = int(ox + length * np.sin(ang)), int(oy - length * np.cos(ang))
                cv2.arrowedLine(img, (ox, oy), (ex, ey), cyan, max(2, int(5 * k)), cv2.LINE_AA, tipLength=0.25)
        # ASCII only (OpenCV cannot draw Cyrillic); the Bulgarian banner is drawn by the page
        state = {ARMED: "ARMED: RAISE ONE ARM", FOLLOWING: "FOLLOWING", STOPPED: "STOPPED"}[ctrl.state]
        if ctrl.state == FOLLOWING and c.status == "too_close":
            state += " (TOO CLOSE)"
        text = f"{state}  vx {vx:.2f}  w {vyaw:+.2f}  AI {self.detector.fps:.0f} fps"
        # top-right: the bottom corners are covered by the joysticks in the UI
        self._label(img, text, (w - int(16 * k), int(52 * k)), cyan if ctrl.state == FOLLOWING else white, k, right=True)
        if self._slow:
            self._label(img, f"AI SLOW (<{SLOW_FPS:.0f} fps): vx <= {SLOW_MAX_VX}", (w - int(16 * k), int(96 * k)), amber, k, right=True)

    @staticmethod
    def _draw_arms(img, box, color, k) -> None:
        kp = getattr(box, "kp", None)
        if not kp:
            return
        h, w = img.shape[:2]
        for chain in ((5, 7, 9), (6, 8, 10), (5, 6)):  # shoulders - elbows - wrists
            pts = [kp[i] for i in chain]
            if all(c >= 0.4 for _, _, c in pts):
                xy = np.array([(int(x * w), int(y * h)) for x, y, _ in pts], np.int32)
                cv2.polylines(img, [xy], False, color, max(2, int(3 * k)), cv2.LINE_AA)

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
