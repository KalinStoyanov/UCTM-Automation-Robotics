import asyncio

import remote_control as rc


def test_shutdown_cancels_inflight_motion_before_final_stop(monkeypatch):
    async def scenario():
        events = []
        motion_started = asyncio.Event()
        queue = rc.CommandQueue()

        class MockApp:
            async def run_async(self):
                queue.submit(0.1, 0.0)
                await asyncio.wait_for(motion_started.wait(), timeout=1.0)
                events.append("APP_EXIT")

        async def mock_watchdog():
            await asyncio.sleep(10)

        async def mock_dispatch(linear, angular):
            if linear != 0.0 or angular != 0.0:
                events.append("MOTION_STARTED")
                motion_started.set()
                try:
                    await asyncio.sleep(10)
                finally:
                    events.append("MOTION_CANCELLED")
            else:
                events.append("FINAL_STOP")

        monkeypatch.setattr(rc, "app", MockApp())
        monkeypatch.setattr(rc, "watchdog", mock_watchdog)
        monkeypatch.setattr(rc, "dispatch_command", mock_dispatch)
        monkeypatch.setattr(rc, "command_queue", queue)
        monkeypatch.setattr(
            rc, "update", lambda *args, **kwargs: None
        )

        await asyncio.wait_for(rc.main(), timeout=3.0)

        assert events == [
            "MOTION_STARTED",
            "APP_EXIT",
            "MOTION_CANCELLED",
            "FINAL_STOP",
        ]
        assert queue.fault is True
        assert queue.pending is None

    asyncio.run(scenario())
