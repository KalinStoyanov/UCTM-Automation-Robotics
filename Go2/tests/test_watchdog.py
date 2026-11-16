import asyncio

import remote_control as rc


def test_watchdog_timeout(monkeypatch):
    async def scenario():
        calls = []
        clock = [100.0]

        monkeypatch.setattr(rc, "WATCHDOG_TIMEOUT", 0.01)
        monkeypatch.setattr(rc, "last_motion_input", rc.time.monotonic() - 1.0)

        def mock_update(command, linear, angular, **kwargs):
            calls.append((command, linear, angular))
            rc.last_motion_input = None

        monkeypatch.setattr(rc, "update", mock_update)

        task = asyncio.create_task(rc.watchdog())
        try:
            await asyncio.sleep(0.08)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        assert calls == [("STOP (WATCHDOG)", 0.0, 0.0)]

    asyncio.run(scenario())


def test_watchdog_before_timeout(monkeypatch):
    async def scenario():
        calls = []
        clock = [100.0]

        monkeypatch.setattr(rc, "WATCHDOG_TIMEOUT", 0.5)
        monkeypatch.setattr(rc, "last_motion_input", rc.time.monotonic())
        monkeypatch.setattr(
            rc, "update",
            lambda *args, **kwargs: calls.append(args),
        )

        task = asyncio.create_task(rc.watchdog())
        try:
            await asyncio.sleep(0.08)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        assert calls == []

    asyncio.run(scenario())


def test_watchdog_does_not_repeat_stop(monkeypatch):
    async def scenario():
        calls = []
        monkeypatch.setattr(rc, "WATCHDOG_TIMEOUT", 0.01)
        monkeypatch.setattr(rc, "last_motion_input", rc.time.monotonic() - 1.0)

        def mock_update(command, linear, angular, **kwargs):
            calls.append(command)
            rc.last_motion_input = None

        monkeypatch.setattr(rc, "update", mock_update)

        task = asyncio.create_task(rc.watchdog())
        try:
            await asyncio.sleep(0.18)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        assert calls == ["STOP (WATCHDOG)"]

    asyncio.run(scenario())
