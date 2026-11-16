"""DD-M2 motion bridge with serialized command execution."""

import asyncio
import math
import threading
import time

from src.robot.robot_interface import RobotInterface


class MotionBridge:
    def __init__(
        self,
        mode="simulation",
        ip="192.168.12.1",
        command_timeout=0.4,
        stale_timeout=0.5,
    ):
        if mode not in ("simulation", "robot"):
            raise ValueError("Invalid mode")

        self.mode = mode
        self.ip = ip
        self.command_timeout = command_timeout
        self.stale_timeout = stale_timeout

        self.robot = None
        self.thread = None
        self.loop = None
        self.ready = threading.Event()
        self.error = None

        self.lock = threading.Lock()
        self.latest = None
        self.last_update = 0.0
        self.stop_latched = False
        self.active = False
        self.last_posture = "STANDING"

    def start(self):
        if self.mode == "simulation":
            return

        if self.active:
            raise RuntimeError("Bridge already active")

        self.ready.clear()
        self.error = None
        self.active = True

        self.thread = threading.Thread(
            target=self._thread_main,
            daemon=True,
        )
        self.thread.start()

        if not self.ready.wait(timeout=15):
            self.active = False
            raise TimeoutError("Robot connection timeout")

        if self.error:
            self.active = False
            raise self.error

    def _thread_main(self):
        try:
            asyncio.run(self._worker())
        except Exception as exc:
            self.error = exc
            self.ready.set()

    async def _send(self, operation):
        return await asyncio.wait_for(
            operation,
            timeout=self.command_timeout,
        )

    async def _safe_stop(self):
        await self._send(self.robot.stop())

    async def _worker(self):
        self.loop = asyncio.get_running_loop()
        self.robot = RobotInterface(ip=self.ip)

        try:
            await asyncio.wait_for(
                self.robot.connect(),
                timeout=10.0,
            )
            self.ready.set()

            while self.active:
                await asyncio.sleep(0.05)

                with self.lock:
                    result = self.latest
                    age = time.monotonic() - self.last_update
                    blocked = self.stop_latched

                if blocked or result is None or age > self.stale_timeout:
                    await self._safe_stop()
                    continue

                state = result["state"]
                posture = result.get("posture", "STANDING")
                motion = result["motion"]

                if state == "STOP":
                    await self._safe_stop()
                    continue

                if posture == "LYING":
                    await self._safe_stop()
                    continue

                if posture != self.last_posture:
                    await self._safe_stop()

                    with self.lock:
                        if self.stop_latched:
                            continue

                    if posture == "STANDING":
                        await self._send(self.robot.stand())
                    elif posture == "SITTING":
                        await self._send(self.robot.sit())
                    else:
                        raise ValueError("Unsupported posture")

                    self.last_posture = posture

                vx = float(motion["linear_m_s"])
                wz = float(motion["angular_rad_s"])

                if not math.isfinite(vx) or not math.isfinite(wz):
                    await self._safe_stop()
                    continue

                with self.lock:
                    if self.stop_latched:
                        continue

                if abs(vx) < 1e-6 and abs(wz) < 1e-6:
                    await self._safe_stop()
                else:
                    await self._send(
                        self.robot.move(vx=vx, vy=0.0, vyaw=wz)
                    )

        except Exception as exc:
            self.error = exc
            with self.lock:
                self.stop_latched = True
                self.latest = None
            raise

        finally:
            if self.robot:
                try:
                    await self._safe_stop()
                except Exception:
                    pass

                try:
                    await asyncio.wait_for(
                        self.robot.disconnect(),
                        timeout=3.0,
                    )
                except Exception:
                    pass

    def update(self, result):
        with self.lock:
            state = result["state"]

            if state == "STOP":
                self.stop_latched = True
                self.latest = result

            elif self.stop_latched:
                return

            else:
                self.latest = result

            self.last_update = time.monotonic()

    def reset_stop(self):
        with self.lock:
            if self.mode == "robot":
                if self.error is not None:
                    raise RuntimeError(
                        "Communication fault: reconnect required"
                    )
                if not self.active or not self.ready.is_set():
                    raise RuntimeError(
                        "Robot bridge is not active"
                    )

            self.stop_latched = False
            self.latest = None
            self.last_update = 0.0

    def close(self):
        if self.mode == "simulation":
            return

        with self.lock:
            self.stop_latched = True
            self.latest = None

        self.active = False

        if self.thread:
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                raise TimeoutError(
                    "MotionBridge thread did not terminate"
                )
