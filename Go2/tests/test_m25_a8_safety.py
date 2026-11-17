"""M25-A8: concurrent STOP safety, offline only."""

import asyncio
import pytest

from core.control import remote_control as rc
from core.safety.obstacle import Clearance, ObstacleSafetyFilter

CLEAR = Clearance(2, 2, 2, 2, 2)
BLOCKED = Clearance(0.1, 2, 2, 2, 2)


@pytest.fixture
def r(monkeypatch):
    monkeypatch.setattr(rc, "command_queue", rc.CommandQueue())
    monkeypatch.setattr(rc, "obstacle_safety", ObstacleSafetyFilter())
    monkeypatch.setattr(rc, "obstacle_latched", False)
    monkeypatch.setattr(rc, "active_velocity", (0.0, 0.0))
    monkeypatch.setattr(rc, "active_dispatch_task", None)
    monkeypatch.setattr(rc, "stop_generation", 0)
    monkeypatch.setattr(rc, "stop_confirmed", False)
    monkeypatch.setattr(rc, "status", "READY")
    return rc


def test_pending_stop_blocks_new_move(r):
    r.observe_obstacle(CLEAR)
    r.guarded_submit(0.1, 0)
    r.observe_obstacle(BLOCKED)
    r.observe_obstacle(CLEAR)

    assert r.obstacle_latched
    assert not r.stop_confirmed
    assert r.guarded_submit(0.1, 0) is None
    assert r.command_queue.pending[1:] == (0, 0)


def test_stop_requires_successful_completion(r):
    r.observe_obstacle(CLEAR)
    r.obstacle_stop()

    assert r.guarded_submit(0.1, 0) is None

    stop = r.command_queue.take()
    assert stop[1:] == (0, 0)
    assert r.command_queue.stop_in_progress

    r.command_queue.finish_stop()

    assert not r.stop_confirmed
    assert r.guarded_submit(0.1, 0) is None


def test_stale_sensor_during_motion(r):
    now = [100.0]
    r.obstacle_safety = ObstacleSafetyFilter(
        max_age=0.25, clock=lambda: now[0]
    )
    r.observe_obstacle(CLEAR)
    r.active_velocity = (0.1, 0.0)

    now[0] += 0.30

    async def scenario():
        task = asyncio.create_task(r.obstacle_monitor())
        try:
            await asyncio.sleep(0.06)
            assert r.obstacle_latched
            assert r.status == "SENSOR_FAULT"
            assert r.command_queue.pending[1:] == (0, 0)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_stop_failure_blocks_restart(r, monkeypatch):
    async def scenario():
        attempted = asyncio.Event()

        async def dispatch(linear, angular):
            if linear == angular == 0:
                attempted.set()
                raise ConnectionError("STOP failed")

        monkeypatch.setattr(r, "dispatch_command", dispatch)
        r.observe_obstacle(CLEAR)
        r.obstacle_stop()

        worker = asyncio.create_task(r.command_worker())
        try:
            await asyncio.wait_for(attempted.wait(), 1)
            await asyncio.sleep(0.05)

            assert r.command_queue.fault
            assert not r.stop_confirmed
            assert r.guarded_submit(0.1, 0) is None
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(scenario())


def test_successful_stop_then_explicit_restart(r, monkeypatch):
    async def scenario():
        stopped = asyncio.Event()

        async def dispatch(linear, angular):
            if linear == angular == 0:
                stopped.set()

        monkeypatch.setattr(r, "dispatch_command", dispatch)

        r.observe_obstacle(CLEAR)
        r.obstacle_stop()

        worker = asyncio.create_task(r.command_worker())
        try:
            await asyncio.wait_for(stopped.wait(), 1)
            await asyncio.sleep(0.05)

            assert r.stop_confirmed
            assert not r.command_queue.stop_in_progress
            assert r.obstacle_latched

            assert r.guarded_submit(0.1, 0) is not None
            assert not r.obstacle_latched
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(scenario())
