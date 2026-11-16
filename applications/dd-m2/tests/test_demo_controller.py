import math

from src.demo.controller import DemoController
from src.demo.commands import map_gesture


def person(pid, raised=False, horizontal=False):
    return {
        "id": pid,
        "bbox": [300, 100, 500, 350],
        "arm_raised": raised,
        "left_arm": "HORIZONTAL" if horizontal else "LOWERED",
        "right_arm": "LOWERED",
    }


def test_idle():
    c = DemoController()
    assert c.update([], 800, 600)["state"] == "IDLE"


def test_follow_selection():
    c = DemoController()
    r = c.update([person(5, raised=True)], 800, 600)
    assert r["state"] == "FOLLOW"
    assert r["target_id"] == 5


def test_ambiguous_selection():
    c = DemoController()
    r = c.update([
        person(5, raised=True),
        person(6, raised=True),
    ], 800, 600)
    assert r["state"] == "IDLE"


def test_target_lost():
    c = DemoController()
    c.update([person(5, raised=True)], 800, 600)
    r = c.update([person(6, raised=True)], 800, 600)
    assert r["state"] == "STOP"
    assert r["motion"]["linear_m_s"] == 0


def test_arm_lowered():
    c = DemoController()
    c.update([person(5, raised=True)], 800, 600)
    r = c.update([person(5)], 800, 600)
    assert r["state"] == "STOP"


def test_rotate_search():
    c = DemoController()
    c.update([person(5, raised=True)], 800, 600)
    r = c.update([person(5, horizontal=True)], 800, 600)
    assert r["state"] == "ROTATE_SEARCH"
    assert r["motion"]["linear_m_s"] == 0


def test_search_finds_new_person():
    c = DemoController()
    c.update([person(5, raised=True)], 800, 600)
    c.update([person(5, horizontal=True)], 800, 600)
    r = c.update([person(6, raised=True)], 800, 600)
    assert r["state"] == "FOLLOW"
    assert r["target_id"] == 6


def test_search_full_rotation():
    c = DemoController()
    c.update([person(5, raised=True)], 800, 600)
    c.update([person(5, horizontal=True)], 800, 600)

    for _ in range(100):
        result = c.update([], 800, 600, dt=0.2)
        if result["state"] == "STOP":
            break

    assert c.state == "STOP"
    assert c.search_angle >= 2 * math.pi - 1e-6


def test_stop_priority():
    c = DemoController()
    c.update([person(5, raised=True)], 800, 600)
    r = c.update([person(5, raised=True)], 800, 600, gesture="STOP")
    assert r["state"] == "STOP"
    assert r["motion"]["linear_m_s"] == 0


def test_gesture_mapping():
    assert map_gesture("Thumb_Up") == "COME_TO_ME"
    assert map_gesture("Thumb_Down") == "MOVE_AWAY"
    assert map_gesture("Open_Palm") == "STOP"
