"""M25-A9: offline concurrency and STOP audit."""

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
    monkeypatch.setattr(rc, "vx", 0.0)
    monkeypatch.setattr(rc, "wz", 0.0)
    return rc


def run(coro):
    return asyncio.run(coro)


def test_a9_1_repeated_obstacle_during_stop(r, monkeypatch):
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()
        cancelled = []

        async def dispatch(v, w):
            if v == w == 0:
                started.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    cancelled.append("STOP")
                    raise

        monkeypatch.setattr(r, "dispatch_command", dispatch)

        r.observe_obstacle(CLEAR)
        r.obstacle_stop()

        worker = asyncio.create_task(r.command_worker())
        try:
            await asyncio.wait_for(started.wait(), 1)
            r.obstacle_stop()
            await asyncio.sleep(0.05)

            assert not cancelled, "Active STOP was cancelled"
            assert r.command_queue.stop_in_progress
        finally:
            release.set()
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    run(scenario())


def test_a9_2_sensor_fault_during_stop(r, monkeypatch):
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()
        cancelled = []

        async def dispatch(v, w):
            if v == w == 0:
                started.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    cancelled.append("STOP")
                    raise

        monkeypatch.setattr(r, "dispatch_command", dispatch)

        r.observe_obstacle(CLEAR)
        r.obstacle_stop()

        worker = asyncio.create_task(r.command_worker())
        try:
            await asyncio.wait_for(started.wait(), 1)
            r.observe_obstacle(None)
            await asyncio.sleep(0.05)

            assert not cancelled
            assert not r.stop_confirmed
        finally:
            release.set()
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    run(scenario())


def test_a9_3_move_blocked_during_stop(r, monkeypatch):
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()

        async def dispatch(v, w):
            if v == w == 0:
                started.set()
                await release.wait()

        monkeypatch.setattr(r, "dispatch_command", dispatch)

        r.observe_obstacle(CLEAR)
        r.obstacle_stop()

        worker = asyncio.create_task(r.command_worker())
        try:
            await asyncio.wait_for(started.wait(), 1)
            assert r.guarded_submit(0.1, 0) is None
            assert r.command_queue.stop_in_progress
        finally:
            release.set()
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    run(scenario())


def test_a9_4_failed_stop_latches_fault(r, monkeypatch):
    async def scenario():
        attempted = asyncio.Event()

        async def dispatch(v, w):
            if v == w == 0:
                attempted.set()
                raise ConnectionError("STOP failure")

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

    run(scenario())


def test_a9_5_explicit_restart_after_stop(r, monkeypatch):
    async def scenario():
        stopped = asyncio.Event()

        async def dispatch(v, w):
            if v == w == 0:
                stopped.set()

        monkeypatch.setattr(r, "dispatch_command", dispatch)

        r.observe_obstacle(CLEAR)
        r.obstacle_stop()

        worker = asyncio.create_task(r.command_worker())
        try:
            await asyncio.wait_for(stopped.wait(), 1)
            await asyncio.sleep(0.05)

            assert r.stop_confirmed
            assert r.obstacle_latched
            assert r.guarded_submit(0.1, 0) is not None
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    run(scenario())


def test_a9_6_repeated_stop_preserves_latch(r):
    r.observe_obstacle(CLEAR)
    r.obstacle_stop()
    first = r.command_queue.pending

    r.obstacle_stop()
    second = r.command_queue.pending

    assert r.obstacle_latched
    assert not r.stop_confirmed
    assert first[1:] == (0, 0)
    assert second[1:] == (0, 0)
    assert r.guarded_submit(0.1, 0) is None


def test_a9_7_invalid_sensor_stops_motion(r):
    r.observe_obstacle(CLEAR)
    r.active_velocity = (0.1, 0.0)

    assert r.observe_obstacle(None) is False
    assert r.obstacle_latched
    assert r.status == "SENSOR_FAULT"
    assert r.command_queue.pending[1:] == (0, 0)


def test_a9_8_no_restart_after_cancelled_stop(r, monkeypatch):
    async def scenario():
        started = asyncio.Event()

        async def dispatch(v, w):
            if v == w == 0:
                started.set()
                await asyncio.sleep(10)

        monkeypatch.setattr(r, "dispatch_command", dispatch)

        r.observe_obstacle(CLEAR)
        r.obstacle_stop()

        worker = asyncio.create_task(r.command_worker())
        try:
            await asyncio.wait_for(started.wait(), 1)
            r.obstacle_stop()
            await asyncio.sleep(0.05)

            assert not r.stop_confirmed
            assert r.guarded_submit(0.1, 0) is None
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    run(scenario())
