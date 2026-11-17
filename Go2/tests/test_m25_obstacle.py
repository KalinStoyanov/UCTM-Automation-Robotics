import pytest
from core.safety.obstacle import Clearance, ObstacleSafetyFilter


def test_no_sensor_data():
    s = ObstacleSafetyFilter()
    assert s.command(0.2, 0, 0) == (0, 0, 0)


@pytest.mark.parametrize("direction,velocity", [
    ("forward", (0.2, 0, 0)),
    ("backward", (-0.2, 0, 0)),
    ("left", (0, 0.2, 0)),
    ("right", (0, -0.2, 0)),
    ("turn", (0, 0, 0.3)),
])
def test_directional_obstacle(direction, velocity):
    s = ObstacleSafetyFilter()
    distances = dict.fromkeys(
        ("forward", "backward", "left", "right", "turn"), 2.0
    )
    distances[direction] = 0.3
    s.observe(Clearance(**distances))
    assert s.command(*velocity) == (0, 0, 0)
    assert s.state == "STOPPED_OBSTACLE"


def test_clear_path():
    s = ObstacleSafetyFilter()
    s.observe(Clearance(2, 2, 2, 2, 2))
    assert s.command(0.2, 0, 0) == (0.2, 0, 0)


def test_obstacle_latched_until_new_command():
    s = ObstacleSafetyFilter()
    s.observe(Clearance(0.2, 2, 2, 2, 2))
    assert s.command(0.2, 0, 0) == (0, 0, 0)

    s.observe(Clearance(2, 2, 2, 2, 2))
    assert s.state == "STOPPED_OBSTACLE"

    assert s.command(0.2, 0, 0) == (0.2, 0, 0)


def test_invalid_sensor_data():
    s = ObstacleSafetyFilter()
    s.observe(Clearance(float("nan"), 2, 2, 2, 2))
    assert s.command(0.2, 0, 0) == (0, 0, 0)
    assert s.state == "SENSOR_FAULT"
