"""M25-A10: fail-closed offline LiDAR-to-Clearance adapter.

Input coordinates and units must be explicitly validated.
No WebRTC connection or robot command is performed here.
"""

from dataclasses import dataclass
import math

from core.safety.obstacle import Clearance


@dataclass(frozen=True)
class LidarGeometry:
    """Explicit geometry contract for normalized robot-frame points.

    x: forward, y: left, z: up; all coordinates in metres.
    """

    min_z: float
    max_z: float
    half_width: float
    half_length: float
    max_range: float

    def __post_init__(self):
        values = (
            self.min_z,
            self.max_z,
            self.half_width,
            self.half_length,
            self.max_range,
        )
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Non-finite geometry")
        if self.min_z >= self.max_z:
            raise ValueError("Invalid height interval")
        if self.half_width <= 0 or self.half_length <= 0:
            raise ValueError("Invalid robot dimensions")
        if self.max_range <= 0:
            raise ValueError("Invalid maximum range")


def points_to_clearance(
    points,
    geometry,
    *,
    frame_verified=False,
    scan_complete=False,
):
    """Convert validated robot-frame XYZ points to Clearance.

    Returns None on invalid, empty or unverified input.

    Clearance distances are measured from the robot's
    rectangular footprint, not from its centre.

    This is an offline prototype. It does not certify
    coverage, occlusion handling or physical safety.
    """

    if not isinstance(geometry, LidarGeometry):
        return None

    if frame_verified is not True or scan_complete is not True:
        return None

    if not isinstance(points, (list, tuple)) or not points:
        return None

    parsed = []

    for point in points:
        if not isinstance(point, (list, tuple)):
            return None
        if len(point) != 3:
            return None
        if any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            for v in point
        ):
            return None

        parsed.append(tuple(float(v) for v in point))

    forward = math.inf
    backward = math.inf
    left = math.inf
    right = math.inf
    turn = math.inf

    relevant = 0

    for x, y, z in parsed:
        if not geometry.min_z <= z <= geometry.max_z:
            continue

        distance = math.hypot(x, y)
        if distance > geometry.max_range:
            continue

        relevant += 1

        dx = max(abs(x) - geometry.half_length, 0.0)
        dy = max(abs(y) - geometry.half_width, 0.0)
        footprint_distance = math.hypot(dx, dy)

        # Any point inside the footprint gives zero clearance.
        if dx == 0 and dy == 0:
            return Clearance(0.0, 0.0, 0.0, 0.0, 0.0)

        # Conservative directional sector assignment.
        if x >= geometry.half_length:
            forward = min(forward, footprint_distance)

        if x <= -geometry.half_length:
            backward = min(backward, footprint_distance)

        if y >= geometry.half_width:
            left = min(left, footprint_distance)

        if y <= -geometry.half_width:
            right = min(right, footprint_distance)

        turn = min(turn, footprint_distance)

    if relevant == 0:
        return None

    # Unknown directions remain blocked.
    def value(v):
        return 0.0 if math.isinf(v) else v

    return Clearance(
        forward=value(forward),
        backward=value(backward),
        left=value(left),
        right=value(right),
        turn=value(turn),
    )
