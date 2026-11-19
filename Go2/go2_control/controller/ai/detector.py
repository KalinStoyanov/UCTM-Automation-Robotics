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
# Pose for follow mode. Benchmarked on this Mac (person crops): YOLO11n-pose 8.5-11.4 ms per
# crop / 23.6 ms for 4 crops vs MediaPipe pose_landmarker_lite 11.7 ms / 49.8 ms.
POSE_MODEL = Path(__file__).resolve().parents[2] / "models" / "yolo11n-pose.pt"
CONF = 0.45
POSE_MAX_PERSONS = 4     # largest person boxes that get a pose estimate
POSE_IMGSZ = 320       # 256 misplaced wrists on tall full-body crops; 320 judged them right
KP_CONF = 0.4            # keypoint confidence needed to judge an arm


@dataclass(frozen=True)
class Box:
    x1: float  # normalized 0..1
    y1: float
    x2: float
    y2: float
    name: str
    conf: float
    arms: int | None = None   # arms above the head (0/1/2), None = pose not estimated / unsure
    kp: tuple | None = field(default=None, compare=False)  # 17 COCO keypoints (x, y, conf), normalized

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


def arms_raised(kp) -> int | None:
    """COCO keypoints [(x, y, conf)] in image coords (y down) -> number of wrists above the head.
    "Above the head" = above the top-most face keypoint by 30 % of the face-to-shoulder distance.
    None when the head or shoulders are not visible enough to judge."""
    head = [p for p in kp[0:5] if p[2] >= KP_CONF]          # nose, eyes, ears
    shoulders = [p for p in kp[5:7] if p[2] >= KP_CONF]
    if not head or not shoulders:
        return None
    head_y = min(p[1] for p in head)
    shoulder_y = sum(p[1] for p in shoulders) / len(shoulders)
    top = head_y - 0.3 * max(shoulder_y - head_y, 1e-6)
    return sum(1 for wr in (kp[9], kp[10]) if wr[2] >= KP_CONF and wr[1] < top)


class YoloDetector:
    def __init__(self, robot, model_path: Path = MODEL) -> None:
        self.robot = robot
        self.model_path = Path(model_path)
        self._users: set[str] = set()
        self._pose_users: set[str] = set()
        self._pose_model = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._model = None
        self._det = Detections()
        self._times: list[float] = []
        self.error = ""

    # ---- consumers ----
    def acquire(self, user: str, pose: bool = False) -> None:
        with self._lock:
            self._users.add(user)
            if pose:
                self._pose_users.add(user)
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._run, name="yolo", daemon=True)
                self._thread.start()
        self._wake.set()

    def release(self, user: str) -> None:
        with self._lock:
            self._users.discard(user)
            self._pose_users.discard(user)
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

    # ---- pose (follow mode) ----
    def _add_pose(self, frame, boxes: tuple) -> tuple:
        """Run YOLO11n-pose only on the largest person boxes (crops), set .arms / .kp."""
        if self._pose_model is None:
            from ultralytics import YOLO

            self._pose_model = YOLO(str(POSE_MODEL))
        h, w = frame.shape[:2]
        persons = sorted((b for b in boxes if b.name == "person"), key=lambda b: -b.area)[:POSE_MAX_PERSONS]
        if not persons:
            return boxes
        crops, origins = [], []
        for b in persons:
            # margin: a raised hand can stick out above the person box
            bw, bh = (b.x2 - b.x1) * w, (b.y2 - b.y1) * h
            x1, x2 = int(max(0, b.x1 * w - 0.15 * bw)), int(min(w, b.x2 * w + 0.15 * bw))
            y1, y2 = int(max(0, b.y1 * h - 0.25 * bh)), int(min(h, b.y2 * h + 0.05 * bh))
            crops.append(frame[y1:y2, x1:x2])
            origins.append((x1, y1))
        results = self._pose_model(crops, imgsz=POSE_IMGSZ, verbose=False)
        posed = {}
        for b, (ox, oy), res in zip(persons, origins, results):
            kps = res.keypoints
            if kps is None or kps.data is None or len(kps.data) == 0:
                continue
            # the pose of the largest skeleton in the crop belongs to this box
            areas = res.boxes.xywh[:, 2] * res.boxes.xywh[:, 3] if res.boxes is not None and len(res.boxes) else None
            i = int(areas.argmax()) if areas is not None else 0
            pts = [(float(x), float(y), float(c)) for x, y, c in kps.data[i].tolist()]
            arms = arms_raised(pts)
            kp = tuple(((x + ox) / w, (y + oy) / h, c) for x, y, c in pts)
            posed[id(b)] = Box(b.x1, b.y1, b.x2, b.y2, b.name, b.conf, arms, kp)
        return tuple(posed.get(id(b), b) for b in boxes)

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
                if self._pose_users:
                    boxes = self._add_pose(frame, boxes)
                now = time.monotonic()
                with self._lock:
                    self._det = Detections(self._det.seq + 1, now, boxes)
                    self._times = [t for t in self._times if now - t <= 1.0] + [now]
            except Exception:  # noqa: BLE001
                log.exception("yolo frame")
                time.sleep(0.2)
