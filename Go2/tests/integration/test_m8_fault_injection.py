import asyncio
import importlib
import sys
from pathlib import Path

import pytest

from core.communication.go2_transport import Go2Transport

DDM2 = Path(__file__).resolve().parents[2] / "applications/dd-m2"
sys.path.insert(0, str(DDM2))

RobotInterface = importlib.import_module(
    "src.robot.robot_interface"
).RobotInterface


class FaultTransport(Go2Transport):
    def __init__(self):
        super().__init__(mode="SIMULATION")
        self.fail_stop = False
        self.fail_move = False
        self.delay_move = 0.0
        self.channel_open = True
        self.history = []

    def channel_ready(self):
        return self.state == "CONNECTED" and self.channel_open

    async def send_move(self, vx=0.0, vy=0.0, wz=0.0):
        if self.delay_move:
            await asyncio.sleep(self.delay_move)

        if self.fail_move:
            raise TimeoutError("Injected movement timeout")

        result = await super().send_move(vx, vy, wz)
        self.history.append(("MOVE", vx, vy, wz))
        return result

    async def stop(self):
        if self.fail_stop:
            raise TimeoutError("Injected STOP failure")

        result = await super().stop()
        self.history.append(("STOP",))
        return result


def run(coro):
    return asyncio.run(coro)


def test_m8_combined_fault_injection():
    async def scenario():
        robot = RobotInterface(command_timeout=1.0)
        transport = FaultTransport()
        robot.connection = transport

        await robot.connect()

        try:
            # M8.1: STOP failure.
            await robot.move(0.1, 0.0, 0.0)
            transport.fail_stop = True

            with pytest.raises(TimeoutError):
                await robot.stop()

            assert robot.fault
            assert not robot.stop_confirmed
            assert not await robot.authorize_recovery()

            transport.fail_stop = False
            await robot.stop()
            assert await robot.authorize_recovery()

            # M8.2: Movement timeout.
            transport.fail_move = True

            with pytest.raises(TimeoutError):
                await robot.move(0.1, 0.0, 0.0)

            assert robot.fault
            transport.fail_move = False

            await robot.stop()
            assert await robot.authorize_recovery()

            # M8.3: DataChannel loss.
            transport.channel_open = False

            with pytest.raises(RuntimeError):
                await robot.move(0.1, 0.0, 0.0)

            assert robot.fault
            assert not await robot.authorize_recovery()

            transport.channel_open = True
            await robot.stop()
            assert await robot.authorize_recovery()

            # M8.4: Concurrent commands.
            transport.delay_move = 0.05
            transport.history.clear()

            await asyncio.gather(
                robot.move(0.1, 0.0, 0.0),
                robot.move(0.0, 0.1, 0.0),
            )

            assert len(transport.history) == 2
            assert transport.history[0][0] == "MOVE"
            assert transport.history[1][0] == "MOVE"

            transport.delay_move = 0.0

            # M8.5: Cancellation during movement.
            transport.delay_move = 0.5

            task = asyncio.create_task(
                robot.move(0.1, 0.0, 0.0)
            )
            await asyncio.sleep(0.05)
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await task

            assert robot.fault

            transport.delay_move = 0.0

            # M8.6: No stale commands after recovery.
            with pytest.raises(RuntimeError):
                await robot.move(0.1, 0.0, 0.0)

            transport.history.clear()
            await robot.stop()
            assert await robot.authorize_recovery()

            assert transport.history == [("STOP",)]

            await robot.move(0.1, 0.0, 0.0)
            assert transport.history[-1][0] == "MOVE"

        finally:
            await robot.disconnect()

    run(scenario())
