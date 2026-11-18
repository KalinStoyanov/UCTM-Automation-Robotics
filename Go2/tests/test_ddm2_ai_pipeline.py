from types import SimpleNamespace

from experiments.ddm2_ai_pipeline import OfflineAIPipeline


class FakeRuntime:
    def __init__(self, result):
        self.result = result

    def step(self, frame, now):
        return self.result, {"deadline_miss": False}


def result(action, angular=0.0, confidence=0.95):
    return SimpleNamespace(
        action=action,
        linear_m_s=0.0,
        angular_rad_s=angular,
        confidence=confidence,
    )


def test_ai_left():
    pipeline = OfflineAIPipeline(
        runtime=FakeRuntime(result("TURN_LEFT", -0.15))
    )
    command, timing = pipeline.step({}, 1.0)
    assert command.action == "TURN_LEFT"
    assert command.angular == 0.15
    assert timing["deadline_miss"] is False


def test_ai_right():
    pipeline = OfflineAIPipeline(
        runtime=FakeRuntime(result("TURN_RIGHT", 0.15))
    )
    command, _ = pipeline.step({}, 1.0)
    assert command.action == "TURN_RIGHT"
    assert command.angular == -0.15


def test_ai_stop():
    pipeline = OfflineAIPipeline(
        runtime=FakeRuntime(result("STOP"))
    )
    command, _ = pipeline.step(None, 1.0)
    assert command.action == "STOP"
    assert command.linear == 0.0
    assert command.angular == 0.0


def test_ai_invalid_result():
    pipeline = OfflineAIPipeline(
        runtime=FakeRuntime(None)
    )
    command, _ = pipeline.step({}, 1.0)
    assert command.action == "STOP"


def test_real_m19_offline():
    import time

    pipeline = OfflineAIPipeline()
    now = time.monotonic()

    frame = {
        "timestamp": now,
        "detections": [{
            "object_id": 1,
            "center_x": 0.2,
            "confidence": 0.95,
        }],
    }

    command, timing = pipeline.step(frame, now)

    assert command.action in {
        "STOP", "TURN_LEFT", "TURN_RIGHT"
    }
    assert abs(command.angular) <= 0.20
    assert timing["deadline_miss"] is False
