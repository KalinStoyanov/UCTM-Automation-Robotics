import asyncio
import pytest

import go2_webrtc as gw


def test_live_connection_disabled():
    assert gw.LIVE_ENABLED is False

    adapter = gw.Go2WebRTC()

    assert adapter.state == "DISCONNECTED"
    assert adapter.channel_ready() is False

    async def scenario():
        with pytest.raises(
            RuntimeError,
            match="LIVE WebRTC connection is disabled",
        ):
            await adapter.connect()

    asyncio.run(scenario())

    assert adapter.state == "DISCONNECTED"
    assert adapter.connection is None


@pytest.mark.parametrize(
    "method_name",
    ["send_move", "stop"],
)
def test_live_commands_disabled(method_name):
    assert gw.LIVE_ENABLED is False

    adapter = gw.Go2WebRTC()

    async def scenario():
        method = getattr(adapter, method_name)

        with pytest.raises(
            RuntimeError,
            match="LIVE WebRTC connection is disabled",
        ):
            await method()

    asyncio.run(scenario())

    assert adapter.state == "DISCONNECTED"
    assert adapter.connection is None


def test_closed_datachannel_not_ready():
    from types import SimpleNamespace

    adapter = gw.Go2WebRTC()

    channel = SimpleNamespace(readyState="closed")
    datachannel = SimpleNamespace(
        data_channel_opened=True,
        channel=channel,
    )
    adapter.connection = SimpleNamespace(
        datachannel=datachannel,
    )

    assert adapter.channel_ready() is False

    channel.readyState = "open"
    assert adapter.channel_ready() is True

    datachannel.data_channel_opened = False
    assert adapter.channel_ready() is False


def test_send_request_rejects_closed_channel(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(gw, "LIVE_ENABLED", True)

    adapter = gw.Go2WebRTC()
    adapter.state = "CONNECTED"

    channel = SimpleNamespace(readyState="closed")
    datachannel = SimpleNamespace(
        data_channel_opened=True,
        channel=channel,
    )
    adapter.connection = SimpleNamespace(
        datachannel=datachannel,
    )

    async def scenario():
        with pytest.raises(
            RuntimeError,
            match="WebRTC DataChannel is not ready",
        ):
            await adapter.send_request({
                "topic": "test",
                "options": {},
            })

    asyncio.run(scenario())

    assert adapter.state == "ERROR"
    assert channel.readyState == "closed"


def test_send_request_timeout_sets_error(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(gw, "LIVE_ENABLED", True)

    async def mock_publish(topic, options):
        raise asyncio.TimeoutError()

    async def mock_wait_for(awaitable, timeout):
        return await awaitable

    monkeypatch.setattr(gw.asyncio, "wait_for", mock_wait_for)

    channel = SimpleNamespace(readyState="open")
    datachannel = SimpleNamespace(
        data_channel_opened=True,
        channel=channel,
        pub_sub=SimpleNamespace(
            publish_request_new=mock_publish,
        ),
    )

    adapter = gw.Go2WebRTC()
    adapter.state = "CONNECTED"
    adapter.connection = SimpleNamespace(
        datachannel=datachannel,
    )

    async def scenario():
        with pytest.raises(asyncio.TimeoutError):
            await adapter.send_request({
                "topic": "test",
                "options": {},
            })

    asyncio.run(scenario())

    assert adapter.state == "ERROR"


def test_send_request_connection_error_sets_error(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(gw, "LIVE_ENABLED", True)

    async def mock_publish(topic, options):
        raise ConnectionError("Simulated WebRTC connection loss")

    channel = SimpleNamespace(readyState="open")
    datachannel = SimpleNamespace(
        data_channel_opened=True,
        channel=channel,
        pub_sub=SimpleNamespace(
            publish_request_new=mock_publish,
        ),
    )

    adapter = gw.Go2WebRTC()
    adapter.state = "CONNECTED"
    adapter.connection = SimpleNamespace(
        datachannel=datachannel,
    )

    async def scenario():
        with pytest.raises(
            ConnectionError,
            match="Simulated WebRTC connection loss",
        ):
            await adapter.send_request({
                "topic": "test",
                "options": {},
            })

    asyncio.run(scenario())

    assert adapter.state == "ERROR"


def test_send_request_cancellation_sets_error(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(gw, "LIVE_ENABLED", True)

    started = asyncio.Event()

    async def mock_publish(topic, options):
        started.set()
        await asyncio.sleep(10)

    channel = SimpleNamespace(readyState="open")
    datachannel = SimpleNamespace(
        data_channel_opened=True,
        channel=channel,
        pub_sub=SimpleNamespace(
            publish_request_new=mock_publish,
        ),
    )

    adapter = gw.Go2WebRTC()
    adapter.state = "CONNECTED"
    adapter.connection = SimpleNamespace(
        datachannel=datachannel,
    )

    async def scenario():
        task = asyncio.create_task(
            adapter.send_request({
                "topic": "test",
                "options": {},
            })
        )

        try:
            await asyncio.wait_for(started.wait(), timeout=1.0)
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await task

            assert adapter.state == "ERROR"

        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(
                    task,
                    return_exceptions=True,
                )

    asyncio.run(scenario())


def test_disconnect_success():
    from types import SimpleNamespace

    calls = []

    async def mock_disconnect():
        calls.append("disconnect")

    adapter = gw.Go2WebRTC()
    adapter.state = "CONNECTED"
    adapter.connection = SimpleNamespace(
        disconnect=mock_disconnect,
    )

    asyncio.run(adapter.disconnect())

    assert calls == ["disconnect"]
    assert adapter.state == "DISCONNECTED"
    assert adapter.connection is None


def test_disconnect_connection_error():
    from types import SimpleNamespace

    async def mock_disconnect():
        raise ConnectionError("Simulated disconnect failure")

    adapter = gw.Go2WebRTC()
    adapter.state = "CONNECTED"
    adapter.connection = SimpleNamespace(
        disconnect=mock_disconnect,
    )

    with pytest.raises(ConnectionError):
        asyncio.run(adapter.disconnect())

    assert adapter.state == "ERROR"
    assert adapter.connection is not None


def test_disconnect_timeout(monkeypatch):
    from types import SimpleNamespace

    async def mock_disconnect():
        raise asyncio.TimeoutError("Simulated disconnect timeout")

    adapter = gw.Go2WebRTC()
    adapter.state = "CONNECTED"
    adapter.connection = SimpleNamespace(
        disconnect=mock_disconnect,
    )

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(adapter.disconnect())

    assert adapter.state == "ERROR"
    assert adapter.connection is not None


def test_disconnect_timeout_enforced(monkeypatch):
    from types import SimpleNamespace

    calls = []
    original_wait_for = asyncio.wait_for

    async def mock_wait_for(awaitable, timeout):
        calls.append(timeout)
        if hasattr(awaitable, "close"):
            awaitable.close()
        raise asyncio.TimeoutError("Simulated deadline exceeded")

    async def mock_disconnect():
        raise AssertionError("Should not execute")

    adapter = gw.Go2WebRTC()
    adapter.state = "CONNECTED"
    adapter.connection = SimpleNamespace(
        disconnect=mock_disconnect,
    )

    monkeypatch.setattr(gw.asyncio, "wait_for", mock_wait_for)

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(adapter.disconnect())

    assert calls == [5.0]
    assert adapter.state == "ERROR"
    assert adapter.connection is not None


def test_disconnect_cancellation():
    from types import SimpleNamespace

    started = asyncio.Event()

    async def mock_disconnect():
        started.set()
        await asyncio.sleep(10)

    adapter = gw.Go2WebRTC()
    adapter.state = "CONNECTED"
    adapter.connection = SimpleNamespace(
        disconnect=mock_disconnect,
    )

    async def scenario():
        task = asyncio.create_task(adapter.disconnect())

        try:
            await asyncio.wait_for(started.wait(), timeout=1.0)
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await task

            assert adapter.state == "ERROR"
            assert adapter.connection is not None

        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(
                    task,
                    return_exceptions=True,
                )

    asyncio.run(scenario())


def test_disconnect_idempotent():
    adapter = gw.Go2WebRTC()

    assert adapter.state == "DISCONNECTED"
    assert adapter.connection is None

    asyncio.run(adapter.disconnect())
    asyncio.run(adapter.disconnect())

    assert adapter.state == "DISCONNECTED"
    assert adapter.connection is None
