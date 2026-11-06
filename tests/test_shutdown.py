import asyncio

import remote_control as rc


def test_normal_shutdown_order(monkeypatch):
    async def scenario():
        events = []
        watchdog_started = asyncio.Event()
        worker_started = asyncio.Event()

        class MockApp:
            async def run_async(self):
                await asyncio.wait_for(
                    asyncio.gather(
                        watchdog_started.wait(),
                        worker_started.wait(),
                    ),
                    timeout=1.0,
                )
                events.append("APP_EXIT")

        async def mock_watchdog():
            try:
                watchdog_started.set()
                await asyncio.sleep(10)
            finally:
                events.append("WATCHDOG_EXIT")

        async def mock_worker():
            try:
                worker_started.set()
                await asyncio.sleep(10)
            finally:
                events.append("WORKER_EXIT")

        async def mock_dispatch(linear, angular):
            assert (linear, angular) == (0.0, 0.0)
            events.append("FINAL_STOP")

        monkeypatch.setattr(rc, "app", MockApp())
        monkeypatch.setattr(rc, "watchdog", mock_watchdog)
        monkeypatch.setattr(rc, "command_worker", mock_worker)
        monkeypatch.setattr(rc, "dispatch_command", mock_dispatch)
        monkeypatch.setattr(
            rc, "command_queue", rc.CommandQueue()
        )
        monkeypatch.setattr(
            rc, "update", lambda *args, **kwargs: None
        )

        await rc.main()

        assert events[0] == "APP_EXIT"
        assert set(events[1:3]) == {
            "WATCHDOG_EXIT",
            "WORKER_EXIT",
        }
        assert events[-1] == "FINAL_STOP"
        assert len(events) == 4

    asyncio.run(scenario())


def test_final_stop_timeout_activates_fault(monkeypatch):
    async def scenario():
        events = []
        queue = rc.CommandQueue()

        class MockApp:
            async def run_async(self):
                await asyncio.sleep(0)

        async def mock_background():
            await asyncio.sleep(10)

        async def blocked_stop(linear, angular):
            assert (linear, angular) == (0.0, 0.0)
            events.append("STOP_STARTED")
            await asyncio.sleep(10)
            events.append("STOP_COMPLETED")

        monkeypatch.setattr(rc, "app", MockApp())
        monkeypatch.setattr(rc, "watchdog", mock_background)
        monkeypatch.setattr(rc, "command_worker", mock_background)
        monkeypatch.setattr(rc, "dispatch_command", blocked_stop)
        monkeypatch.setattr(rc, "command_queue", queue)
        monkeypatch.setattr(
            rc, "update", lambda *args, **kwargs: None
        )

        await asyncio.wait_for(rc.main(), timeout=3.0)

        assert queue.fault
        assert events == ["STOP_STARTED"]
        assert queue.pending is None

    asyncio.run(scenario())


def test_final_stop_connection_error_activates_fault(monkeypatch):
    async def scenario():
        queue = rc.CommandQueue()
        events = []

        class MockApp:
            async def run_async(self):
                await asyncio.sleep(0)

        async def mock_background():
            await asyncio.sleep(10)

        async def failing_stop(linear, angular):
            assert (linear, angular) == (0.0, 0.0)
            events.append("STOP_ATTEMPTED")
            raise ConnectionError("Simulated connection loss")

        monkeypatch.setattr(rc, "app", MockApp())
        monkeypatch.setattr(rc, "watchdog", mock_background)
        monkeypatch.setattr(rc, "command_worker", mock_background)
        monkeypatch.setattr(rc, "dispatch_command", failing_stop)
        monkeypatch.setattr(rc, "command_queue", queue)
        monkeypatch.setattr(
            rc, "update", lambda *args, **kwargs: None
        )

        await asyncio.wait_for(rc.main(), timeout=3.0)

        assert events == ["STOP_ATTEMPTED"]
        assert queue.fault
        assert queue.pending is None
        assert queue.submit(0.1, 0.0) is None

    asyncio.run(scenario())


def test_final_stop_cancellation_activates_fault(monkeypatch):
    async def scenario():
        queue = rc.CommandQueue()
        stop_started = asyncio.Event()

        class MockApp:
            async def run_async(self):
                await asyncio.sleep(0)

        async def mock_background():
            await asyncio.sleep(10)

        async def blocked_stop(linear, angular):
            assert (linear, angular) == (0.0, 0.0)
            stop_started.set()
            await asyncio.sleep(10)

        monkeypatch.setattr(rc, "app", MockApp())
        monkeypatch.setattr(rc, "watchdog", mock_background)
        monkeypatch.setattr(rc, "command_worker", mock_background)
        monkeypatch.setattr(rc, "dispatch_command", blocked_stop)
        monkeypatch.setattr(rc, "command_queue", queue)
        monkeypatch.setattr(
            rc, "update", lambda *args, **kwargs: None
        )

        task = asyncio.create_task(rc.main())

        try:
            await asyncio.wait_for(
                stop_started.wait(),
                timeout=1.0,
            )

            task.cancel()

            try:
                await task
                assert False, "CancelledError was not propagated"
            except asyncio.CancelledError:
                pass

            assert queue.fault
            assert queue.pending is None

        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(
                    task,
                    return_exceptions=True,
                )

    asyncio.run(scenario())
