"""DD-M2 RobotInterface with M7 safety interlock."""

import asyncio
import math
import time

from core.communication.go2_webrtc import Go2WebRTC
from core.communication.go2_transport import (
    MAX_LINEAR_SPEED,
    MAX_ANGULAR_SPEED,
)
from core.control.remote_control import CommandQueue


class RobotInterface:
    def __init__(
        self,
        ip="192.168.12.1",
        max_linear=MAX_LINEAR_SPEED,
        max_angular=MAX_ANGULAR_SPEED,
        command_timeout=0.5,
    ):
        self.ip = ip
        self.connection = Go2WebRTC()
        self.max_linear = min(float(max_linear), MAX_LINEAR_SPEED)
        self.max_angular = min(float(max_angular), MAX_ANGULAR_SPEED)
        if self.max_linear <= 0 or self.max_angular <= 0:
            raise ValueError("Speed limits must be positive")
        if not math.isfinite(command_timeout) or command_timeout <= 0:
            raise ValueError("Invalid command timeout")

        self.command_timeout = command_timeout
        self.last_command = time.monotonic()
        self.active = False
        self.watchdog_task = None
        self.queue = CommandQueue()
        self.stop_confirmed = False
        self._lock = asyncio.Lock()

    @property
    def connected(self):
        return (
            self.connection.state == "CONNECTED"
            and self.connection.channel_ready()
        )

    @property
    def fault(self):
        return self.queue.fault

    async def connect(self):
        if self.active and self.watchdog_task:
            self.watchdog_task.cancel()
            try:
                await self.watchdog_task
            except asyncio.CancelledError:
                pass

        await self.connection.connect()
        self.active = True
        self.last_command = time.monotonic()
        self.watchdog_task = asyncio.create_task(self._watchdog())

    async def move(self, vx=0.0, vy=0.0, vyaw=0.0):
        async with self._lock:
            values = (float(vx), float(vy), float(vyaw))
            if not all(math.isfinite(v) for v in values):
                raise ValueError("Motion velocities must be finite")

            if not self.connected:
                self.queue.set_fault()
                self.stop_confirmed = False
                raise RuntimeError("Communication unavailable: FAULT")

            if self.fault:
                raise RuntimeError("Movement blocked: authorization required")

            vx = max(-self.max_linear, min(self.max_linear, values[0]))
            vy = max(-self.max_linear, min(self.max_linear, values[1]))
            vyaw = max(-self.max_angular, min(self.max_angular, values[2]))

            # Include lateral-only movement in the queue safety gate.
            gate_linear = vx if vx != 0.0 else vy
            if self.queue.submit(gate_linear, vyaw) is None:
                raise RuntimeError("Movement rejected by safety queue")

            command = self.queue.take()
            if command is None:
                raise RuntimeError("No command available")

            is_zero = vx == 0.0 and vy == 0.0 and vyaw == 0.0

            try:
                if is_zero:
                    await self.connection.stop()
                    self.stop_confirmed = True
                else:
                    await self.connection.send_move(vx, vy, vyaw)
                    self.stop_confirmed = False
            except BaseException:
                self.queue.set_fault()
                self.stop_confirmed = False
                raise
            finally:
                if is_zero and self.stop_confirmed:
                    self.queue.finish_stop()

            self.last_command = time.monotonic()
            return {
                "linear_m_s": vx,
                "linear_km_h": vx * 3.6,
                "angular_rad_s": vyaw,
                "angular_deg_s": math.degrees(vyaw),
            }

    async def stop(self):
        async with self._lock:
            self.queue.submit(0.0, 0.0)
            self.queue.take()
            self.stop_confirmed = False

            try:
                await self.connection.stop()
            except BaseException:
                self.queue.set_fault()
                raise

            self.queue.finish_stop()
            self.stop_confirmed = True
            self.last_command = time.monotonic()

    async def authorize_recovery(self):
        async with self._lock:
            if not self.connected or not self.stop_confirmed:
                return False
            if not self.queue.authorize_recovery():
                return False
            return self.queue.clear_fault()

    async def stand(self):
        async with self._lock:
            if self.fault or not self.connected:
                raise RuntimeError("Stand blocked by safety interlock")
            return await self.connection.stand()

    async def sit(self):
        async with self._lock:
            if self.fault or not self.connected:
                raise RuntimeError("Sit blocked by safety interlock")
            return await self.connection.sit()

    async def _watchdog(self):
        while self.active:
            await asyncio.sleep(0.1)

            if self.fault:
                continue

            if not self.connected:
                self.queue.set_fault()
                self.stop_confirmed = False
                continue

            if time.monotonic() - self.last_command > self.command_timeout:
                self.queue.set_fault()
                self.stop_confirmed = False
                try:
                    await self.stop()
                except Exception:
                    pass

    async def disconnect(self):
        self.active = False

        if self.watchdog_task:
            self.watchdog_task.cancel()
            try:
                await self.watchdog_task
            except asyncio.CancelledError:
                pass
            self.watchdog_task = None

        try:
            if self.connected:
                await self.stop()
        finally:
            await self.connection.disconnect()
