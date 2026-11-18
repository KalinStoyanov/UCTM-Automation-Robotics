import pytest
from types import SimpleNamespace

from experiments.ddm2_ai_control import AIController


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


def make_controller(commands, executor=None):
    recorded = []

    if executor is None:
        executor = lambda vx, wz: recorded.append((vx, wz))

    pipeline = FakePipeline(commands)
    controller = AIController(
        pipeline=pipeline,
        executor=executor,
    )
    return controller, pipeline, recorded


def test_start_locked():
    controller, pipeline, recorded = make_controller([
        command("TURN_LEFT", 0.1)
    ])
    assert controller.step_offline({}, 1.0) == "STOP"
    assert pipeline.calls == 0
    assert recorded == [(0.0, 0.0)]


def test_authorized_sequence():
    controller, pipeline, recorded = make_controller([
        command("TURN_LEFT", 0.1),
        command("TURN_RIGHT", -0.1),
    ])
    assert controller.authorize_offline()
    assert controller.step_offline({}, 1.0) == "EXECUTED"
    assert controller.step_offline({}, 2.0) == "EXECUTED"
    assert recorded == [(0.0, 0.1), (0.0, -0.1)]


def test_manual_stop_blocks_ai():
    controller, pipeline, recorded = make_controller([
        command("TURN_LEFT", 0.1),
        command("TURN_RIGHT", -0.1),
    ])
    assert controller.authorize_offline()
    assert controller.step_offline({}, 1.0) == "EXECUTED"

    controller.manual_stop()

    assert controller.step_offline({}, 2.0) == "STOP"
    assert pipeline.calls == 1
    assert recorded[-1] == (0.0, 0.0)
    assert controller.gateway.stop_latched


def test_ai_stop_blocks_following_commands():
    controller, pipeline, recorded = make_controller([
        command("STOP"),
        command("TURN_LEFT", 0.1),
    ])
    assert controller.authorize_offline()
    assert controller.step_offline({}, 1.0) == "STOP"
    assert controller.step_offline({}, 2.0) == "STOP"
    assert pipeline.calls == 1
    assert controller.core.arbiter.stop_latched


def test_invalid_direction_stops():
    controller, pipeline, recorded = make_controller([
        command("TURN_LEFT", -0.1)
    ])
    assert controller.authorize_offline()
    assert controller.step_offline({}, 1.0) == "STOP"
    assert recorded[-1] == (0.0, 0.0)


def test_executor_failure_must_latch_stop():
    def broken_executor(vx, wz):
        raise RuntimeError("Injected executor failure")

    controller, pipeline, recorded = make_controller(
        [command("TURN_LEFT", 0.1)],
        executor=broken_executor,
    )
    assert controller.authorize_offline()

    try:
        controller.step_offline({}, 1.0)
    except RuntimeError:
        pass

    assert controller.gateway.stop_latched, (
        "Executor failure must block further AI commands"
    )
    assert controller.core.arbiter.stop_latched, (
        "Executor failure must latch controller STOP"
    )


def test_executor_failure_requires_explicit_reset():
    calls = []
    fail_once = [True]

    def executor(vx, wz):
        calls.append((vx, wz))
        if fail_once[0]:
            fail_once[0] = False
            raise RuntimeError("Injected failure")

    controller, pipeline, recorded = make_controller(
        [
            command("TURN_LEFT", 0.1),
            command("TURN_RIGHT", -0.1),
        ],
        executor=executor,
    )

    assert controller.authorize_offline()
    assert controller.step_offline({}, 1.0) == "STOP"

    assert controller.gateway.stop_latched
    assert controller.core.arbiter.stop_latched

    assert not controller.authorize_offline()
    assert controller.step_offline({}, 2.0) == "STOP"
    assert pipeline.calls == 1

    controller.core.reset_stop()

    assert not controller.core.arbiter.motion_authorized
    assert controller.authorize_offline()

    assert controller.step_offline({}, 3.0) == "EXECUTED"
    assert calls[-1] == (0.0, -0.1)


def test_executor_failure_blocks_remaining_ai_commands():
    def executor(vx, wz):
        raise RuntimeError("Execution failure")

    controller, pipeline, recorded = make_controller(
        [
            command("TURN_LEFT", 0.1),
            command("TURN_LEFT", 0.1),
        ],
        executor=executor,
    )

    assert controller.authorize_offline()
    assert controller.step_offline({}, 1.0) == "STOP"

    for now in (2.0, 3.0, 4.0):
        assert controller.step_offline({}, now) == "STOP"

    assert pipeline.calls == 1
    assert controller.gateway.stop_latched
    assert controller.core.arbiter.stop_latched
