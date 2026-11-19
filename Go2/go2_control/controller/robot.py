"""Robot session: one WebRTC connection shared by video, telemetry and commands.

All network I/O runs on a dedicated asyncio loop thread. The public methods
(connect, disconnect, action, set_velocity, stop, latest_frame, telemetry)
are thread-safe and never block on the robot.
"""
from __future__ import annotations

import asyncio
import collections
import json
import logging
import math
import random
import threading
import time
from typing import Any

import numpy as np

from unitree_webrtc_connect.constants import DATA_CHANNEL_TYPE, RTC_TOPIC, SPORT_CMD, SPORT_CMD_MCF

from .events import EventLog
from .timing import ACTION_WAIT, TRICKS

log = logging.getLogger("go2")

# Safety limits (server-side, regardless of what the UI sends).
MAX_LINEAR = 1.0   # m/s, |vx| and |vy|
MAX_YAW = 1.5      # rad/s, |vyaw|
# Speed presets shown in the top bar (first = default on every page load).
# Values are full-stick speeds; the hard caps above still apply on top.
SPEED_PRESETS = [
    {"id": "slow", "label": "Бавно", "linear": 0.3, "yaw": 0.6},
    {"id": "normal", "label": "Нормално", "linear": 0.6, "yaw": 1.0},
    {"id": "fast", "label": "Бърз", "linear": 1.0, "yaw": 1.5},
]

# Body posture ("Още" panel): small ranges only; sent as awaited actions.
POSTURE_LIMITS = {
    "Euler": {"x": (-0.15, 0.15), "y": (-0.15, 0.15), "z": (0.0, 0.0)},  # roll, pitch, yaw [rad]
    "BodyHeight": {"data": (-0.10, 0.03)},                                # m, relative to default
}
POSTURE_NEUTRAL = {"Euler": {"x": 0.0, "y": 0.0, "z": 0.0}, "BodyHeight": {"data": 0.0}}

MOVE_PERIOD = 0.1  # Move is re-sent at 10 Hz while velocity is non-zero
DEADMAN = 0.3      # no set_velocity for this long -> StopMove once
REPLY_TIMEOUT = 1.0   # awaited commands (StandUp, Sit, Hello, BalanceStand, StopMove, ...)

# Actions shown in the UI, in display order: (SPORT_CMD name, Bulgarian label, icon id, group).
# "Трикове" = every in-place trick in the installed SPORT_CMD that the firmware accepts
# (WiggleHips is listed but filtered out by fw_supported: code 3203 on 1.1.12). Left out on purpose:
# Wallow (rolls onto its back, posture afterwards unknown), Trigger (reserved id, unclear),
# Dance3/Dance4 (not in this library's SPORT_CMD), and everything in FORBIDDEN.
ACTION_CATALOG = [
    ("StandUp", "Стани", "stand-up", "posture"),
    ("StandDown", "Легни", "stand-down", "posture"),
    ("BalanceStand", "Баланс", "balance", "posture"),
    ("RecoveryStand", "Възстанови", "recovery", "posture"),
    ("Sit", "Седни", "sit", "posture"),
    ("RiseSit", "Изправи от седнало", "rise-sit", "posture"),
    ("Hello", "Здрасти", "hello", "tricks"),
    ("Stretch", "Протягане", "stretch", "tricks"),
    ("Dance1", "Танц 1", "dance1", "tricks"),
    ("Dance2", "Танц 2", "dance2", "tricks"),
    ("Content", "Радост", "content", "tricks"),
    ("Scrape", "Поклон", "scrape", "tricks"),
    ("WiggleHips", "Кълчене", "wiggle", "tricks"),
    ("FingerHeart", "Сърце", "heart", "tricks"),
]
ACTION_GROUPS = {"posture": "Поза", "tricks": "Трикове"}

# Bulgarian names for the operator log.
LABELS = {n: lbl for n, lbl, _, _ in ACTION_CATALOG}
LABELS.update({"StopMove": "StopMove", "Move": "Движение", "Euler": "Наклон", "BodyHeight": "Височина",
               "Damp": "Damp", "Pose": "Режим поза"})


def label(name: str) -> str:
    return LABELS.get(name, name)


def code_text(code: Any) -> str:
    if code == 0:
        return "OK"
    if code == "timeout":
        return "няма отговор"
    if code == "not connected":
        return "няма връзка"
    return f"код {code}"


# Never exposed, even if someone sends the name by hand.
FORBIDDEN = {
    "Damp", "FrontFlip", "BackFlip", "LeftFlip", "RightFlip", "FrontJump",
    "FrontPounce", "Handstand", "HandStand", "Bound", "FreeJump", "FreeBound",
    "MoonWalk", "StandOut", "Wallow",
}

# After these, the robot must be put in BalanceStand before it accepts Move.
NEEDS_BALANCE_AFTER = {"StandUp", "RiseSit", "RecoveryStand"}

FSM_TRICK = 1006        # sportmodestate error_code while a trick runs (robot log, fw 1.1.12)
STOP_CHECK_AFTER = 2.0  # s after СТОП/АВАРИЙНО: log the robot's FSM state (did it stop?)

# Replies to RTC_TOPIC["SPORT_MOD"] requests come back on this topic (robot logs, fw 1.1.12).
SPORT_RESPONSE_TOPIC = "rt/api/sport/response"

# ---------------- posture logic ----------------
STANDING, SITTING, LYING, UNKNOWN = "STANDING", "SITTING", "LYING", "UNKNOWN"
POSTURE_LABEL = {STANDING: "Стои", SITTING: "Седи", LYING: "Лежи", UNKNOWN: "—"}
# Posture each command leaves the robot in (inferred from what we send).
POSTURE_AFTER = {"StandUp": STANDING, "RiseSit": STANDING, "RecoveryStand": STANDING,
                 "BalanceStand": STANDING, "Sit": SITTING, "StandDown": LYING}
# Actions that need the robot standing (and balanced) first.
NEEDS_STANDING = {"Hello", "Stretch", "Sit", "Euler", "BodyHeight", "Move", "BalanceStand", *TRICKS}
# sportmodestate "mode" values that clearly confirm a posture (others are ignored).
MODE_POSTURE = {1: STANDING, 3: STANDING, 5: LYING, 10: SITTING}
MODE_GRACE = 2.0  # s after a posture command during which telemetry may still lag behind


def _to_standing(posture: str, balanced: bool) -> list[tuple[str, bool]]:
    if posture == STANDING:
        return [] if balanced else [("BalanceStand", True)]
    if posture == SITTING:
        return [("RiseSit", True), ("BalanceStand", True)]
    return [("StandUp", True), ("BalanceStand", True)]  # LYING or UNKNOWN


def plan_steps(name: str, posture: str, balanced: bool = True) -> list[tuple[str, bool]]:
    """Commands to send for `name` from `posture`: [(command, auto_inserted)].
    An empty list means: already there, skip. For "Move" only the preparation is returned."""
    if name in ("StandUp", "RiseSit"):
        if posture == STANDING:
            return []
        if posture == SITTING:
            return [("RiseSit", name != "RiseSit")]   # standing up from sitting is RiseSit
        if posture == LYING:
            return [("StandUp", name != "StandUp")]   # standing up from lying is StandUp
        return [(name, False)]
    if name == "StandDown":
        if posture == LYING:
            return []
        if posture == SITTING:
            return [("RiseSit", True), ("StandDown", False)]
        return [("StandDown", False)]
    if name == "Sit":
        if posture == SITTING:
            return []
        return _to_standing(posture, balanced) + [("Sit", False)]
    if name == "BalanceStand":
        return [s for s in _to_standing(posture, False) if s[0] != "BalanceStand"] + [("BalanceStand", False)]
    if name == "Move":
        return _to_standing(posture, balanced)
    if name in NEEDS_STANDING:
        return _to_standing(posture, balanced) + [(name, False)]
    return [(name, False)]

# rt/lf/sportmodestate "mode" values (Unitree SDK docs).
MODE_NAMES = {
    0: "Готов", 1: "Баланс", 2: "Поза", 3: "Ходене", 5: "Легнал",
    6: "Заключен", 7: "Отпуснат", 8: "Възстановяване", 10: "Седнал",
}


# Firmware 1.1.12 (>= 1.1.7) runs the MCF sport API (library table SPORT_CMD_MCF). Robot test
# 2026-11-19: WiggleHips (1033) and BodyHeight (1013) answered code 3203 every time and never
# moved; both are missing from SPORT_CMD_MCF, while every command that worked is in it.
# So only commands whose api_id is in that table are offered.
MCF_IDS = frozenset(SPORT_CMD_MCF.values())


def fw_supported(name: str) -> bool:
    return SPORT_CMD.get(name) in MCF_IDS


def available_actions(cmds: dict | None = None) -> list[dict]:
    """Catalog entries whose SPORT_CMD name exists in the installed library and whose api_id
    the robot firmware accepts (SPORT_CMD_MCF)."""
    cmds = SPORT_CMD if cmds is None else cmds
    return [
        {"name": n, "label": lbl, "icon": icon, "group": group}
        for n, lbl, icon, group in ACTION_CATALOG
        if n in cmds and n not in FORBIDDEN and fw_supported(n)
    ]


def available_posture(cmds: dict | None = None) -> dict:
    """Posture commands whose SPORT_CMD name exists and that the firmware accepts, with their
    parameter ranges. BodyHeight: code 3203 on fw 1.1.12 (robot log 2026-11-19) -> hidden."""
    cmds = SPORT_CMD if cmds is None else cmds
    return {n: lim for n, lim in POSTURE_LIMITS.items() if n in cmds and fw_supported(n)}


def clamp_posture(name: str, param: dict | None) -> dict[str, float]:
    if name not in POSTURE_LIMITS:
        raise ValueError(f"posture not allowed: {name}")
    out = {}
    for k, (lo, hi) in POSTURE_LIMITS[name].items():
        try:
            v = float((param or {}).get(k, 0.0))
        except (TypeError, ValueError):
            v = 0.0
        out[k] = round(min(hi, max(lo, v if math.isfinite(v) else 0.0)), 3)
    return out


def _clamp(v: Any, limit: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(v):
        return 0.0
    v = max(-limit, min(limit, v))
    return 0.0 if abs(v) < 1e-3 else round(v, 3)


def clamp_velocity(vx: Any, vy: Any, vyaw: Any) -> tuple[float, float, float]:
    return _clamp(vx, MAX_LINEAR), _clamp(vy, MAX_LINEAR), _clamp(vyaw, MAX_YAW)


class BaseRobot:
    """Shared control logic. Subclasses implement the transport."""

    sim = False

    def __init__(self, waits: dict[str, float] | None = None) -> None:
        self.waits = dict(ACTION_WAIT if waits is None else waits)  # motion durations (timing.py)
        self.events = EventLog()
        self.posture_state = UNKNOWN          # inferred: STANDING / SITTING / LYING / UNKNOWN
        self._settle_until = 0.0              # posture motion still running until then
        self._plan_task: asyncio.Task | None = None
        self._plan_busy = False               # a chain is still sending its auto-inserted steps
        self._pose_mode = False               # Pose (1028) on: body attitude control (Euler)
        self._plan_name: str | None = None
        self._busy_name: str | None = None   # trick the robot is (probably) still performing
        self._busy_until = 0.0
        self.allowed = {a["name"] for a in available_actions()}
        self.posture_allowed = set(available_posture())
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="robot-loop", daemon=True)
        self._lock = threading.Lock()
        self._vel = (0.0, 0.0, 0.0)
        self._last_vel_time = 0.0
        self._pending_stop = False
        self._moving = False          # loop-thread only
        self._needs_balance = False   # loop-thread only
        self._frame: np.ndarray | None = None
        self._frame_seq = 0
        self._frame_cond = threading.Condition()
        self._frame_times: collections.deque[float] = collections.deque(maxlen=90)
        self._state = "disconnected"   # disconnected | connecting | connected | error
        self._error = ""
        self._want_connected = False
        self._telemetry: dict[str, Any] = {
            "battery": None, "voltage": None, "mode": None, "mode_id": None, "fsm": None,
            "last_command": None, "last_code": None, "last_command_at": None,
        }
        self._started = False
        self.last_action_at = 0.0   # monotonic time of the last action (read by upper layers)
        self._move_sent = 0
        self._move_log_at = 0.0
        self._move_last_code: Any = None
        self._move_last_code_at = 0.0
        self._move_warn_at = 0.0
        self._move_burst_at = 0.0

    # ---------- lifecycle ----------
    def start(self) -> "BaseRobot":
        if not self._started:
            self._started = True
            self._thread.start()
            asyncio.run_coroutine_threadsafe(self._control_loop(), self._loop)
            asyncio.run_coroutine_threadsafe(self._watchdog(), self._loop)
        return self

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def close(self) -> None:
        if not self._started:
            return
        try:
            self._submit(self._shutdown()).result(timeout=5)
        except Exception as e:  # noqa: BLE001
            log.warning("shutdown: %s", e)

        async def _cancel_all():
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        try:
            self._submit(_cancel_all()).result(timeout=2)
        except Exception:  # noqa: BLE001
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2)
        if not self._loop.is_running():
            self._loop.close()

    async def _shutdown(self) -> None:
        self._want_connected = False
        if self._state == "connected":
            await self._send("StopMove")
        await self._close_transport()
        self._state = "disconnected"

    # ---------- public, thread-safe API ----------
    def connect(self):
        self._want_connected = True
        return self._submit(self._connect_once())

    def disconnect(self):
        self._want_connected = False
        return self._submit(self._shutdown())

    def action(self, name: str):
        if name not in self.allowed:
            raise ValueError(f"action not allowed: {name}")
        return self._submit(self._do_action(name))

    def posture(self, name: str, param: dict | None = None):
        """Euler / BodyHeight with clamped parameters, sent as an awaited action.
        Euler switches the robot into pose mode first (see _run_plan)."""
        if name not in self.posture_allowed:
            raise ValueError(f"posture not allowed: {name}")
        return self._submit(self._do_action(name, clamp_posture(name, param)))

    def posture_reset(self):
        """Neutral attitude, then leave pose mode."""
        return self._submit(self._do_posture_reset())

    async def _do_posture_reset(self) -> Any:
        if not self._pose_mode:  # a tilt only exists in pose mode; never stand the robot up for this
            self.events.add("Позата вече е неутрална")
            return 0
        code = await self._send("Euler", dict(POSTURE_NEUTRAL["Euler"]))
        await self._set_pose_mode(False)
        return code

    async def _set_pose_mode(self, on: bool) -> Any:
        """Pose (1028): on fw 1.1.12 Euler answered code 0 but did not move the body in the
        normal balance stand (FSM 100); attitude control needs pose mode."""
        code = await self._send("Pose", {"data": on})
        if code in (0, "timeout"):
            self._pose_mode = on
        if on:
            self._settle_until = max(self._settle_until, time.monotonic() + self.waits.get("Pose", 0.0))
        return code

    def set_velocity(self, vx: Any, vy: Any, vyaw: Any) -> tuple[float, float, float]:
        vel = clamp_velocity(vx, vy, vyaw)
        with self._lock:
            was_moving = self._vel != (0.0, 0.0, 0.0)
            self._vel = vel
            self._last_vel_time = time.monotonic()
            if was_moving and vel == (0.0, 0.0, 0.0):
                self._pending_stop = True
        return vel

    def stop(self, note: str = "СТОП"):
        """Zero velocity and send StopMove (awaited). `note` is the operator log line:
        "СТОП" for the button / Space / Esc, something else when an upper layer stops."""
        with self._lock:
            self._vel = (0.0, 0.0, 0.0)
            self._pending_stop = False
        return self._submit(self._do_stop(note))

    def latest_frame(self) -> tuple[int, np.ndarray | None]:
        with self._frame_cond:
            return self._frame_seq, self._frame

    def wait_frame(self, after_seq: int, timeout: float = 1.0) -> tuple[int, np.ndarray | None]:
        with self._frame_cond:
            self._frame_cond.wait_for(lambda: self._frame_seq != after_seq, timeout=timeout)
            return self._frame_seq, self._frame

    def telemetry(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._frame_cond:
            recent = [t for t in self._frame_times if now - t <= 1.0]
        with self._lock:
            vel = self._vel
        t = dict(self._telemetry)
        t.update({
            "state": self._state,
            "connected": self._state == "connected",
            "error": self._error,
            "sim": self.sim,
            "fps": len(recent) if recent and now - recent[-1] < 1.0 else 0,
            "velocity": {"vx": vel[0], "vy": vel[1], "vyaw": vel[2]},
            "posture": self.posture_state,
            "posture_label": POSTURE_LABEL.get(self.posture_state, self.posture_state),
            "chain": self._plan_busy,
        })
        return t

    # ---------- frames ----------
    def _push_frame(self, img: np.ndarray) -> None:
        with self._frame_cond:
            self._frame = img
            self._frame_seq += 1
            self._frame_times.append(time.monotonic())
            self._frame_cond.notify_all()

    # ---------- commands ----------
    # Every send goes on the wire synchronously, in call order (datachannel is ordered).
    # Move is fire-and-forget; other commands await their reply (REPLY_TIMEOUT) in their own task.
    def _fmt(self, param: dict | None) -> str:
        if not param:
            return ""
        return " " + " ".join(f"{k}={v:+.2f}" if isinstance(v, float) else f"{k}={v}" for k, v in param.items())

    def _issue(self, name: str, param: dict | None):
        """Put a request on the wire right now; returns (reply future | None, t0, code if failed)."""
        if name == "StopMove":
            self._move_burst_at = 0.0  # the next Move starts a new burst ("start" log line)
        try:
            return self._transmit(name, param, want_reply=True), time.monotonic(), "not connected"
        except Exception as e:  # noqa: BLE001
            return None, time.monotonic(), f"error: {e}"

    async def _await_reply(self, name: str, param: dict | None, fut, t0: float, code: Any,
                           ui: bool = True) -> Any:
        if fut is not None:
            done, _ = await asyncio.wait({fut}, timeout=REPLY_TIMEOUT)
            if not done:
                code = "timeout"  # not cancelled on purpose: a late reply must not hit a cancelled future
                # The robot answers long actions only when they finish (Dance1: after 16 s on the
                # robot); log that late reply so the operator sees when a trick is really over.
                fut.add_done_callback(lambda f, n=name, t=t0: self._late_reply(n, t, f))
            else:
                try:
                    code = self._reply_code(fut.result())
                except Exception as e:  # noqa: BLE001
                    code = f"error: {e}"
        ms = (time.monotonic() - t0) * 1000
        log.log(logging.INFO if code == 0 else logging.WARNING,
                "CMD %-12s%s -> code=%s (%.0f ms)", name, self._fmt(param), code, ms)
        self._telemetry.update(last_command=name, last_code=code, last_command_at=time.time())
        if ui:
            self.events.add(f"{label(name)}: {code_text(code)} ({ms:.0f} ms)", "ok" if code == 0 else "warn")
        return code

    def _late_reply(self, name: str, t0: float, fut) -> None:
        if fut.cancelled():
            return
        try:
            code = self._reply_code(fut.result())
        except Exception as e:  # noqa: BLE001
            code = f"error: {e}"
        secs = time.monotonic() - t0
        log.info("CMD %-12s late reply -> code=%s (%.1f s)", name, code, secs)
        self.events.add(f"{label(name)}: завърши, {code_text(code)} (след {secs:.1f} s)", "ok" if code == 0 else "warn")
        if name == self._busy_name:
            self._busy_until = 0.0  # the trick is over

    def _trick_running(self) -> str | None:
        """Name of the trick that is (probably) still running. Real robot: sportmodestate
        error_code 1006 while a trick runs (robot log 2026-11-19); sim: our time estimate."""
        if self._busy_name and (self._telemetry.get("fsm") == FSM_TRICK
                                or time.monotonic() < self._busy_until):
            return self._busy_name
        return None

    async def _send(self, name: str, param: dict | None = None, ui: bool = True) -> Any:
        """Send now and await the reply (max REPLY_TIMEOUT). Never used for Move."""
        if name in TRICKS:
            self._busy_name, self._busy_until = name, time.monotonic() + self.waits.get(name, 0.0)
        return await self._await_reply(name, param, *self._issue(name, param), ui=ui)

    def _send_bg(self, name: str, param: dict | None = None, ui: bool = False) -> None:
        """Send now (synchronously, so wire order = call order); await + log the reply in a task."""
        self._loop.create_task(self._await_reply(name, param, *self._issue(name, param), ui=ui))

    def _send_move(self, vel: tuple[float, float, float]) -> None:
        """Fire-and-forget Move. Logged at most once per second."""
        param = {"x": vel[0], "y": vel[1], "z": vel[2]}
        try:
            self._transmit("Move", param, want_reply=False)
            self._move_sent += 1
        except Exception as e:  # noqa: BLE001
            log.warning("CMD Move send failed: %s", e)
        self._telemetry.update(last_command="Move", last_code=self._move_last_code, last_command_at=time.time())
        now = time.monotonic()
        if now - self._move_burst_at > 0.5:  # first Move of a new movement
            log.info("CMD Move        %s -> start", self._fmt(param))
            self._move_sent, self._move_log_at = 0, now
        elif now - self._move_log_at >= 1.0:
            reply = "no reply" if self._move_last_code is None or now - self._move_last_code_at > 1.5 \
                else f"last reply code={self._move_last_code}"
            log.info("CMD Move        %s -> %d sent in %.1f s, %s",
                     self._fmt(param), self._move_sent, now - self._move_log_at, reply)
            self._move_sent, self._move_log_at = 0, now
        self._move_burst_at = now

    def _on_move_reply(self, code: Any) -> None:
        """Called by the transport when a Move reply arrives (if the robot sends one)."""
        self._move_last_code, self._move_last_code_at = code, time.monotonic()
        if code != 0 and time.monotonic() - self._move_warn_at >= 1.0:
            self._move_warn_at = time.monotonic()
            log.warning("CMD Move reply code=%s", code)

    @staticmethod
    def _reply_code(r: Any) -> Any:
        r = r or {}
        return r.get("data", {}).get("header", {}).get("status", {}).get("code")

    async def _do_action(self, name: str, param: dict | None = None) -> Any:
        self.last_action_at = time.monotonic()
        with self._lock:
            had_vel = self._vel != (0.0, 0.0, 0.0)
            self._vel = (0.0, 0.0, 0.0)
            self._pending_stop = False
        if had_vel or self._moving:
            self._moving = False
            self._send_bg("StopMove")  # on the wire now; reply logged in the background
        if self._plan_busy and self._plan_task is not None:
            self._plan_task.cancel()  # a newer request replaces a chain that is still preparing
            if self._plan_name != name:  # e.g. slider steps replacing each other are not news
                self.events.add("Авто-веригата е заменена от нова команда", "warn")
        task = self._start_plan(name, param)
        try:
            return await task
        except asyncio.CancelledError:
            return "cancelled"

    # ---------- posture chains ----------
    def _start_plan(self, name: str, param: dict | None = None) -> asyncio.Task:
        self._plan_busy = True  # set synchronously: the control loop must not start a second chain
        self._plan_name = name
        self._plan_task = self._loop.create_task(self._run_plan(name, param))
        return self._plan_task

    async def _run_plan(self, name: str, param: dict | None) -> Any:
        me = asyncio.current_task()
        try:
            if self._pose_mode and name != "Euler":
                # anything else (actions, movement) leaves pose mode first
                self.events.add("Авто: изключвам режим поза")
                await self._set_pose_mode(False)
            steps = plan_steps(name, self.posture_state, not self._needs_balance)
            what = "движение" if name == "Move" else label(name)
            if not steps:
                if name != "Move":
                    self.events.add(f"{label(name)}: вече {POSTURE_LABEL[self.posture_state].lower()}, пропуснато")
                return 0
            sent = [c for c, _ in steps]
            if name != "Move" and name not in sent:
                self.events.add(f"Авто: {label(sent[-1])} вместо {label(name)} "
                                f"({POSTURE_LABEL[self.posture_state].lower()})")
            else:
                auto = [c for c, ins in steps if ins]
                if auto:
                    self.events.add(f"Авто: {' → '.join(label(c) for c in auto)} преди {what}")
            for i, (cmd, _) in enumerate(steps):
                await self._wait_settled()
                if i == len(steps) - 1 and name != "Move":
                    # the requested command itself: await its reply, like any action
                    if cmd == "Euler" and not self._pose_mode:
                        self.events.add("Авто: режим поза за наклона")
                        await self._set_pose_mode(True)
                        await self._wait_settled()
                    self._plan_busy = False
                    return await self._send_tracked(cmd, param if cmd == name else None)
                reply = self._send_tracked_bg(cmd)  # auto step: never block on its reply
                await self._wait_settled()           # ... but give the motion its time
                if reply.done() and reply.result() not in (0, "timeout"):
                    self.events.add(f"Авто-веригата спря: {label(cmd)} → {code_text(reply.result())}", "warn")
                    return reply.result()
            return 0
        finally:
            if self._plan_task is me:
                self._plan_busy = False

    async def _wait_settled(self) -> None:
        while (left := self._settle_until - time.monotonic()) > 0:
            await asyncio.sleep(min(0.05, left))

    def _apply_posture(self, cmd: str) -> tuple:
        """Optimistic update when `cmd` goes on the wire. Returns the previous state."""
        prev = (self.posture_state, self._needs_balance)
        if cmd in POSTURE_AFTER:
            self.posture_state = POSTURE_AFTER[cmd]
            if cmd in NEEDS_BALANCE_AFTER or POSTURE_AFTER[cmd] != STANDING:
                self._needs_balance = True
            elif cmd == "BalanceStand":
                self._needs_balance = False
        if cmd in POSTURE_AFTER or cmd in ("Euler", "BodyHeight"):
            self._settle_until = max(self._settle_until, time.monotonic() + self.waits.get(cmd, 0.0))
        return prev

    def _revert_posture(self, cmd: str, prev: tuple, code: Any) -> None:
        if code not in (0, "timeout") and cmd in POSTURE_AFTER:
            self.posture_state, self._needs_balance = prev  # the robot refused: it did not move

    async def _send_tracked(self, cmd: str, param: dict | None = None) -> Any:
        prev = self._apply_posture(cmd)
        code = await self._send(cmd, param)
        self._revert_posture(cmd, prev, code)
        return code

    def _send_tracked_bg(self, cmd: str) -> asyncio.Task:
        prev = self._apply_posture(cmd)
        task = self._loop.create_task(self._await_reply(cmd, None, *self._issue(cmd, None), ui=True))
        task.add_done_callback(lambda t: t.cancelled() or self._revert_posture(cmd, prev, t.result()))
        return task

    def _on_mode(self, mode: Any) -> None:
        """sportmodestate telemetry: adopt the posture only when the mode clearly confirms it
        and no chain / recent posture command could make it stale."""
        target = MODE_POSTURE.get(mode)
        if target is None or self._plan_busy or time.monotonic() < self._settle_until + MODE_GRACE:
            return
        balanced = mode in (1, 3)
        if target == self.posture_state and not (balanced and self._needs_balance):
            return
        self.posture_state = target
        self._needs_balance = not balanced
        self.events.add(f"Поза от телеметрията: {POSTURE_LABEL[target]}")

    async def _do_stop(self, note: str = "СТОП") -> Any:
        self._moving = False
        self.events.add(note, "danger" if note == "СТОП" else "info")
        if self._plan_busy and self._plan_task is not None:
            self._plan_task.cancel()
            self._plan_busy = False
            self.events.add("Авто-веригата е отменена", "warn")
        trick = self._trick_running()
        if not trick:
            return await self._send("StopMove")
        # During a trick the robot did not answer StopMove at all (Dance2, robot log 2026-11-19).
        # Try StopMove and right after it BalanceStand, and log what each one returns.
        self.events.add(f"„{label(trick)}“ още върви: StopMove + Баланс, за да опитам да го прекъсна", "warn")
        self._issue_and_log("StopMove")
        self._needs_balance = False
        code = await self._send_tracked("BalanceStand")
        self._loop.call_later(STOP_CHECK_AFTER, self._report_after_stop, trick)
        return code

    def _issue_and_log(self, name: str) -> None:
        """Send now; await + log its reply in the background (keeps the wire order)."""
        self._loop.create_task(self._await_reply(name, None, *self._issue(name, None), ui=True))

    def _report_after_stop(self, trick: str) -> None:
        fsm = self._telemetry.get("fsm")
        if fsm is None:
            return  # sim: no robot state to report
        still = fsm == FSM_TRICK
        self.events.add(f"{STOP_CHECK_AFTER:.0f} s след СТОП: робот FSM {fsm}"
                        + (f" (трикът „{label(trick)}“ още върви)" if still else ""), "warn" if still else "info")

    def emergency_damp(self):
        """АВАРИЙНО: Damp (motors go limp, the robot lowers itself to the ground). Deliberately
        outside the action whitelist, where Damp stays forbidden."""
        with self._lock:
            self._vel = (0.0, 0.0, 0.0)
            self._pending_stop = False
        return self._submit(self._do_damp())

    async def _do_damp(self) -> Any:
        self._moving = False
        self.events.add("АВАРИЙНО: Damp", "danger")
        if self._plan_busy and self._plan_task is not None:
            self._plan_task.cancel()
            self._plan_busy = False
        code = await self._send("Damp")
        if code in (0, "timeout"):
            self.posture_state, self._needs_balance = LYING, True
        self._loop.call_later(STOP_CHECK_AFTER, self._report_after_stop, self._busy_name or "Damp")
        return code

    async def _control_loop(self) -> None:
        """10 Hz movement loop. Nothing in here awaits the robot."""
        next_move = 0.0
        while True:
            await asyncio.sleep(0.01)
            try:
                now = time.monotonic()
                with self._lock:
                    vel = self._vel
                    stale = vel != (0.0, 0.0, 0.0) and now - self._last_vel_time > DEADMAN
                    if stale:
                        self._vel = vel = (0.0, 0.0, 0.0)
                    pending_stop, self._pending_stop = self._pending_stop, False
                if stale:
                    log.warning("DEADMAN: no velocity update for %.0f ms -> StopMove", DEADMAN * 1000)
                    self.events.add(f"Deadman: {DEADMAN * 1000:.0f} ms без команда → StopMove", "warn")
                if stale or pending_stop:
                    if self._moving:  # nothing to stop if no Move went out (e.g. still standing up)
                        self._send_bg("StopMove")
                    self._moving = False
                    continue
                if vel == (0.0, 0.0, 0.0) or self._state != "connected":
                    next_move = 0.0
                    continue
                if self._plan_busy:
                    continue  # a posture chain is running: hold Moves until it is done
                if self.posture_state != STANDING or self._needs_balance or self._pose_mode:
                    self._start_plan("Move")  # stand up / balance first (BalanceStand rule included)
                    continue
                if now < self._settle_until or now < next_move:
                    continue
                self._send_move(vel)
                self._moving = True
                next_move = now + MOVE_PERIOD if now - next_move > MOVE_PERIOD else next_move + MOVE_PERIOD
            except Exception:  # noqa: BLE001
                log.exception("control loop")

    async def _watchdog(self) -> None:
        """Reconnect automatically while the user wants a connection."""
        while True:
            await asyncio.sleep(1.0)
            try:
                if self._state == "connected" and not self._transport_alive():
                    log.warning("connection lost")
                    self._state = "disconnected"
                    self._error = "Връзката с робота прекъсна"
                    await self._close_transport()
                if self._want_connected and self._state in ("disconnected", "error"):
                    await asyncio.sleep(2.0)
                    if self._want_connected and self._state in ("disconnected", "error"):
                        await self._connect_once()
            except Exception:  # noqa: BLE001
                log.exception("watchdog")

    async def _connect_once(self) -> None:
        if self._state in ("connecting", "connected"):
            return
        self._state = "connecting"
        self._error = ""
        try:
            await self._open_transport()
            self._state = "connected"
            log.info("connected")
        except Exception as e:  # noqa: BLE001
            self._state = "error"
            self._error = self._describe_error(e)
            log.error("connect failed: %s", self._error)
            try:
                await self._close_transport()
            except Exception:  # noqa: BLE001
                pass

    def _describe_error(self, e: Exception) -> str:
        return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__

    # ---------- transport (subclass) ----------
    async def _open_transport(self) -> None:
        raise NotImplementedError

    async def _close_transport(self) -> None:
        raise NotImplementedError

    def _transport_alive(self) -> bool:
        return True

    def _transmit(self, name: str, param: dict | None, want_reply: bool) -> "asyncio.Future | None":
        """Put one sport request on the wire *now* (loop thread). Returns a reply future
        when want_reply, else None. Must not await."""
        raise NotImplementedError


class RobotSession(BaseRobot):
    """Real Go2 over WebRTC (LocalAP, 192.168.12.1)."""

    def __init__(self) -> None:
        super().__init__()
        self.conn = None

    async def _open_transport(self) -> None:
        from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod

        conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
        self.conn = conn
        await asyncio.wait_for(conn.connect(), timeout=40)
        conn.video.add_track_callback(self._on_track)
        res = conn.video.switchVideoChannel(True)
        if asyncio.iscoroutine(res):
            await res
        ps = conn.datachannel.pub_sub
        # Local hook only (no subscribe message to the robot): pub_sub.run_resolve calls
        # subscriptions[topic] for every incoming message on that topic. Replies to
        # rt/api/sport/request arrive on rt/api/sport/response (seen in the robot logs).
        ps.subscriptions[SPORT_RESPONSE_TOPIC] = self._on_sport_reply
        ps.subscribe(RTC_TOPIC["LOW_STATE"], self._on_low_state)
        ps.subscribe(RTC_TOPIC["LF_SPORT_MOD_STATE"], self._on_sport_state)

    async def _close_transport(self) -> None:
        conn, self.conn = self.conn, None
        if conn is not None:
            await asyncio.wait_for(conn.disconnect(), timeout=5)

    def _transport_alive(self) -> bool:
        pc = getattr(self.conn, "pc", None)
        return pc is not None and pc.connectionState not in ("failed", "closed")

    def _describe_error(self, e: Exception) -> str:
        n = type(e).__name__
        if n == "RobotBusyError":
            return "Роботът е зает: затвори приложението Unitree на телефона"
        if n == "LocalSignalingPortError":
            return "Роботът не е достъпен на 192.168.12.1: Mac-ът на WiFi мрежата на робота ли е?"
        if n == "NoSdpAnswerError":
            return "Роботът не отговори на връзката: изчакай или рестартирай робота"
        if n in ("AesKeyRequiredError", "AesKeyRejectedError"):
            return "Фърмуерът иска AES ключ (≥ 1.1.15): виж README"
        if isinstance(e, (asyncio.TimeoutError, TimeoutError)) or n == "DataChannelTimeoutError":
            return "Няма отговор от робота (WiFi на робота?)"
        if isinstance(e, OSError) or "Connection" in n:
            return "Роботът не е достъпен на 192.168.12.1 (WiFi на робота?)"
        return super()._describe_error(e)

    def _transmit(self, name: str, param: dict | None, want_reply: bool):
        """Same wire format as pub_sub.publish_request_new, but sent synchronously:
        the reply future (if wanted) is registered first, then the request goes out via
        pub_sub.publish_without_callback (the library's fire-and-forget send)."""
        conn = self.conn
        ch = getattr(getattr(conn, "datachannel", None), "channel", None)
        if conn is None or ch is None or ch.readyState != "open":
            return None  # publish_without_callback would drop it silently anyway
        ps = conn.datachannel.pub_sub
        topic = RTC_TOPIC["SPORT_MOD"]
        req_id = int(time.time() * 1000) % 2147483648 + random.randint(0, 1000)
        payload = {
            "header": {"identity": {"id": req_id, "api_id": SPORT_CMD[name]}},
            "parameter": json.dumps(param) if param is not None else "",
        }
        fut = None
        if want_reply:
            fut = self._loop.create_future()
            ps.future_resolver.save_resolve(DATA_CHANNEL_TYPE["REQUEST"], topic, fut, req_id)
        ps.publish_without_callback(topic, payload, DATA_CHANNEL_TYPE["REQUEST"])
        return fut

    def _on_sport_reply(self, msg: dict) -> None:
        """Every message on rt/api/sport/request; we only look at Move replies here."""
        hdr = ((msg or {}).get("data") or {}).get("header") or {}
        if (hdr.get("identity") or {}).get("api_id") == SPORT_CMD["Move"]:
            self._on_move_reply((hdr.get("status") or {}).get("code"))

    async def _on_track(self, track) -> None:
        while True:
            frame = await track.recv()
            self._push_frame(frame.to_ndarray(format="bgr24"))

    def _on_low_state(self, msg: dict) -> None:
        d = msg.get("data") or {}
        bms = d.get("bms_state") or {}
        if "soc" in bms:
            self._telemetry["battery"] = bms["soc"]
        if "power_v" in d:
            self._telemetry["voltage"] = round(float(d["power_v"]), 1)

    def _on_sport_state(self, msg: dict) -> None:
        d = msg.get("data") or {}
        if "error_code" in d:  # fw 1.1.12: the FSM state (1006 = trick running), "mode" stays 0
            self._telemetry["fsm"] = d["error_code"]
        if "mode" in d:
            m = d["mode"]
            self._telemetry["mode_id"] = m
            self._telemetry["mode"] = MODE_NAMES.get(m, f"Режим {m}")
            self._on_mode(m)


class SimRobot(BaseRobot):
    """Same API; Mac webcam as video, commands only logged."""

    sim = True
    SIM_MODES = {
        "StandUp": 6, "StandDown": 5, "BalanceStand": 1, "RecoveryStand": 8, "Sit": 10,
        "RiseSit": 6, "Hello": 1, "Stretch": 1, "Dance1": 1, "Dance2": 1, "StopMove": 1, "Move": 3,
    }

    def __init__(self, camera: int | str | None = "auto") -> None:
        super().__init__()
        self.camera = camera
        self._cap_stop = threading.Event()
        self._cap_thread: threading.Thread | None = None
        self._battery = 92.0
        self._telemetry.update(mode="Готов", mode_id=0)

    async def _open_transport(self) -> None:
        await asyncio.sleep(0.3)
        self._cap_stop.clear()
        self._cap_thread = threading.Thread(target=self._capture, name="sim-camera", daemon=True)
        self._cap_thread.start()
        self._telemetry["battery"] = int(self._battery)
        self._telemetry["voltage"] = 28.6
        # like a booted Go2: it reports balance stand, which the posture logic adopts
        self._telemetry.update(mode_id=1, mode=MODE_NAMES[1])
        self._on_mode(1)

    async def _close_transport(self) -> None:
        self._cap_stop.set()

    def _transmit(self, name: str, param: dict | None, want_reply: bool):
        m = self.SIM_MODES.get(name)
        if m is not None:
            self._telemetry.update(mode_id=m, mode=MODE_NAMES.get(m))
        self._battery = max(5.0, self._battery - 0.002)
        self._telemetry["battery"] = int(self._battery)
        delay = random.uniform(0.003, 0.015)
        if not want_reply:
            self._loop.call_later(delay, self._on_move_reply, 0)  # pretend the robot answers Move
            return None
        fut = self._loop.create_future()
        self._loop.call_later(delay, lambda: fut.done() or fut.set_result({"data": {"header": {"status": {"code": 0}}}}))
        return fut

    def _capture(self) -> None:
        import cv2

        cap = self._open_camera(cv2)
        fails = 0
        while not self._cap_stop.is_set():
            if cap is not None:
                ok, img = cap.read()
                if ok:
                    fails = 0
                    if img.shape[1] > 1280:
                        img = cv2.resize(img, (1280, int(img.shape[0] * 1280 / img.shape[1])), interpolation=cv2.INTER_AREA)
                    self._push_frame(img)
                    continue
                fails += 1
                if fails > 30:
                    log.warning("SIM: webcam stopped delivering frames, using test pattern")
                    cap.release()
                    cap = None
                time.sleep(0.03)
                continue
            self._push_frame(self._test_pattern())
            time.sleep(1 / 15)
        if cap is not None:
            cap.release()

    def _open_camera(self, cv2):
        """Open the requested webcam; camera='auto' picks the first index that delivers
        non-black frames (some Macs expose a dark virtual/Continuity device at index 0)."""
        if self.camera is None:
            return None
        if isinstance(self.camera, str) and self.camera not in ("auto",) and not self.camera.isdigit():
            return _FileSource(cv2, self.camera)  # image or video file, for rehearsals and tests
        candidates = [0, 1, 2] if self.camera == "auto" else [int(self.camera)]
        for idx in candidates:
            cap = cv2.VideoCapture(idx)
            if not cap.isOpened():
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            if self.camera != "auto":
                log.info("SIM: webcam %d", idx)
                return cap
            end, best = time.monotonic() + 2.5, 0.0
            while time.monotonic() < end and not self._cap_stop.is_set():
                ok, img = cap.read()
                if ok:
                    best = max(best, float(img.mean()))
                    if best > 8:
                        break
            if best > 8:
                log.info("SIM: webcam index %d (auto)", idx)
                return cap
            log.info("SIM: webcam index %d delivers black frames, trying next", idx)
            cap.release()
        log.warning("SIM: no usable webcam, using test pattern")
        return None

    def _test_pattern(self) -> np.ndarray:
        import cv2

        img = np.zeros((720, 1280, 3), np.uint8)
        img[:] = (40, 32, 28)
        x = int((time.monotonic() * 200) % 1280)
        cv2.rectangle(img, (x, 300), (x + 120, 420), (90, 200, 120), -1)
        cv2.putText(img, "SIM - no webcam", (40, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (220, 220, 220), 2)
        return img


class _FileSource:
    """cv2.VideoCapture-like source that loops an image or video file at ~15 fps."""

    def __init__(self, cv2, path: str) -> None:
        self.cv2 = cv2
        self.img = cv2.imread(path)
        self.cap = None if self.img is not None else cv2.VideoCapture(path)
        if self.img is None and not self.cap.isOpened():
            raise FileNotFoundError(path)
        log.info("SIM: video from file %s", path)

    def read(self):
        time.sleep(1 / 15)
        if self.img is not None:
            return True, self.img.copy()
        ok, img = self.cap.read()
        if not ok:
            self.cap.set(self.cv2.CAP_PROP_POS_FRAMES, 0)
            ok, img = self.cap.read()
        return ok, img

    def release(self) -> None:
        if self.cap is not None:
            self.cap.release()
