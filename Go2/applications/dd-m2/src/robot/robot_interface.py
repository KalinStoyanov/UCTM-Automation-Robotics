"""DD-M2 RobotInterface backed by GO2 Core."""

import asyncio
import math
import time

from core.communication.go2_webrtc import Go2WebRTC
from core.communication.go2_transport import (
    MAX_LINEAR_SPEED,
    MAX_ANGULAR_SPEED,
)


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
        self.command_timeout = command_timeout
        self.last_command = time.monotonic()
        self.active = False
        self.watchdog_task = None

    @property
    def connected(self):
        return (
            self.connection.state == "CONNECTED"
            and self.connection.channel_ready()
        )

    async def connect(self):
        await self.connection.connect()
        self.active = True
        self.last_command = time.monotonic()
        self.watchdog_task = asyncio.create_task(self._watchdog())

    async def move(self, vx=0.0, vy=0.0, vyaw=0.0):
        if not all(math.isfinite(v) for v in (vx, vy, vyaw)):
            raise ValueError("Motion velocities must be finite")

        vx = max(-self.max_linear, min(self.max_linear, vx))
        vy = max(-self.max_linear, min(self.max_linear, vy))
        vyaw = max(-self.max_angular, min(self.max_angular, vyaw))

        await self.connection.send_move(vx, vy, vyaw)
        self.last_command = time.monotonic()

        return {
            "linear_m_s": vx,
            "linear_km_h": vx * 3.6,
            "angular_rad_s": vyaw,
            "angular_deg_s": math.degrees(vyaw),
        }

    async def stop(self):
        await self.connection.stop()
        self.last_command = time.monotonic()

    async def stand(self):
        await self.connection.stand()

    async def sit(self):
        await self.connection.sit()

    async def _watchdog(self):
        while self.active:
            await asyncio.sleep(0.1)
            if time.monotonic() - self.last_command > self.command_timeout:
                if self.connected:
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
