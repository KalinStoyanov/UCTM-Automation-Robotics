"""Operator-facing event log ("Дневник" in the UI): short Bulgarian lines, newest last."""
from __future__ import annotations

import collections
import itertools
import logging
import threading
import time
from typing import Any, Callable

log = logging.getLogger("go2.ui")

LEVELS = ("info", "ok", "warn", "danger")


class EventLog:
    def __init__(self, maxlen: int = 200) -> None:
        self._items: collections.deque[dict[str, Any]] = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._listeners: list[Callable[[dict[str, Any]], None]] = []

    def add(self, text: str, level: str = "info") -> dict[str, Any]:
        entry = {"id": next(self._ids), "t": time.time(), "text": text, "level": level if level in LEVELS else "info"}
        with self._lock:
            self._items.append(entry)
            listeners = list(self._listeners)
        log.log(logging.WARNING if level in ("warn", "danger") else logging.INFO, "UI %s", text)
        for fn in listeners:
            try:
                fn(entry)
            except Exception:  # noqa: BLE001
                log.exception("event listener")
        return entry

    def recent(self, n: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._items)[-n:]

    def texts(self) -> list[str]:
        with self._lock:
            return [e["text"] for e in self._items]

    def subscribe(self, fn: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            self._listeners.append(fn)
