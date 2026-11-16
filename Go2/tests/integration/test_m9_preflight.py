import asyncio
import importlib
import math
import sys
from pathlib import Path

import pytest

from core.communication.go2_transport import (
    Go2Transport,
    MAX_LINEAR_SPEED,
    MAX_ANGULAR_SPEED,
)
from core.communication.go2_webrtc import LIVE_ENABLED

DDM2 = Path(__file__).resolve().parents[2] / "applications/dd-m2"
sys.path.insert(0, str(DDM2))

RobotInterface = importlib.import_module(
    "src.robot.robot_interface"
).RobotInterface


class PreflightTransport(Go2Transport):
    def channel_ready(self):
        return self.state == "CONNECTED"


def test_m9_combined_preflight():
    async def scenario():
        # Configuration and initial state.
        assert LIVE_ENABLED is False
        assert MAX_LINEAR_SPEED == pytest.approx(0.20)
        assert MAX_ANGULAR_SPEED == pytest.approx(0.30)

        robot = RobotInterface(command_timeout=1.0)
        robot.connection = PreflightTransport(mode="SIMULATION")

        assert not robot.connected
        assert not robot.active
        assert not robot.fault

        # Motion is forbidden before connection.
        with pytest.raises(RuntimeError):
            await robot.move(0.1, 0.0, 0.0)

        assert robot.fault

        await robot.connect()

        try:
            # Connection alone must not clear FAULT.
            assert robot.connected
            assert robot.fault

            with pytest.raises(RuntimeError):
                await robot.move(0.1, 0.0, 0.0)

            assert not await robot.authorize_recovery()

            # STOP + explicit authorization.
            await robot.stop()
            assert robot.stop_confirmed
            assert await robot.authorize_recovery()
            assert not robot.fault

            # Velocity limits and unit conversions.
            result = await robot.move(1.0, -1.0, 2.0)
            params = robot.connection.last_request[
                "options"
            ]["parameter"]

            assert params["x"] == pytest.approx(0.20)
            assert params["y"] == pytest.approx(-0.20)
            assert params["z"] == pytest.approx(0.30)

            assert result["linear_m_s"] == pytest.approx(0.20)
            assert result["linear_km_h"] == pytest.approx(0.72)
            assert result["angular_rad_s"] == pytest.approx(0.30)
            assert result["angular_deg_s"] == pytest.approx(
                math.degrees(0.30)
            )

            # Repeated fault must block movement.
            robot.queue.set_fault()

            with pytest.raises(RuntimeError):
                await robot.move(0.1, 0.0, 0.0)

            assert robot.fault

            # STOP and recovery restore operation.
            await robot.stop()
            assert await robot.authorize_recovery()
            await robot.move(0.1, 0.0, 0.0)

        finally:
            await robot.disconnect()

        assert not robot.connected
        assert not robot.active
        assert robot.watchdog_task is None

    asyncio.run(scenario())
