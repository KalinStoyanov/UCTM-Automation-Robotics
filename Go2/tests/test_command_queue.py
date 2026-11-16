import pytest

from remote_control import (
    CommandQueue,
    MAX_LINEAR_SPEED,
    MAX_ANGULAR_SPEED,
)


@pytest.mark.parametrize(
    "linear, angular, expected_linear, expected_angular",
    [
        (1.0, 0.0, MAX_LINEAR_SPEED, 0.0),
        (-1.0, 0.0, -MAX_LINEAR_SPEED, 0.0),
        (0.0, 2.0, 0.0, MAX_ANGULAR_SPEED),
        (0.0, -2.0, 0.0, -MAX_ANGULAR_SPEED),
    ],
)
def test_velocity_limits(
    linear, angular, expected_linear, expected_angular
):
    queue = CommandQueue()

    assert queue.submit(linear, angular) is not None

    command = queue.take()

    assert command is not None

    _, vx, wz = command

    assert vx == pytest.approx(expected_linear)
    assert wz == pytest.approx(expected_angular)


@pytest.mark.parametrize(
    "linear, angular",
    [
        (float("nan"), 0.0),
        (float("inf"), 0.0),
        (float("-inf"), 0.0),
        (0.0, float("nan")),
        (0.0, float("inf")),
        (0.0, float("-inf")),
    ],
)
def test_nonfinite_velocity_rejected(linear, angular):
    queue = CommandQueue()

    with pytest.raises(ValueError):
        queue.submit(linear, angular)

    assert queue.pending is None
    assert queue.sequence == 0


def test_stop_replaces_pending_move():
    queue = CommandQueue()

    queue.submit(0.1, 0.0)
    queue.submit(0.0, 0.0)

    assert queue.pending is not None
    assert queue.pending[1:] == (0.0, 0.0)


def test_pending_stop_blocks_move():
    queue = CommandQueue()

    queue.submit(0.0, 0.0)

    assert queue.submit(0.1, 0.0) is None
    assert queue.pending[1:] == (0.0, 0.0)


def test_stop_execution_blocks_move():
    queue = CommandQueue()

    queue.submit(0.0, 0.0)
    command = queue.take()

    assert command[1:] == (0.0, 0.0)
    assert queue.stop_in_progress

    assert queue.submit(0.1, 0.0) is None

    queue.finish_stop()

    assert not queue.stop_in_progress
    assert queue.submit(0.1, 0.0) is not None


def test_fault_blocks_movement():
    queue = CommandQueue()
    queue.set_fault()

    assert queue.fault
    assert queue.submit(0.1, 0.0) is None
    assert queue.pending is None


def test_stop_allowed_during_fault():
    queue = CommandQueue()
    queue.set_fault()

    assert queue.submit(0.0, 0.0) is not None

    command = queue.take()

    assert command[1:] == (0.0, 0.0)
    assert queue.stop_in_progress

    queue.finish_stop()

    assert queue.fault
    assert queue.recovery_ready()


def test_fault_recovery_requires_authorization():
    queue = CommandQueue()
    queue.set_fault()

    assert not queue.clear_fault()
    assert queue.fault

    assert queue.authorize_recovery()
    assert queue.clear_fault()

    assert not queue.fault
    assert not queue.recovery_authorized

    assert queue.submit(0.1, 0.0) is not None


def test_recovery_blocked_while_stop_in_progress():
    queue = CommandQueue()
    queue.set_fault()

    assert queue.submit(0.0, 0.0) is not None
    command = queue.take()

    assert command[1:] == (0.0, 0.0)
    assert queue.stop_in_progress

    assert not queue.recovery_ready()
    assert not queue.authorize_recovery()
    assert not queue.clear_fault()
    assert queue.fault
    assert queue.submit(0.1, 0.0) is None

    queue.finish_stop()

    assert queue.recovery_ready()
    assert queue.authorize_recovery()
    assert queue.clear_fault()
    assert not queue.fault


def test_recovery_blocked_while_stop_in_progress():
    queue = CommandQueue()
    queue.set_fault()

    assert queue.submit(0.0, 0.0) is not None
    command = queue.take()

    assert command[1:] == (0.0, 0.0)
    assert queue.stop_in_progress

    assert not queue.recovery_ready()
    assert not queue.authorize_recovery()
    assert not queue.clear_fault()
    assert queue.fault
    assert queue.submit(0.1, 0.0) is None

    queue.finish_stop()

    assert queue.recovery_ready()
    assert queue.authorize_recovery()
    assert queue.clear_fault()
    assert not queue.fault


def test_recovery_blocked_while_stop_in_progress():
    queue = CommandQueue()
    queue.set_fault()

    assert queue.submit(0.0, 0.0) is not None
    command = queue.take()

    assert command[1:] == (0.0, 0.0)
    assert queue.stop_in_progress

    assert not queue.recovery_ready()
    assert not queue.authorize_recovery()
    assert not queue.clear_fault()
    assert queue.fault
    assert queue.submit(0.1, 0.0) is None

    queue.finish_stop()

    assert queue.recovery_ready()
    assert queue.authorize_recovery()
    assert queue.clear_fault()
    assert not queue.fault
