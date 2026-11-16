import pytest

import go2_webrtc as gw
import remote_control as rc


def test_live_keyboard_dispatch_is_blocked(monkeypatch):
    monkeypatch.setattr(gw, "LIVE_ENABLED", True)

    with pytest.raises(
        RuntimeError,
        match="LIVE keyboard dispatch is not enabled",
    ):
        rc.schedule_command(0.1, 0.0)


def test_simulation_mode_accepts_command(monkeypatch):
    monkeypatch.setattr(gw, "LIVE_ENABLED", False)

    queue = rc.CommandQueue()
    monkeypatch.setattr(rc, "command_queue", queue)

    result = rc.schedule_command(0.1, 0.0)

    assert result is not False
    assert queue.pending is not None
