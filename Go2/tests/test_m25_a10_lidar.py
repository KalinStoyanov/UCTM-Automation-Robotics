import math

import pytest

from core.safety.lidar_adapter import (
    LidarGeometry,
    points_to_clearance,
)
from core.safety.obstacle import ObstacleSafetyFilter


@pytest.fixture
def geometry():
    # Synthetic dimensions, not physical Go2 measurements.
    return LidarGeometry(
        min_z=-0.2,
        max_z=0.5,
        half_width=0.2,
        half_length=0.3,
        max_range=5.0,
    )


def convert(points, geometry, **kwargs):
    return points_to_clearance(
        points,
        geometry,
        frame_verified=True,
        scan_complete=True,
        **kwargs,
    )


def test_unverified_frame_rejected(geometry):
    assert points_to_clearance(
        [(1.0, 0.0, 0.0)],
        geometry,
        scan_complete=True,
    ) is None


def test_incomplete_scan_rejected(geometry):
    assert points_to_clearance(
        [(1.0, 0.0, 0.0)],
        geometry,
        frame_verified=True,
    ) is None


def test_empty_scan_rejected(geometry):
    assert convert([], geometry) is None


def test_nan_rejected(geometry):
    assert convert(
        [(math.nan, 0.0, 0.0)], geometry
    ) is None


def test_infinity_rejected(geometry):
    assert convert(
        [(math.inf, 0.0, 0.0)], geometry
    ) is None


def test_malformed_point_rejected(geometry):
    assert convert([(1.0, 0.0)], geometry) is None


def test_near_forward_obstacle(geometry):
    c = convert([(0.6, 0.0, 0.0)], geometry)
    assert c is not None
    assert c.forward == pytest.approx(0.3)
    assert c.turn == pytest.approx(0.3)


def test_far_forward_obstacle(geometry):
    c = convert([(2.0, 0.0, 0.0)], geometry)
    assert c.forward == pytest.approx(1.7)


def test_left_obstacle(geometry):
    c = convert([(0.0, 0.4, 0.0)], geometry)
    assert c.left == pytest.approx(0.2)


def test_right_obstacle(geometry):
    c = convert([(0.0, -0.4, 0.0)], geometry)
    assert c.right == pytest.approx(0.2)


def test_backward_obstacle(geometry):
    c = convert([(-0.6, 0.0, 0.0)], geometry)
    assert c.backward == pytest.approx(0.3)


def test_inside_footprint(geometry):
    c = convert([(0.0, 0.0, 0.0)], geometry)
    assert all(v == 0 for v in vars(c).values())


def test_outside_height_returns_unknown(geometry):
    assert convert([(1.0, 0.0, 2.0)], geometry) is None


def test_outside_range_returns_unknown(geometry):
    assert convert([(10.0, 0.0, 0.0)], geometry) is None


def test_unknown_direction_blocked(geometry):
    c = convert([(2.0, 0.0, 0.0)], geometry)
    assert c.backward == 0.0
    assert c.left == 0.0
    assert c.right == 0.0


def test_safety_filter_stops_near_obstacle(geometry):
    c = convert([(0.6, 0.0, 0.0)], geometry)
    safety = ObstacleSafetyFilter()
    assert safety.observe(c)
    assert not safety.safe(0.1, 0.0, 0.0)


def test_safety_filter_accepts_far_forward(geometry):
    c = convert([(2.0, 0.0, 0.0)], geometry)
    safety = ObstacleSafetyFilter()
    assert safety.observe(c)
    assert safety.safe(0.1, 0.0, 0.0)


def test_sensor_failure_invalidates_filter(geometry):
    safety = ObstacleSafetyFilter()
    c = convert([(2.0, 0.0, 0.0)], geometry)
    assert safety.observe(c)
    assert not safety.observe(None)
    assert not safety.safe(0.1, 0.0, 0.0)


def test_stale_sensor_blocks_motion(geometry):
    now = [0.0]
    safety = ObstacleSafetyFilter(clock=lambda: now[0])
    c = convert([(2.0, 0.0, 0.0)], geometry)
    assert safety.observe(c)
    now[0] = 0.3
    assert not safety.safe(0.1, 0.0, 0.0)


def test_invalid_geometry_rejected():
    with pytest.raises(ValueError):
        LidarGeometry(1.0, 0.0, 0.2, 0.3, 5.0)
