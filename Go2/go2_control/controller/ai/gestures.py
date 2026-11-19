"""Gesture mode: MediaPipe gesture recognizer on the latest robot frame.

Runs in its own thread; triggering an action is a non-blocking submit to the
robot loop, so recognition can never stall robot control.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

log = logging.getLogger("go2.gestures")

MODEL = Path(__file__).resolve().parents[2] / "gesture_recognizer.task"
# ======================= gesture -> action (the only mapping table) =======================
# Actions go through robot.action(), i.e. through the posture logic: "StandUp" from sitting
# becomes RiseSit, tricks stand the robot up first, etc. Entries whose action does not exist
# in the installed SPORT_CMD (or is not allowed) are dropped at startup.
MAPPING = {
    "Thumb_Up": "Hello",          # Палец нагоре -> Здрасти
    "Closed_Fist": "Sit",         # Юмрук -> Седни
    "Open_Palm": "RiseSit",       # Отворена длан -> Изправи от седнало (while following: stop following)
    "Victory": "Stretch",         # Победа -> Протягане
    "Pointing_Up": "StandUp",     # Сочи нагоре -> Стани
    "Thumb_Down": "StandDown",    # Палец надолу -> Легни
    "ILoveYou": "FingerHeart",    # Обичам те -> Сърце
}
# ===========================================================================================
LABELS = {
    "Thumb_Up": "Палец нагоре", "Closed_Fist": "Юмрук", "Open_Palm": "Отворена длан",
    "Victory": "Победа", "Pointing_Up": "Сочи нагоре", "Thumb_Down": "Палец надолу",
    "ILoveYou": "Обичам те", "None": "—",
}
STREAK = 8
COOLDOWN = 4.0
PROC_WIDTH = 640

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11),
    (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
]


class GestureMode:
    def __init__(self, robot, model_path: Path = MODEL) -> None:
        self.robot = robot
        self.model_path = Path(model_path)
        self.mapping = {g: a for g, a in MAPPING.items() if a in robot.allowed}
        self._enabled = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._rec = None
        self._lock = threading.Lock()
        self._hands: list[list[tuple[float, float]]] = []
        self._gesture = "None"
        self._score = 0.0
        self._streak = 0
        self._last_trigger: dict[str, Any] | None = None
        self._last_sent = 0.0
        self._error = ""
        self._proc_fps = 0.0
        # Optional hook set by the app: override(gesture) -> (name, callable) | None.
        # When it returns something, that gesture runs the callable instead of its mapped action.
        self.override = None
        # Optional hook set by the app: on_trigger(action) right before a mapped action is sent.
        self.on_trigger = None

    @property
    def enabled(self) -> bool:
        return self._enabled.is_set()

    def set_enabled(self, on: bool) -> None:
        if on:
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._run, name="gestures", daemon=True)
                self._thread.start()
            self._enabled.set()
            log.info("gesture mode ON")
        else:
            self._enabled.clear()
            with self._lock:
                self._hands, self._gesture, self._score, self._streak = [], "None", 0.0, 0
            log.info("gesture mode OFF")

    def close(self) -> None:
        self._stop.set()
        self._enabled.set()

    def state(self) -> dict[str, Any]:
        with self._lock:
            g = self._gesture
            return {
                "enabled": self.enabled,
                "ready": self._rec is not None,
                "gesture": g,
                "gesture_label": LABELS.get(g, g),
                "score": round(self._score, 2),
                "action": self._override_name(g) or self.mapping.get(g),
                "streak": min(self._streak, STREAK),
                "streak_needed": STREAK,
                "cooldown": max(0.0, round(COOLDOWN - (time.monotonic() - self._last_sent), 1)) if self._last_sent else 0.0,
                "last_trigger": self._last_trigger,
                "fps": round(self._proc_fps, 1),
                "error": self._error,
                "mapping": self.mapping,
            }

    def draw(self, img: np.ndarray) -> None:
        if not self.enabled:
            return
        with self._lock:
            hands, g, score = self._hands, self._gesture, self._score
            action = self.mapping.get(g)
        h, w = img.shape[:2]
        k = max(0.45, w / 1280)  # overlay scales with frame size
        cyan, white = (242, 208, 63), (245, 240, 235)
        for pts in hands:
            px = [(int(x * w), int(y * h)) for x, y in pts]
            for a, b in HAND_CONNECTIONS:
                cv2.line(img, px[a], px[b], white, max(1, int(2 * k)), cv2.LINE_AA)
            for p in px:
                cv2.circle(img, p, max(2, int(4 * k)), cyan, -1, cv2.LINE_AA)
        if g != "None":
            text = f"{g} {score:.0%}" + (f" -> {action}" if action else "")
            fs, th_ = 0.8 * k, max(1, int(2 * k))
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, fs, th_)
            pad, x0, y0 = int(10 * k), int(16 * k), int(16 * k)
            cv2.rectangle(img, (x0, y0), (x0 + tw + 2 * pad, y0 + th + 2 * pad), (20, 16, 12), -1)
            cv2.putText(img, text, (x0 + pad, y0 + th + pad), cv2.FONT_HERSHEY_SIMPLEX, fs,
                        cyan if action else white, th_, cv2.LINE_AA)

    def _override_name(self, g: str) -> str | None:
        if self.override is None:
            return None
        try:
            ov = self.override(g)
        except Exception:  # noqa: BLE001
            return None
        return ov[0] if ov else None

    # ---------- worker ----------
    def _load(self):
        import mediapipe as mp
        from mediapipe.tasks import python as mpt
        from mediapipe.tasks.python import vision

        self._mp = mp
        return vision.GestureRecognizer.create_from_options(vision.GestureRecognizerOptions(
            base_options=mpt.BaseOptions(model_asset_path=str(self.model_path)),
            running_mode=vision.RunningMode.VIDEO, num_hands=2))

    def _run(self) -> None:
        try:
            self._rec = self._load()
        except Exception as e:  # noqa: BLE001
            self._error = f"Моделът не се зареди: {e}"
            log.exception("gesture model")
            return
        seq, last_ts, times = 0, 0, []
        while not self._stop.is_set():
            if not self._enabled.wait(timeout=0.5):
                continue
            seq, frame = self.robot.wait_frame(seq, timeout=0.5)
            if frame is None or not self.enabled:
                continue
            try:
                self._process(frame, last_ts := max(last_ts + 1, int(time.monotonic() * 1000)))
            except Exception:  # noqa: BLE001
                log.exception("gesture frame")
                time.sleep(0.2)
            now = time.monotonic()
            times = [t for t in times if now - t < 1.0] + [now]
            self._proc_fps = len(times)

    def _process(self, frame: np.ndarray, ts_ms: int) -> None:
        h, w = frame.shape[:2]
        if w > PROC_WIDTH:
            frame = cv2.resize(frame, (PROC_WIDTH, int(h * PROC_WIDTH / w)), interpolation=cv2.INTER_AREA)
        img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        res = self._rec.recognize_for_video(img, ts_ms)
        g, score = "None", 0.0
        if res.gestures:
            top = res.gestures[0][0]
            g, score = top.category_name or "None", float(top.score)
        hands = [[(lm.x, lm.y) for lm in hand] for hand in (res.hand_landmarks or [])]
        trigger = override = None
        ov_name = self._override_name(g)
        with self._lock:
            self._streak = self._streak + 1 if g == self._gesture else 1
            self._gesture, self._score, self._hands = g, score, hands
            action = self.mapping.get(g)
            now = time.monotonic()
            if ov_name and self._streak == STREAK:
                # safety overrides (e.g. Open_Palm = stop following) ignore the cooldown
                override = ov_name
                self._last_trigger = {"gesture": g, "gesture_label": LABELS.get(g, g), "action": ov_name, "at": time.time()}
            elif action and self._streak == STREAK and now - self._last_sent > COOLDOWN:
                self._last_sent = now
                trigger = action
                self._last_trigger = {"gesture": g, "gesture_label": LABELS.get(g, g), "action": action, "at": time.time()}
        if override:
            log.info("GESTURE %s -> %s", g, override)
            try:
                self.override(g)[1]()
            except Exception:  # noqa: BLE001
                log.exception("gesture override")
        if trigger:
            log.info("GESTURE %s -> %s", g, trigger)
            if self.on_trigger:
                try:
                    self.on_trigger(trigger)
                except Exception:  # noqa: BLE001
                    log.exception("gesture on_trigger")
            try:
                self.robot.action(trigger)  # non-blocking submit to the robot loop
            except Exception as e:  # noqa: BLE001
                log.error("gesture action %s: %s", trigger, e)
