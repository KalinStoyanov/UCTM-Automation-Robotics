import asyncio

import remote_control as rc


def test_worker_cancellation_activates_fault(monkeypatch):
    async def scenario():
        queue = rc.CommandQueue()
        started = asyncio.Event()

        async def mock_dispatch(linear, angular):
            started.set()
            await asyncio.sleep(10)

        monkeypatch.setattr(rc, "command_queue", queue)
        monkeypatch.setattr(rc, "dispatch_command", mock_dispatch)

        worker = asyncio.create_task(rc.command_worker())

        try:
            queue.submit(0.1, 0.0)

            await asyncio.wait_for(
                started.wait(),
                timeout=1.0,
            )

            worker.cancel()

            try:
                await worker
            except asyncio.CancelledError:
                pass

            assert worker.cancelled()
            assert queue.fault
            assert queue.pending is None
            assert queue.submit(0.1, 0.0) is None
            assert queue.submit(0.0, 0.0) is not None

        finally:
            if not worker.done():
                worker.cancel()
                await asyncio.gather(
                    worker,
                    return_exceptions=True,
                )

    asyncio.run(scenario())


def test_worker_communication_failure(monkeypatch):
    async def scenario():
        queue = rc.CommandQueue()
        events = []
        move_failed = asyncio.Event()
        stop_completed = asyncio.Event()

        async def mock_dispatch(linear, angular):
            if linear == 0.0 and angular == 0.0:
                events.append("STOP")
                stop_completed.set()
                return

            events.append("MOVE_FAILED")
            move_failed.set()
            raise ConnectionError("Simulated communication failure")

        monkeypatch.setattr(rc, "command_queue", queue)
        monkeypatch.setattr(rc, "dispatch_command", mock_dispatch)

        worker = asyncio.create_task(rc.command_worker())

        try:
            queue.submit(0.1, 0.0)

            await asyncio.wait_for(
                move_failed.wait(),
                timeout=1.0,
            )

            # Allow the worker to process the exception.
            await asyncio.sleep(0.05)

            assert queue.fault
            assert queue.submit(0.1, 0.0) is None

            assert queue.submit(0.0, 0.0) is not None

            await asyncio.wait_for(
                stop_completed.wait(),
                timeout=1.0,
            )

            assert events == ["MOVE_FAILED", "STOP"]
            assert queue.fault
            assert not worker.done()

        finally:
            worker.cancel()
            await asyncio.gather(
                worker,
                return_exceptions=True,
            )

    asyncio.run(scenario())
