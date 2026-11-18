from types import SimpleNamespace

from experiments.ddm2_ai_arbitration import CommandArbiter


def cmd(action, angular=0.0, linear=0.0):
    return SimpleNamespace(
        action=action, angular=angular, linear=linear
    )


def enabled():
    arb = CommandArbiter()
    arb.set_motion_authorized(True)
    assert arb.enable_ai()
    return arb


def test_default_ai_disabled():
    arb = CommandArbiter()
    assert not arb.enable_ai()
    assert arb.ai_command(cmd("TURN_LEFT", 0.1)).action == "STOP"


def test_ai_left():
    result = enabled().ai_command(cmd("TURN_LEFT", 0.1))
    assert (result.source, result.angular) == ("AI", 0.1)


def test_ai_right():
    result = enabled().ai_command(cmd("TURN_RIGHT", -0.1))
    assert (result.source, result.angular) == ("AI", -0.1)


def test_manual_override():
    arb = enabled()
    result = arb.manual_command(0.1, 0.0)
    assert result.source == "MANUAL"
    assert arb.mode == "MANUAL"


def test_manual_stop_priority():
    arb = enabled()
    arb.manual_stop()
    assert arb.ai_command(cmd("TURN_LEFT", 0.1)).action == "STOP"
    assert not arb.enable_ai()


def test_explicit_reset_required():
    arb = enabled()
    arb.manual_stop()
    arb.reset_stop()
    assert not arb.enable_ai()
    arb.set_motion_authorized(True)
    assert arb.enable_ai()


def test_invalid_ai_latches_stop():
    arb = enabled()
    assert arb.ai_command(cmd("FORWARD", 0.0)).action == "STOP"
    assert arb.stop_latched


def test_invalid_ai_direction():
    arb = enabled()
    assert arb.ai_command(cmd("TURN_LEFT", -0.1)).action == "STOP"
    assert arb.stop_latched


def test_ai_stop_latches():
    arb = enabled()
    assert arb.ai_command(cmd("STOP")).action == "STOP"
    assert arb.stop_latched


def test_authorization_revoked():
    arb = enabled()
    arb.set_motion_authorized(False)
    assert arb.ai_command(cmd("TURN_LEFT", 0.1)).action == "STOP"
