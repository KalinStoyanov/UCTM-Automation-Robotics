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

DDM2 = Path(__file__).resolve().parents[2] / "applications/dd-m2"
sys.path.insert(0, str(DDM2))

RobotInterface = importlib.import_module(
    "src.robot.robot_interface"
).RobotInterface


class MockGo2Transport(Go2Transport):
    def channel_ready(self):
        return self.state == "CONNECTED"


def run(coro):
    return asyncio.run(coro)


def test_ddm2_go2_motion_limits():
    async def scenario():
        robot = RobotInterface()
        robot.connection = MockGo2Transport(mode="SIMULATION")

        await robot.connect()
        try:
            result = await robot.move(1.0, -1.0, 2.0)

            params = robot.connection.last_request[
                "options"
            ]["parameter"]

            assert params["x"] == MAX_LINEAR_SPEED
            assert params["y"] == -MAX_LINEAR_SPEED
            assert params["z"] == MAX_ANGULAR_SPEED

            assert result["linear_m_s"] == MAX_LINEAR_SPEED
            assert result["linear_km_h"] == pytest.approx(
                MAX_LINEAR_SPEED * 3.6
            )
            assert result["angular_rad_s"] == MAX_ANGULAR_SPEED
            assert result["angular_deg_s"] == pytest.approx(
                math.degrees(MAX_ANGULAR_SPEED)
            )
        finally:
            await robot.disconnect()

    run(scenario())


def test_ddm2_go2_stop():
    async def scenario():
        robot = RobotInterface()
        robot.connection = MockGo2Transport(mode="SIMULATION")

        await robot.connect()
        try:
            await robot.move(0.1, 0.0, 0.0)
            await robot.stop()

            request = robot.connection.last_request
            assert request["options"]["parameter"] == {}
        finally:
            await robot.disconnect()

    run(scenario())


def test_ddm2_go2_rejects_nonfinite():
    async def scenario():
        robot = RobotInterface()
        robot.connection = MockGo2Transport(mode="SIMULATION")

        await robot.connect()
        try:
            with pytest.raises(ValueError):
                await robot.move(float("nan"), 0.0, 0.0)

            assert robot.connection.last_request is None
        finally:
            await robot.disconnect()

    run(scenario())


def test_ddm2_go2_watchdog_timeout():
    async def scenario():
        robot = RobotInterface(command_timeout=0.15)
        robot.connection = MockGo2Transport(mode="SIMULATION")

        await robot.connect()
        try:
            await robot.move(0.1, 0.0, 0.0)
            await asyncio.sleep(0.35)

            request = robot.connection.last_request
            assert request["options"]["parameter"] == {}
        finally:
            await robot.disconnect()

    run(scenario())


def test_ddm2_go2_connection_loss():
    async def scenario():
        robot = RobotInterface()
        robot.connection = MockGo2Transport(mode="SIMULATION")

        await robot.connect()
        try:
            await robot.move(0.1, 0.0, 0.0)

            # Simulate communication loss.
            await robot.connection.disconnect()

            assert not robot.connected

            with pytest.raises(RuntimeError):
                await robot.move(0.1, 0.0, 0.0)
        finally:
            await robot.disconnect()

    run(scenario())



def test_m7_combined_safety_lifecycle():
    async def scenario():
        robot = RobotInterface(command_timeout=0.15)
        robot.connection = MockGo2Transport(mode="SIMULATION")
        await robot.connect()

        try:
            # Normal movement and lateral movement.
            await robot.move(0.1, 0.0, 0.0)
            await robot.move(0.0, 0.1, 0.0)
            assert not robot.fault

            # Watchdog: STOP followed by persistent FAULT.
            await asyncio.sleep(0.35)
            assert robot.fault
            assert robot.stop_confirmed
            assert robot.connection.last_request["options"]["parameter"] == {}

            with pytest.raises(RuntimeError):
                await robot.move(0.1, 0.0, 0.0)

            # Explicit authorization restores movement.
            assert await robot.authorize_recovery()
            assert not robot.fault
            await robot.move(0.1, 0.0, 0.0)

            # Communication loss.
            await robot.connection.disconnect()
            with pytest.raises(RuntimeError):
                await robot.move(0.1, 0.0, 0.0)
            assert robot.fault

            # Reconnection alone cannot restore movement.
            await robot.connection.connect()
            with pytest.raises(RuntimeError):
                await robot.move(0.1, 0.0, 0.0)
            assert not await robot.authorize_recovery()

            # STOP and authorization are both required.
            await robot.stop()
            assert robot.stop_confirmed
            assert await robot.authorize_recovery()
            await robot.move(0.1, 0.0, 0.0)

            # A second fault must block movement again.
            robot.queue.set_fault()
            with pytest.raises(RuntimeError):
                await robot.move(0.1, 0.0, 0.0)
            assert robot.fault

        finally:
            await robot.disconnect()

    run(scenario())
