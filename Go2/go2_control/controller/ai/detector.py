"""Shared YOLO11n detector: one thread, runs while at least one consumer needs it."""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

os.environ.setdefault("YOLO_OFFLINE", "1")  # never try to reach the internet on the robot WiFi

log = logging.getLogger("go2.detector")

MODEL = Path(__file__).resolve().parents[2] / "models" / "yolo11n.pt"
CONF = 0.45


@dataclass(frozen=True)
class Box:
    x1: float  # normalized 0..1
    y1: float
    x2: float
    y2: float
    name: str
    conf: float

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def h(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return max(0.0, self.x2 - self.x1) * max(0.0, self.y2 - self.y1)


@dataclass(frozen=True)
class Detections:
    seq: int = 0            # increments with every processed frame
    t: float = 0.0          # time.monotonic() when produced
    boxes: tuple[Box, ...] = field(default_factory=tuple)

    def persons(self, min_conf: float = 0.0) -> list[Box]:
        return [b for b in self.boxes if b.name == "person" and b.conf >= min_conf]


class YoloDetector:
    def __init__(self, robot, model_path: Path = MODEL) -> None:
        self.robot = robot
        self.model_path = Path(model_path)
        self._users: set[str] = set()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._model = None
        self._det = Detections()
        self._times: list[float] = []
        self.error = ""

    # ---- consumers ----
    def acquire(self, user: str) -> None:
        with self._lock:
            self._users.add(user)
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._run, name="yolo", daemon=True)
                self._thread.start()
        self._wake.set()

    def release(self, user: str) -> None:
        with self._lock:
            self._users.discard(user)
            if not self._users:
                self._det = Detections(seq=self._det.seq, t=time.monotonic())
                self._wake.clear()

    @property
    def active(self) -> bool:
        return bool(self._users)

    @property
    def ready(self) -> bool:
        return self._model is not None

    def latest(self) -> Detections:
        with self._lock:
            return self._det

    @property
    def fps(self) -> float:
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._times if now - t <= 1.0]
        return float(len(recent)) if recent and now - recent[-1] < 1.0 else 0.0

    def close(self) -> None:
        self._stop.set()
        self._wake.set()

    # ---- worker ----
    def _run(self) -> None:
        try:
            from ultralytics import YOLO

            self._model = YOLO(str(self.model_path))
        except Exception as e:  # noqa: BLE001
            self.error = f"Моделът не се зареди: {e}"
            log.exception("yolo model")
            return
        seq = 0
        while not self._stop.is_set():
            if not self._wake.wait(timeout=0.5) or not self.active:
                continue
            seq, frame = self.robot.wait_frame(seq, timeout=0.5)
            if frame is None or not self.active:
                continue
            try:
                h, w = frame.shape[:2]
                r = self._model(frame, imgsz=640, conf=CONF, verbose=False)[0]
                boxes = tuple(
                    Box(x1 / w, y1 / h, x2 / w, y2 / h, r.names[int(k)], float(c))
                    for (x1, y1, x2, y2), c, k in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist())
                )
                now = time.monotonic()
                with self._lock:
                    self._det = Detections(self._det.seq + 1, now, boxes)
                    self._times = [t for t in self._times if now - t <= 1.0] + [now]
            except Exception:  # noqa: BLE001
                log.exception("yolo frame")
                time.sleep(0.2)
