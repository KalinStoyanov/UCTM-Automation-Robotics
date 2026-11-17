"""M25-A7: offline obstacle safety integration tests."""

import asyncio
import pytest

from core.control import remote_control as rc
from core.safety.obstacle import Clearance, ObstacleSafetyFilter


CLEAR = Clearance(2.0, 2.0, 2.0, 2.0, 2.0)
BLOCKED = Clearance(0.1, 2.0, 2.0, 2.0, 2.0)
TURN_BLOCKED = Clearance(2.0, 2.0, 2.0, 2.0, 0.1)


@pytest.fixture
def isolated(monkeypatch):
    """Fresh queue, sensor and controller state per test."""
    monkeypatch.setattr(rc, "command_queue", rc.CommandQueue())
    monkeypatch.setattr(rc, "obstacle_safety", ObstacleSafetyFilter())
    monkeypatch.setattr(rc, "obstacle_latched", False)
    monkeypatch.setattr(rc, "active_velocity", (0.0, 0.0))
    monkeypatch.setattr(rc, "active_dispatch_task", None)
    monkeypatch.setattr(rc, "stop_generation", 0)
    monkeypatch.setattr(rc, "status", "READY")
    monkeypatch.setattr(rc, "vx", 0.0)
    monkeypatch.setattr(rc, "wz", 0.0)
    return rc


def test_obstacle_replaces_pending_move(isolated):
    r = isolated
    r.observe_obstacle(CLEAR)
    assert r.guarded_submit(0.1, 0.0) is not None

    r.observe_obstacle(BLOCKED)
    assert r.obstacle_latched
    assert r.command_queue.pending[1:] == (0.0, 0.0)
    assert r.status == "STOPPED_OBSTACLE"


def test_clearance_does_not_auto_resume(isolated):
    r = isolated
    r.observe_obstacle(CLEAR)
    r.guarded_submit(0.1, 0.0)
    r.observe_obstacle(BLOCKED)
    r.observe_obstacle(CLEAR)

    assert r.obstacle_latched
    assert r.command_queue.pending[1:] == (0.0, 0.0)


def test_new_command_waits_for_stop_completion(isolated, monkeypatch):
    r = isolated

    async def scenario():
        stop_started = asyncio.Event()
        allow_stop = asyncio.Event()
        stop_completed = asyncio.Event()

        async def dispatch(linear, angular):
            if linear == angular == 0.0:
                stop_started.set()
                await allow_stop.wait()
                stop_completed.set()

        monkeypatch.setattr(r, "dispatch_command", dispatch)

        r.observe_obstacle(CLEAR)
        r.guarded_submit(0.1, 0.0)
        r.observe_obstacle(BLOCKED)
        r.observe_obstacle(CLEAR)

        assert r.obstacle_latched
        assert r.guarded_submit(0.1, 0.0) is None

        worker = asyncio.create_task(r.command_worker())
        try:
            await asyncio.wait_for(stop_started.wait(), 1.0)

            assert r.command_queue.stop_in_progress
            assert not r.stop_confirmed
            assert r.guarded_submit(0.1, 0.0) is None

            allow_stop.set()
            await asyncio.wait_for(stop_completed.wait(), 1.0)

            for _ in range(100):
                if r.stop_confirmed and not r.command_queue.stop_in_progress:
                    break
                await asyncio.sleep(0.01)

            assert r.stop_confirmed
            assert not r.command_queue.stop_in_progress
            assert r.obstacle_latched

            assert r.guarded_submit(0.1, 0.0) is not None
            assert not r.obstacle_latched
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(scenario())


def test_stale_sensor_blocks_motion(isolated):
    r = isolated
    now = [100.0]
    r.obstacle_safety = ObstacleSafetyFilter(
        max_age=0.25, clock=lambda: now[0]
    )
    r.observe_obstacle(CLEAR)
    now[0] += 0.30

    assert r.guarded_submit(0.1, 0.0) is None
    assert r.obstacle_latched
    assert r.status == "SENSOR_FAULT"
    assert r.command_queue.pending[1:] == (0.0, 0.0)


def test_turning_obstacle_stops(isolated):
    r = isolated
    r.observe_obstacle(CLEAR)
    r.guarded_submit(0.0, 0.2)
    r.observe_obstacle(TURN_BLOCKED)

    assert r.obstacle_latched
    assert r.command_queue.pending[1:] == (0.0, 0.0)


def test_obstacle_cancels_active_move(isolated, monkeypatch):
    r = isolated

    async def scenario():
        started = asyncio.Event()
        cancelled = asyncio.Event()
        stopped = asyncio.Event()
        events = []

        async def dispatch(linear, angular):
            if linear == angular == 0.0:
                events.append("STOP")
                stopped.set()
                return

            events.append("MOVE")
            started.set()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                events.append("CANCEL")
                cancelled.set()
                raise

        monkeypatch.setattr(r, "dispatch_command", dispatch)
        r.observe_obstacle(CLEAR)

        worker = asyncio.create_task(r.command_worker())
        try:
            assert r.guarded_submit(0.1, 0.0) is not None
            await asyncio.wait_for(started.wait(), 1.0)

            r.observe_obstacle(BLOCKED)

            await asyncio.wait_for(cancelled.wait(), 1.0)
            await asyncio.wait_for(stopped.wait(), 1.0)

            assert events == ["MOVE", "CANCEL", "STOP"]
            assert r.obstacle_latched
            assert not r.command_queue.fault
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(scenario())


def test_stop_transport_failure_sets_fault(isolated, monkeypatch):
    r = isolated

    async def scenario():
        stop_attempted = asyncio.Event()

        async def dispatch(linear, angular):
            if linear == angular == 0.0:
                stop_attempted.set()
                raise ConnectionError("Simulated STOP failure")

        monkeypatch.setattr(r, "dispatch_command", dispatch)
        r.observe_obstacle(BLOCKED)
        r.obstacle_stop()

        worker = asyncio.create_task(r.command_worker())
        try:
            await asyncio.wait_for(stop_attempted.wait(), 1.0)
            await asyncio.sleep(0.05)

            assert r.command_queue.fault
            assert r.guarded_submit(0.1, 0.0) is None
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(scenario())
