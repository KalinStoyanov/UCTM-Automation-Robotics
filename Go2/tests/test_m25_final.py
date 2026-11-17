import math

import pytest

from core.communication.go2_webrtc import LIVE_ENABLED
from core.safety.lidar_adapter import LidarGeometry, points_to_clearance
from core.safety.obstacle import ObstacleSafetyFilter, Clearance


@pytest.fixture
def geometry():
    # Synthetic test geometry; not calibrated Go2 dimensions.
    return LidarGeometry(
        min_z=-0.2,
        max_z=0.5,
        half_width=0.2,
        half_length=0.3,
        max_range=5.0,
    )


def scan(points, geometry):
    return points_to_clearance(
        points,
        geometry,
        frame_verified=True,
        scan_complete=True,
    )


def test_live_disabled():
    assert LIVE_ENABLED is False


@pytest.mark.parametrize("points", [
    [],
    [(math.nan, 0, 0)],
    [(math.inf, 0, 0)],
    [(1, 0)],
    [(10, 0, 0)],
    [(1, 0, 10)],
])
def test_invalid_scan_blocks(points, geometry):
    assert scan(points, geometry) is None


def test_unverified_frame_blocks(geometry):
    assert points_to_clearance(
        [(2, 0, 0)],
        geometry,
        scan_complete=True,
    ) is None


def test_incomplete_scan_blocks(geometry):
    assert points_to_clearance(
        [(2, 0, 0)],
        geometry,
        frame_verified=True,
    ) is None


@pytest.mark.parametrize("point,direction", [
    ((0.6, 0, 0), "forward"),
    ((-0.6, 0, 0), "backward"),
    ((0, 0.4, 0), "left"),
    ((0, -0.4, 0), "right"),
])
def test_obstacle_distance(point, direction, geometry):
    c = scan([point], geometry)
    assert c is not None
    assert 0 <= getattr(c, direction) <= 0.5


def test_turn_obstacle(geometry):
    c = scan([(0, 0.4, 0)], geometry)
    safety = ObstacleSafetyFilter()
    assert safety.observe(c)
    assert not safety.safe(0, 0, 0.2)


def test_sensor_timeout():
    clock = [0.0]
    safety = ObstacleSafetyFilter(clock=lambda: clock[0])
    assert safety.observe(Clearance(2, 2, 2, 2, 2))
    assert safety.safe(0.1, 0, 0)
    clock[0] = 0.3
    assert not safety.safe(0.1, 0, 0)


def test_sensor_failure():
    safety = ObstacleSafetyFilter()
    assert safety.observe(Clearance(2, 2, 2, 2, 2))
    assert not safety.observe(None)
    assert not safety.safe(0.1, 0, 0)


def test_zero_clearance_blocks():
    safety = ObstacleSafetyFilter()
    assert safety.observe(Clearance(0, 0, 0, 0, 0))
    for velocity in (
        (0.1, 0, 0),
        (-0.1, 0, 0),
        (0, 0.1, 0),
        (0, -0.1, 0),
        (0, 0, 0.1),
    ):
        assert not safety.safe(*velocity)


def test_exact_stop_threshold_blocks():
    safety = ObstacleSafetyFilter(stop_distance=0.5)
    assert safety.observe(Clearance(0.5, 2, 2, 2, 2))
    assert not safety.safe(0.1, 0, 0)


def test_invalid_velocity_blocks():
    safety = ObstacleSafetyFilter()
    assert safety.observe(Clearance(2, 2, 2, 2, 2))
    assert not safety.safe(math.nan, 0, 0)
    assert not safety.safe(0, 0, math.inf)


def test_no_observation_blocks():
    safety = ObstacleSafetyFilter()
    assert not safety.safe(0.1, 0, 0)
