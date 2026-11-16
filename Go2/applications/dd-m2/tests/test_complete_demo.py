import math

from src.demo.complete_controller import CompleteDemoController
from src.demo.discrete_commands import DiscreteCommands


def person(pid, raised=False, horizontal=False):
    return {
        "id": pid,
        "bbox": [300, 100, 500, 350],
        "arm_raised": raised,
        "arm_above_head": raised,
        "left_arm": (
            "HORIZONTAL" if horizontal else "LOWERED"
        ),
        "right_arm": "LOWERED",
    }


def test_idle():
    c = CompleteDemoController()
    assert c.update([], 800, 600)["state"] == "IDLE"


def test_follow():
    c = CompleteDemoController()
    r = c.update(
        [person(5, raised=True)], 800, 600
    )
    assert r["state"] == "FOLLOW"
    assert r["target_id"] == 5


def test_ambiguous():
    c = CompleteDemoController()
    r = c.update(
        [
            person(5, raised=True),
            person(6, raised=True),
        ],
        800,
        600,
    )
    assert r["state"] == "IDLE"


def test_target_lost():
    c = CompleteDemoController()
    c.update([person(5, raised=True)], 800, 600)
    r = c.update([person(6, raised=True)], 800, 600)
    assert r["state"] == "STOP"


def test_arm_lowered():
    c = CompleteDemoController()
    c.update([person(5, raised=True)], 800, 600)
    r = c.update([person(5)], 800, 600)
    assert r["state"] == "STOP"


def test_rotate_search():
    c = CompleteDemoController()
    c.update([person(5, raised=True)], 800, 600)
    r = c.update(
        [person(5, horizontal=True)], 800, 600
    )
    assert r["state"] == "ROTATE_SEARCH"
    assert r["motion"]["linear_m_s"] == 0


def test_search_new_target():
    c = CompleteDemoController()
    c.update([person(5, raised=True)], 800, 600)
    c.update(
        [person(5, horizontal=True)], 800, 600
    )
    r = c.update(
        [person(6, raised=True)], 800, 600
    )
    assert r["state"] == "FOLLOW"
    assert r["target_id"] == 6


def test_search_one_rotation():
    c = CompleteDemoController()
    c.update([person(5, raised=True)], 800, 600)
    c.update(
        [person(5, horizontal=True)], 800, 600
    )

    for _ in range(100):
        r = c.update([], 800, 600, dt=0.2)
        if r["state"] == "STOP":
            break

    assert c.state == "STOP"
    assert c.search_angle >= 2 * math.pi - 1e-6


def test_stop_priority():
    c = CompleteDemoController()
    c.update([person(5, raised=True)], 800, 600)
    r = c.update(
        [person(5, raised=True)],
        800,
        600,
        command="STOP",
    )
    assert r["state"] == "STOP"
    assert r["motion"]["linear_m_s"] == 0


def test_stop_latched():
    c = CompleteDemoController()
    c.stop()
    r = c.update(
        [person(5, raised=True)], 800, 600
    )
    assert r["state"] == "STOP"


def test_come_to_me():
    c = CompleteDemoController()
    r = c.update(
        [person(5, raised=True)],
        800,
        600,
        command="COME_TO_ME",
    )
    assert r["motion"]["linear_m_s"] > 0


def test_move_away():
    c = CompleteDemoController()
    r = c.update(
        [person(5, raised=True)],
        800,
        600,
        command="MOVE_AWAY",
    )
    assert r["motion"]["linear_m_s"] < 0


def test_sit():
    c = CompleteDemoController()
    r = c.update(
        [], 800, 600, command="SIT"
    )
    assert r["posture"] == "SITTING"
    assert r["motion"]["linear_m_s"] == 0


def test_lie_down():
    c = CompleteDemoController()
    r = c.update(
        [], 800, 600, command="LIE_DOWN"
    )
    assert r["posture"] == "LYING"


def test_stand_up():
    c = CompleteDemoController()
    c.update([], 800, 600, command="SIT")
    r = c.update(
        [], 800, 600, command="STAND_UP"
    )
    assert r["posture"] == "STANDING"


def test_turn_left():
    c = CompleteDemoController()
    r = c.update(
        [], 800, 600,
        command="TURN_LEFT_90",
    )
    assert r["motion"]["angular_rad_s"] > 0


def test_turn_right():
    c = CompleteDemoController()
    r = c.update(
        [], 800, 600,
        command="TURN_RIGHT_90",
    )
    assert r["motion"]["angular_rad_s"] < 0


def test_turn_exact_angle():
    d = DiscreteCommands()
    assert d.command("TURN_LEFT_90")

    angle = 0.0
    for _ in range(200):
        angle += d.step(0.1) * 0.1
        if not d.turning:
            break

    assert math.isclose(
        angle, math.pi / 2, abs_tol=1e-9
    )


def test_turn_blocked_while_sitting():
    d = DiscreteCommands()
    d.command("SIT")
    assert not d.command("TURN_LEFT_90")


def test_stop_cancels_turn():
    c = CompleteDemoController()
    c.update(
        [], 800, 600,
        command="TURN_LEFT_90",
    )
    r = c.update(
        [], 800, 600,
        command="STOP",
    )
    assert r["state"] == "STOP"
    assert not c.discrete.turning
