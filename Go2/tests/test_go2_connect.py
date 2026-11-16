import asyncio
from types import SimpleNamespace

import pytest
import go2_webrtc as gw


def mock_connection_factory(behavior, calls):
    class MockConnection:
        def __init__(self, method):
            calls.append("init")
            self.datachannel = SimpleNamespace(
                data_channel_opened=behavior != "closed",
                channel=SimpleNamespace(
                    readyState="closed" if behavior == "closed" else "open"
                ),
            )

        async def connect(self):
            calls.append("connect")
            if behavior == "error":
                raise ConnectionError("Simulated connection failure")
            if behavior == "timeout":
                raise asyncio.TimeoutError("Simulated timeout")
            if behavior == "cancel":
                raise asyncio.CancelledError()

        async def disconnect(self):
            calls.append("disconnect")

    return MockConnection


@pytest.mark.parametrize(
    "behavior,expected_error",
    [
        ("closed", RuntimeError),
        ("error", ConnectionError),
        ("timeout", asyncio.TimeoutError),
        ("cancel", asyncio.CancelledError),
    ],
)
def test_connect_failure(monkeypatch, behavior, expected_error):
    calls = []
    monkeypatch.setattr(gw, "LIVE_ENABLED", True)
    monkeypatch.setattr(
        gw,
        "UnitreeWebRTCConnection",
        mock_connection_factory(behavior, calls),
    )

    adapter = gw.Go2WebRTC()

    with pytest.raises(expected_error):
        asyncio.run(adapter.connect())

    assert adapter.state == "ERROR"
    assert adapter.connection is None
    assert calls == ["init", "connect", "disconnect"]


def test_connect_success(monkeypatch):
    calls = []
    monkeypatch.setattr(gw, "LIVE_ENABLED", True)
    monkeypatch.setattr(
        gw,
        "UnitreeWebRTCConnection",
        mock_connection_factory("success", calls),
    )

    adapter = gw.Go2WebRTC()
    result = asyncio.run(adapter.connect())

    assert result is True
    assert adapter.state == "CONNECTED"
    assert adapter.channel_ready() is True
    assert calls == ["init", "connect"]
