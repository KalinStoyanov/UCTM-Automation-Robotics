from types import SimpleNamespace
import math
import pytest

from experiments.ddm2_ai_adapter import AICommandAdapter


def proposal(action, angular=0.0, confidence=0.95, linear=0.0):
    return SimpleNamespace(
        action=action,
        linear_m_s=linear,
        angular_rad_s=angular,
        confidence=confidence,
    )


def test_left_turn():
    command = AICommandAdapter().convert(proposal("TURN_LEFT", -0.15))
    assert command.angular == pytest.approx(0.15)


def test_right_turn():
    command = AICommandAdapter().convert(proposal("TURN_RIGHT", 0.15))
    assert command.angular == pytest.approx(-0.15)


def test_stop():
    command = AICommandAdapter().convert(proposal("STOP"))
    assert command.linear == command.angular == 0.0


@pytest.mark.parametrize("result", [
    None,
    object(),
    proposal("FORWARD"),
    proposal("TURN_LEFT", 0.15),
    proposal("TURN_RIGHT", -0.15),
    proposal("TURN_LEFT", 0.0),
    proposal("TURN_LEFT", -0.15, confidence=0.2),
    proposal("TURN_LEFT", math.nan),
    proposal("TURN_LEFT", math.inf),
    proposal("TURN_LEFT", -0.15, linear=0.1),
])
def test_invalid_or_unsafe_stops(result):
    command = AICommandAdapter().convert(result)
    assert command.action == "STOP"
    assert command.linear == 0.0
    assert command.angular == 0.0


def test_angular_limit():
    command = AICommandAdapter().convert(
        proposal("TURN_LEFT", -0.30)
    )
    assert command.angular == pytest.approx(0.20)
