from types import SimpleNamespace

from experiments.ddm2_ai_gateway import AIExecutionGateway


def result(action, angular=0.0, source="AI"):
    return SimpleNamespace(
        action=action,
        source=source,
        linear=0.0,
        angular=angular,
    )


def gateway():
    commands = []
    return AIExecutionGateway(
        lambda vx, wz: commands.append((vx, wz))
    ), commands


def test_default_locked():
    gate, commands = gateway()
    assert gate.execute(result("TURN_LEFT", 0.1)) == "BLOCKED"
    assert commands == []


def test_ai_left():
    gate, commands = gateway()
    gate.authorize()
    assert gate.execute(result("TURN_LEFT", 0.1)) == "EXECUTED"
    assert commands == [(0.0, 0.1)]


def test_ai_right():
    gate, commands = gateway()
    gate.authorize()
    assert gate.execute(result("TURN_RIGHT", -0.1)) == "EXECUTED"
    assert commands == [(0.0, -0.1)]


def test_manual_stop():
    gate, commands = gateway()
    gate.authorize()
    gate.execute(result("TURN_LEFT", 0.1))
    gate.stop()

    assert gate.execute(result("TURN_LEFT", 0.1)) == "BLOCKED"
    assert commands[-1] == (0.0, 0.0)


def test_invalid_command():
    gate, commands = gateway()
    gate.authorize()

    assert gate.execute(result("FORWARD", 0.1)) == "STOP"
    assert gate.stop_latched
    assert commands == [(0.0, 0.0)]


def test_reauthorization():
    gate, commands = gateway()
    gate.authorize()
    gate.stop()
    gate.authorize()

    assert gate.execute(result("TURN_LEFT", 0.1)) == "EXECUTED"


def test_manual_source_rejected():
    gate, commands = gateway()
    gate.authorize()

    assert gate.execute(
        result("TURN_LEFT", 0.1, source="MANUAL")
    ) == "STOP"

    assert commands == [(0.0, 0.0)]
