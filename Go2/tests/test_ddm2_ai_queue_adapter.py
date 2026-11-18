import pytest
from types import SimpleNamespace

from experiments.ddm2_manual_control import CommandQueue
from experiments.ddm2_ai_gateway import AIExecutionGateway
from experiments.ddm2_ai_queue_adapter import QueueExecutor


def ai_command(action="TURN_LEFT", angular=0.1):
    return SimpleNamespace(
        source="AI",
        action=action,
        linear=0.0,
        angular=angular,
    )


def setup():
    queue = CommandQueue()
    executor = QueueExecutor(queue)
    gateway = AIExecutionGateway(executor)
    return queue, executor, gateway


def test_same_queue_instance():
    queue, executor, gateway = setup()
    assert executor.queue is queue
    assert gateway.executor is executor


def test_ai_command_enters_queue():
    queue, _, gateway = setup()
    gateway.authorize()

    assert gateway.execute(ai_command()) == "EXECUTED"

    item = queue.take()
    assert item is not None
    assert item[1:] == (0.0, 0.1)


def test_stop_replaces_pending_motion():
    queue, _, gateway = setup()
    gateway.authorize()

    assert gateway.execute(ai_command()) == "EXECUTED"
    assert gateway.stop() == "STOP"

    item = queue.take()
    assert item[1:] == (0.0, 0.0)

    assert gateway.execute(ai_command()) == "BLOCKED"
    queue.finish_stop()


def test_queue_fault_blocks_ai():
    queue, _, gateway = setup()
    gateway.authorize()
    queue.set_fault()

    with pytest.raises(RuntimeError):
        gateway.execute(ai_command())

    assert gateway.stop_latched
    assert queue.fault


def test_stop_in_progress_blocks_ai():
    queue, _, gateway = setup()
    gateway.authorize()

    assert gateway.stop() == "STOP"
    item = queue.take()

    assert item[1:] == (0.0, 0.0)
    assert queue.stop_in_progress

    gateway.authorize()

    with pytest.raises(RuntimeError):
        gateway.execute(ai_command())

    assert gateway.stop_latched
    queue.finish_stop()


def test_explicit_recovery_required():
    queue, _, gateway = setup()
    gateway.authorize()
    queue.set_fault()

    with pytest.raises(RuntimeError):
        gateway.execute(ai_command())

    assert gateway.stop_latched
    assert queue.fault

    assert queue.authorize_recovery()
    assert queue.clear_fault()
    assert not queue.fault

    # Clearing the queue fault does not unlock the gateway.
    assert gateway.execute(ai_command()) == "BLOCKED"

    gateway.authorize()
    assert gateway.execute(ai_command()) == "EXECUTED"
