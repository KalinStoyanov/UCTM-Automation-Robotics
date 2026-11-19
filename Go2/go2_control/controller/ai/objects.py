"""Object mode: YOLO11n detection overlay on the latest frame (no robot actions)."""
from __future__ import annotations

import collections
import logging
from typing import Any

import cv2
import numpy as np

log = logging.getLogger("go2.objects")

BG = {
    "person": "човек", "dog": "куче", "cat": "котка", "chair": "стол", "bottle": "бутилка",
    "cup": "чаша", "cell phone": "телефон", "laptop": "лаптоп", "backpack": "раница",
    "book": "книга", "tv": "екран", "couch": "диван", "dining table": "маса", "car": "кола",
}


class ObjectMode:
    def __init__(self, detector, skip_persons=lambda: False) -> None:
        self.detector = detector
        self.skip_persons = skip_persons  # follow mode draws persons itself
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, on: bool) -> None:
        self._enabled = bool(on)
        (self.detector.acquire if on else self.detector.release)("objects")
        log.info("object mode %s", "ON" if on else "OFF")

    def state(self) -> dict[str, Any]:
        boxes = self.detector.latest().boxes if self._enabled else ()
        counts = collections.Counter(b.name for b in boxes)
        return {
            "enabled": self._enabled,
            "ready": self.detector.ready,
            "objects": [{"name": n, "label": BG.get(n, n), "count": c} for n, c in counts.most_common(6)],
            "fps": self.detector.fps if self._enabled else 0.0,
            "error": self.detector.error,
        }

    def draw(self, img: np.ndarray) -> None:
        if not self._enabled:
            return
        skip = self.skip_persons()
        h, w = img.shape[:2]
        k = max(0.45, w / 1280)
        for b in self.detector.latest().boxes:
            if skip and b.name == "person":
                continue
            p1, p2 = (int(b.x1 * w), int(b.y1 * h)), (int(b.x2 * w), int(b.y2 * h))
            color = (250, 180, 80) if b.name == "person" else (200, 200, 200)
            t = max(1, int(2 * k))
            cv2.rectangle(img, p1, p2, color, t, cv2.LINE_AA)
            label = f"{b.name} {b.conf:.0%}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6 * k, t)
            pad = int(5 * k)
            cv2.rectangle(img, (p1[0], p1[1] - th - 2 * pad), (p1[0] + tw + 2 * pad, p1[1]), color, -1)
            cv2.putText(img, label, (p1[0] + pad, p1[1] - pad), cv2.FONT_HERSHEY_SIMPLEX, 0.6 * k, (20, 20, 20), t, cv2.LINE_AA)
