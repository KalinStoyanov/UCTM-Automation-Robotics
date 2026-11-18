from types import SimpleNamespace

from experiments.ddm2_ai_controller_core import AIControllerCore


def command(action, angular=0.0):
    return SimpleNamespace(
        action=action,
        linear=0.0,
        angular=angular,
    )


class FakePipeline:
    def __init__(self, result, timing=None, error=False):
        self.result = result
        self.timing = (
            timing if timing is not None
            else {"deadline_miss": False}
        )
        self.error = error
        self.calls = 0

    def step(self, frame, now):
        self.calls += 1
        if self.error:
            raise RuntimeError("Injected AI failure")
        return self.result, self.timing


def enabled(pipeline):
    controller = AIControllerCore(pipeline=pipeline)
    controller.authorize_motion(True)
    assert controller.enable_ai()
    return controller


def test_ai_disabled_by_default():
    pipeline = FakePipeline(command("TURN_LEFT", 0.1))
    controller = AIControllerCore(pipeline=pipeline)
    assert controller.step({}, 1.0).action == "STOP"
    assert pipeline.calls == 0


def test_ai_left():
    controller = enabled(
        FakePipeline(command("TURN_LEFT", 0.1))
    )
    result = controller.step({}, 1.0)
    assert result.source == "AI"
    assert result.angular == 0.1


def test_ai_right():
    controller = enabled(
        FakePipeline(command("TURN_RIGHT", -0.1))
    )
    result = controller.step({}, 1.0)
    assert result.source == "AI"
    assert result.angular == -0.1


def test_manual_stop_priority():
    controller = enabled(
        FakePipeline(command("TURN_LEFT", 0.1))
    )
    controller.manual_stop()
    assert controller.step({}, 1.0).action == "STOP"
    assert controller.arbiter.stop_latched


def test_manual_override():
    controller = enabled(
        FakePipeline(command("TURN_LEFT", 0.1))
    )
    result = controller.manual_command(0.1, 0.0)
    assert result.source == "MANUAL"
    assert controller.step({}, 1.0).action == "STOP"


def test_ai_stop_latches():
    controller = enabled(
        FakePipeline(command("STOP"))
    )
    assert controller.step(None, 1.0).action == "STOP"
    assert controller.arbiter.stop_latched


def test_deadline_miss_stops():
    controller = enabled(
        FakePipeline(
            command("TURN_LEFT", 0.1),
            timing={"deadline_miss": True},
        )
    )
    assert controller.step({}, 1.0).action == "STOP"
    assert controller.arbiter.stop_latched


def test_runtime_exception_stops():
    controller = enabled(
        FakePipeline(None, error=True)
    )
    assert controller.step({}, 1.0).action == "STOP"
    assert controller.arbiter.stop_latched


def test_reauthorization_required():
    controller = enabled(
        FakePipeline(command("TURN_LEFT", 0.1))
    )
    controller.manual_stop()
    controller.reset_stop()

    assert not controller.enable_ai()

    controller.authorize_motion(True)
    assert controller.enable_ai()


def test_revoked_motion_stops():
    controller = enabled(
        FakePipeline(command("TURN_LEFT", 0.1))
    )
    controller.authorize_motion(False)
    assert controller.step({}, 1.0).action == "STOP"
