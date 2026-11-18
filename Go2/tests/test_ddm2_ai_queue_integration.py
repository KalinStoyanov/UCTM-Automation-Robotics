from types import SimpleNamespace

from experiments.ddm2_manual_control import CommandQueue
from experiments.ddm2_ai_control import AIController
from experiments.ddm2_ai_queue_adapter import QueueExecutor


def command(action, angular=0.0):
    return SimpleNamespace(
        action=action,
        linear=0.0,
        angular=angular,
    )


class FakePipeline:
    def __init__(self, commands):
        self.commands = iter(commands)
        self.calls = 0

    def step(self, frame, now):
        self.calls += 1
        return next(self.commands), {"deadline_miss": False}


def make_system(commands):
    queue = CommandQueue()
    executor = QueueExecutor(queue)
    pipeline = FakePipeline(commands)

    controller = AIController(
        pipeline=pipeline,
        executor=executor,
    )

    return controller, pipeline, queue


def test_ai_command_reaches_queue():
    controller, pipeline, queue = make_system([
        command("TURN_LEFT", 0.1)
    ])

    assert controller.authorize_offline()
    assert controller.step_offline({}, 1.0) == "EXECUTED"
    assert queue.take()[1:] == (0.0, 0.1)


def test_latest_ai_command_replaces_pending():
    controller, pipeline, queue = make_system([
        command("TURN_LEFT", 0.1),
        command("TURN_RIGHT", -0.1),
    ])

    assert controller.authorize_offline()
    assert controller.step_offline({}, 1.0) == "EXECUTED"
    assert controller.step_offline({}, 2.0) == "EXECUTED"

    assert queue.take()[1:] == (0.0, -0.1)


def test_manual_stop_replaces_ai_command():
    controller, pipeline, queue = make_system([
        command("TURN_LEFT", 0.1),
        command("TURN_RIGHT", -0.1),
    ])

    assert controller.authorize_offline()
    assert controller.step_offline({}, 1.0) == "EXECUTED"

    assert controller.manual_stop() == "STOP"
    assert queue.take()[1:] == (0.0, 0.0)
    assert controller.step_offline({}, 2.0) == "STOP"
    assert pipeline.calls == 1


def test_queue_fault_latches_controller():
    controller, pipeline, queue = make_system([
        command("TURN_LEFT", 0.1)
    ])

    assert controller.authorize_offline()
    queue.set_fault()

    assert controller.step_offline({}, 1.0) == "STOP"
    assert controller.gateway.stop_latched
    assert controller.core.arbiter.stop_latched


def test_stop_requires_explicit_recovery():
    controller, pipeline, queue = make_system([
        command("TURN_LEFT", 0.1),
        command("TURN_RIGHT", -0.1),
    ])

    assert controller.authorize_offline()
    assert controller.manual_stop() == "STOP"

    assert not controller.authorize_offline()

    pending = queue.take()
    assert pending[1:] == (0.0, 0.0)
    queue.finish_stop()

    controller.core.reset_stop()
    assert controller.authorize_offline()
    assert controller.step_offline({}, 2.0) == "EXECUTED"
